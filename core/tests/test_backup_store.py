"""Backup copies, key files, restore and the runner (Plan 8, Task 4). The key store is in memory;
"another computer" is a new data folder with an empty key store."""

import logging
from datetime import UTC, datetime, timedelta

import pytest

from qsone import copy, settings
from qsone.backup import keys, store
from qsone.backup.keys import BackupError
from qsone.backup.runner import Backups
from qsone.keys import SERVICE
from qsone.projects import Projects
from qsone.records import db, schema, search, vault
from qsone.records.files import add_file
from qsone.records.project import RecordsError
from tests.samples import sample_xlsx
from tests.test_backup_keys import RecordingEscrow

BOQ = "جدول الكميات - عينة.xlsx"
WORDS = ["خرسانة مسلحة", "03/02", "عينة"]


def boq() -> bytes:
    return sample_xlsx({"BOQ": [["03/02", "خرسانة مسلحة للأسقف", "م3", 120]]})


class Machine:
    """One computer: its data folder, its projects and its backups."""

    def __init__(self, data_dir, escrow=None):
        self.data_dir = data_dir
        self.projects = Projects(data_dir)
        self.backups = Backups(data_dir, self.projects, escrow_factory=lambda: escrow)
        self.projects.backups = self.backups

    def new_project(self, name="برج - عينة") -> str:
        pid = self.projects.create(name, "engineer")["id"]
        add_file(self.projects.get(pid), BOQ, boq(), actor="engineer")
        return pid


@pytest.fixture
def recording_escrow():
    return RecordingEscrow()


@pytest.fixture
def machine(data_dir, recording_escrow):
    m = Machine(data_dir, recording_escrow)
    yield m
    m.projects.close_all()


@pytest.fixture
def usb(tmp_path):
    folder = tmp_path / "usb"
    folder.mkdir()
    return folder


def other_computer(tmp_path, monkeypatch, memory_keyring, escrow=None) -> Machine:
    memory_keyring.store.clear()
    data = tmp_path / "other"
    monkeypatch.setenv("QSONE_DATA_DIR", str(data))
    return Machine(data, escrow)


def blob(folder) -> bytes:
    return b"".join(p.read_bytes() for p in folder.rglob("*") if p.is_file())


def test_snapshot_keeps_everything_and_shows_nothing(rec, tmp_path):
    add_file(rec, BOQ, boq(), actor="engineer")
    key = vault.get_key(rec.id)
    path = store.snapshot(rec, tmp_path / "b", key, now="2026-11-05T08:00:00Z")
    assert path.name == "2026-11-05T080000Z.db"
    conn = db.connect(path, key)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == len(schema.MIGRATIONS)
    assert conn.execute("SELECT count(*) FROM chunks").fetchone()[0] == 1
    conn.close()
    assert sorted(p.name for p in (tmp_path / "b").iterdir()) == [path.name]  # one file, no WAL
    for word in WORDS:
        assert word.encode() not in blob(tmp_path / "b")


def test_prune_keeps_ten_newest_and_one_a_day(tmp_path):
    now = datetime(2026, 11, 5, 20, 0, tzinfo=UTC)
    made = []
    for day in range(35):  # one a day for 35 days, and 5 more today: 40
        made.append(now - timedelta(days=day, hours=1))
    made += [now - timedelta(minutes=10 * i) for i in range(1, 6)]
    for at in made:
        (tmp_path / f"{at.strftime('%Y-%m-%dT%H%M%SZ')}.db").write_bytes(b"")
    (tmp_path / "key.json").write_text("{}")
    removed = store.prune(tmp_path, now)
    kept = sorted(p.name for p in tmp_path.glob("*.db"))
    # newest 10 = today's 6 + days 1-4; dailies = days 0-29: 10 + 25 = 35 kept, days 30-34 go
    assert len(kept) == 35 and len(removed) == 5
    assert all(p.name < min(kept) for p in removed)
    assert (tmp_path / "key.json").is_file()


def test_key_json_is_written_on_create_and_holds_no_key(machine, memory_keyring):
    pid = machine.new_project()
    doc = keys.read_doc(machine.projects.root / pid / keys.KEY_FILE)
    key = vault.get_key(pid)
    assert doc["kind"] == "backup_key" and keys.unwrap(doc, backup_key=keys.backup_key()) == key
    assert key.hex() not in str(doc)


def test_an_older_project_gets_its_key_json_when_opened(machine):
    pid = machine.new_project()
    machine.projects.close(pid)
    (machine.projects.root / pid / keys.KEY_FILE).unlink()
    machine.projects.open(pid)
    assert (machine.projects.root / pid / keys.KEY_FILE).is_file()


def test_lost_key_comes_back_from_key_json(machine, memory_keyring, caplog):
    pid = machine.new_project()
    machine.projects.close(pid)
    machine.projects._known.clear()
    del memory_keyring.store[(SERVICE, f"project:{pid}")]
    with caplog.at_level(logging.INFO):
        opened = machine.projects.open(pid)
    assert opened["note"] == copy.PROJECT_KEY_RESTORED and opened["name"] == "برج - عينة"
    assert search.search(machine.projects.get(pid), "03/02").hits
    assert (SERVICE, f"project:{pid}") in memory_keyring.store
    logged = caplog.text
    assert "PROJECT_KEY_RESTORED" in logged and pid in logged and "برج" not in logged


def test_lost_key_and_lost_backup_key_asks_for_sign_in_or_code(data_dir, memory_keyring):
    m = Machine(data_dir)  # no account
    pid = m.new_project()
    m.projects.close(pid)
    memory_keyring.store.clear()
    with pytest.raises(RecordsError) as e:
        m.projects.open(pid)
    assert e.value.text == copy.BACKUP_NEEDS_SIGN_IN


def test_lost_key_comes_back_with_the_account_key(data_dir, memory_keyring):
    escrow = RecordingEscrow()
    m = Machine(data_dir, escrow)
    pid = m.new_project()
    m.projects.close(pid)
    memory_keyring.store.clear()  # the escrow still holds the Backup key
    assert m.projects.open(pid)["note"] == copy.PROJECT_KEY_RESTORED
    m.projects.close_all()


def test_confidential_key_never_meets_the_backup_key_or_the_escrow(machine, recording_escrow, usb):
    pid = machine.new_project()
    bk = keys.backup_key()
    machine.backups.set_folder(str(usb))
    assert machine.backups.run(reason="manual") == 1  # one Backup key wrap in the folder now
    answer = machine.backups.set_confidential(pid, True)
    code = answer["code"]
    assert answer["confidential"] is True and keys.normalise_code(code)
    for place in (
        machine.projects.root / pid,
        store.base(usb) / pid,
        machine.data_dir / "snapshots" / pid,
    ):
        doc = keys.read_doc(place / keys.KEY_FILE)
        assert doc["kind"] == "code" and "key_id" not in doc
        with pytest.raises(BackupError):
            keys.unwrap(doc, backup_key=bk)
        assert keys.unwrap(doc, code=code) == vault.get_key(pid)
    add_file(machine.projects.get(pid), "مذكرة - عينة.xlsx", boq() + b"", actor="engineer")
    machine.backups.run(reason="manual")
    assert keys.read_doc(store.base(usb) / pid / keys.KEY_FILE)["kind"] == "code"
    assert recording_escrow.puts == [bk]
    assert machine.projects.list()[0]["confidential"] is True

    off = machine.backups.set_confidential(pid, False)
    assert off == {"confidential": False}
    doc = keys.read_doc(store.base(usb) / pid / keys.KEY_FILE)
    assert keys.unwrap(doc, backup_key=bk) == vault.get_key(pid)


def test_new_computer_restores_with_the_backup_key(
    machine, usb, tmp_path, monkeypatch, memory_keyring, recording_escrow
):
    pid = machine.new_project()
    machine.backups.set_folder(str(usb))
    assert machine.backups.run(reason="manual") == 1
    for word in WORDS:
        assert word.encode() not in blob(usb)
    machine.projects.close_all()

    b = other_computer(tmp_path, monkeypatch, memory_keyring, escrow=recording_escrow)
    (listed,) = b.backups.found(str(usb))
    assert listed["id"] == pid and listed["name"] == "برج - عينة" and listed["needs"] is None
    assert listed["last_backup"].endswith("Z")
    assert b.backups.restore(str(usb), pid, None) == {"id": pid, "name": "برج - عينة"}
    b.projects.open(pid)
    assert search.search(b.projects.get(pid), "03/02").hits
    assert keys.backup_key() == recording_escrow.held  # the account's key is this computer's now
    b.projects.close_all()


def test_new_computer_without_an_account_restores_with_the_backup_code(
    data_dir, usb, tmp_path, monkeypatch, memory_keyring
):
    a = Machine(data_dir)
    pid = a.new_project()
    a.backups.set_folder(str(usb))
    code = a.backups.new_code()
    a.backups.confirm("backup-key", code[-5:].lower())
    assert a.backups.status()["backup_key"]["code_saved"] is True
    a.backups.run(reason="manual")
    a.projects.close_all()

    b = other_computer(tmp_path, monkeypatch, memory_keyring)
    (listed,) = b.backups.found(str(store.base(usb)))  # the inner folder works too
    assert listed["needs"] == "backup_code" and listed["name"] is None
    with pytest.raises(BackupError) as e:
        b.backups.restore(str(usb), pid, None)
    assert e.value.text == copy.BACKUP_NEEDS_CODE
    with pytest.raises(BackupError) as e:
        b.backups.restore(str(usb), pid, keys.new_recovery_code())
    assert e.value.text == copy.RECOVERY_CODE_WRONG
    assert b.backups.restore(str(usb), pid, code)["name"] == "برج - عينة"
    assert b.backups.found(str(usb))[0]["needs"] is None  # the Backup key is here now
    b.projects.open(pid)
    assert search.search(b.projects.get(pid), "03/02").hits
    b.projects.close_all()


def test_without_account_or_code_restore_asks_for_sign_in(
    data_dir, usb, tmp_path, monkeypatch, memory_keyring
):
    a = Machine(data_dir)
    pid = a.new_project()
    a.backups.set_folder(str(usb))
    a.backups.run(reason="manual")
    a.projects.close_all()
    b = other_computer(tmp_path, monkeypatch, memory_keyring)
    assert b.backups.found(str(usb))[0]["needs"] == "sign_in"
    with pytest.raises(BackupError) as e:
        b.backups.restore(str(usb), pid, None)
    assert e.value.text == copy.BACKUP_NEEDS_SIGN_IN


def test_confidential_project_restores_only_with_its_code(
    machine, usb, tmp_path, monkeypatch, memory_keyring, recording_escrow
):
    pid = machine.new_project()
    code = machine.backups.set_confidential(pid, True)["code"]
    machine.backups.set_folder(str(usb))
    machine.backups.run(reason="manual")
    machine.projects.close_all()
    b = other_computer(tmp_path, monkeypatch, memory_keyring, escrow=recording_escrow)
    assert b.backups.found(str(usb))[0]["needs"] == "project_code"
    with pytest.raises(BackupError) as e:
        b.backups.restore(str(usb), pid, None)  # the account's key does not open it
    assert e.value.text == copy.BACKUP_NEEDS_CODE
    with pytest.raises(BackupError) as e:
        b.backups.restore(str(usb), pid, keys.new_recovery_code())
    assert e.value.text == copy.RECOVERY_CODE_WRONG
    assert b.backups.restore(str(usb), pid, code)["name"] == "برج - عينة"
    assert keys.read_doc(b.projects.root / pid / keys.KEY_FILE)["kind"] == "code"
    assert b.projects.open(pid)["confidential"] is True
    b.projects.close_all()


def test_restore_over_an_existing_project_snapshots_it_first(machine, usb):
    pid = machine.new_project()
    machine.backups.set_folder(str(usb))
    machine.backups.run(reason="manual")
    add_file(
        machine.projects.get(pid),
        "مقايسة - عينة.xlsx",
        sample_xlsx({"A": [["x", 1]]}),
        actor="engineer",
    )
    snapshots = machine.data_dir / "snapshots" / pid
    machine.backups.clock = lambda: datetime(2026, 11, 6, 9, 0, tzinfo=UTC)
    before = set(snapshots.glob("*.db"))
    assert machine.backups.restore(str(usb), pid, None)["id"] == pid
    (kept,) = set(snapshots.glob("*.db")) - before
    conn = db.connect(kept, vault.get_key(pid), readonly=True)
    assert conn.execute("SELECT count(*) FROM files").fetchone()[0] == 2  # the newer file kept
    conn.close()
    machine.projects.open(pid)
    rec = machine.projects.get(pid)
    with rec.read() as conn:
        assert conn.execute("SELECT count(*) FROM files").fetchone()[0] == 1  # as backed up


def test_run_skips_projects_that_did_not_change(machine, usb):
    pid = machine.new_project()
    machine.backups.set_folder(str(usb))
    assert machine.backups.run(reason="manual") == 1
    assert machine.backups.run(reason="timer") == 0
    add_file(
        machine.projects.get(pid),
        "مقايسة - عينة.xlsx",
        sample_xlsx({"A": [["x", 1]]}),
        actor="engineer",
    )
    machine.backups.clock = lambda: datetime.now(UTC) + timedelta(seconds=2)
    assert machine.backups.run(reason="timer") == 1
    assert len(list((store.base(usb) / pid).glob("*.db"))) == 2
    state = settings.load()["backups"][pid]
    assert set(state) == {"at", "audit_id"}  # ids and times only


def test_closing_a_project_backs_it_up(machine, usb):
    pid = machine.new_project()
    machine.backups.set_folder(str(usb))
    machine.projects.close(pid)
    assert list((store.base(usb) / pid).glob("*.db"))
    assert machine.backups.run(pid, reason="manual") == 0  # closed and unchanged


def test_local_snapshots_without_a_folder_keep_three(machine):
    pid = machine.new_project()
    rec = machine.projects.get(pid)
    for i in range(5):
        add_file(rec, f"ملف {i} - عينة.xlsx", sample_xlsx({"A": [[f"x{i}", i]]}), actor="engineer")
        machine.backups.clock = lambda i=i: datetime(2026, 11, 5, 8, i, tzinfo=UTC)
        assert machine.backups.run(reason="timer") == 0  # no folder: nothing counted
    assert len(list((machine.data_dir / "snapshots" / pid).glob("*.db"))) == 3


def test_engineer_records_are_backed_up_like_a_project(machine, general, usb):
    machine.backups.set_folder(str(usb))
    machine.backups.engineer = lambda: general
    assert machine.backups.run(reason="manual") == 1
    found = {f["id"]: f for f in machine.backups.found(str(usb))}
    assert found["engineer"]["needs"] is None and found["engineer"]["name"] == "Engineer Records"


def test_unreachable_folder_is_reported_not_raised(machine, usb):
    machine.new_project()
    machine.backups.set_folder(str(usb))
    machine.backups.run(reason="manual")
    usb.rename(usb.with_name("gone"))
    assert machine.backups.run(reason="timer") == 0
    status = machine.backups.status()
    assert status["reachable"] is False
    day = settings.load()["backup"]["last_ok"][:10]
    assert status["note"] == copy.fill(copy.BACKUP_FOLDER_UNREACHABLE, date=day)


def test_a_folder_that_cannot_be_written_is_refused(machine, tmp_path):
    with pytest.raises(BackupError) as e:
        machine.backups.set_folder("relative/folder")
    assert e.value.text == copy.BACKUP_FOLDER_NOT_WRITABLE
    with pytest.raises(BackupError):
        machine.backups.set_folder(str(tmp_path / "missing"))


def test_last_group_must_match(machine):
    machine.new_project()
    code = machine.backups.new_code()
    with pytest.raises(BackupError) as e:
        machine.backups.confirm("backup-key", "ZZZZZ" if not code.endswith("ZZZZZ") else "00000")
    assert e.value.text == copy.RECOVERY_LAST_GROUP_WRONG
    assert machine.backups.status()["backup_key"]["code_saved"] is False
    assert code not in (machine.data_dir / "settings.json").read_text()
    assert code.replace("-", "") not in blob(machine.data_dir).decode("latin-1")
