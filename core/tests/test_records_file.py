"""The encrypted project file: key, schema, migrations, Guardrail triggers and audit trail."""

import hashlib
import json

import pytest
from keyring.errors import KeyringError

from qsone import copy
from qsone.records import audit, db, schema
from qsone.records.project import Records, RecordsError

ITEM = (
    "insert into items(id,kind,code,fields,created_at,created_by,updated_at,updated_by)"
    " values (?,'boq_item',?,?,'t','e','t','e')"
)


def add_number(c, number_id="n1"):
    c.execute(
        "insert or ignore into sources(id,kind,title,recorded_at,recorded_by)"
        " values ('s1','quote','عرض سعر - عينة','t','e')"
    )
    c.execute(ITEM.replace("insert", "insert or ignore"), ("i1", "03/02", "{}"))
    c.execute(
        "insert into numbers(id,item_id,name,value,unit,currency,source_id,dated,"
        "recorded_at,recorded_by) values (?,'i1','rate','39850.50','m3','EGP','s1',"
        "'2026-11-02','t','e')",
        (number_id,),
    )


def test_create_reopen_keeps_the_name(tmp_path):
    rec = Records.create(tmp_path / "p", name="مدرسة - عينة", actor="engineer")
    rec.close()
    rec = Records.open(tmp_path / "p")
    assert rec.meta()["name"] == "مدرسة - عينة"
    assert rec.meta()["created_by"] == "engineer"
    rec.close()


def test_key_lives_only_in_the_key_store(tmp_path, memory_keyring):
    rec = Records.create(tmp_path / "p", name="x", actor="engineer")
    key = memory_keyring.store[("QS Mind One", f"project:{rec.id}")]
    assert len(bytes.fromhex(key)) == 32
    files = [p for p in (tmp_path / "p").rglob("*") if p.is_file()]
    assert all(key.encode() not in p.read_bytes() for p in files)
    rec.close()


def test_nothing_readable_on_disk_open_or_closed(tmp_path):
    rec = Records.create(tmp_path / "p", name="مشروع سري - عينة", actor="engineer")
    with rec.write("engineer") as c:
        fields = json.dumps({"description": "خرسانة مسلحة للأسقف"}, ensure_ascii=False)
        c.execute(ITEM, ("i1", "03/02", fields))
    for phase in ("open", "closed"):
        blob = b"".join(p.read_bytes() for p in (tmp_path / "p").rglob("*") if p.is_file())
        for word in ["مشروع سري", "خرسانة مسلحة", "03/02"]:
            assert word.encode() not in blob, (phase, word)
        rec.close()


def test_missing_key_says_so(tmp_path, memory_keyring):
    rec = Records.create(tmp_path / "p", name="x", actor="engineer")
    rec.close()
    memory_keyring.store.clear()
    with pytest.raises(RecordsError) as e:
        Records.open(tmp_path / "p")
    assert e.value.text == copy.PROJECT_KEY_MISSING


def test_wrong_key_or_damage_says_so(tmp_path, memory_keyring):
    rec = Records.create(tmp_path / "p", name="x", actor="engineer")
    rec.close()
    entry = ("QS Mind One", f"project:{rec.id}")
    key = memory_keyring.store[entry]
    memory_keyring.store[entry] = "22" * 32
    with pytest.raises(RecordsError) as e:
        Records.open(tmp_path / "p")
    assert e.value.text == copy.PROJECT_DAMAGED

    memory_keyring.store[entry] = key
    path = tmp_path / "p" / "records.db"
    data = bytearray(path.read_bytes())
    middle = len(data) // 2
    data[middle : middle + 4096] = bytes(4096)
    path.write_bytes(bytes(data))
    # Opening reads only a few pages; damage elsewhere is found when its page is read.
    with pytest.raises(RecordsError) as e:
        rec = Records.open(tmp_path / "p")
        try:
            with rec.read() as c:
                tables = c.execute("select name from sqlite_master where type = 'table'")
                for (table,) in tables.fetchall():
                    c.execute(f'select * from "{table}"').fetchall()
        finally:
            rec.close()
    assert e.value.text == copy.PROJECT_DAMAGED
    with pytest.raises(RecordsError) as e, rec.read():
        pass
    assert e.value.text == copy.PROJECT_NOT_OPEN


def test_damage_at_the_start_is_found_on_open(tmp_path):
    rec = Records.create(tmp_path / "p", name="x", actor="engineer")
    rec.close()
    path = tmp_path / "p" / "records.db"
    data = bytearray(path.read_bytes())
    data[16:4096] = bytes(4080)
    path.write_bytes(bytes(data))
    with pytest.raises(RecordsError) as e:
        Records.open(tmp_path / "p")
    assert e.value.text == copy.PROJECT_DAMAGED


def test_a_folder_without_a_project_file_is_not_found(tmp_path):
    (tmp_path / "p").mkdir()
    with pytest.raises(RecordsError) as e:
        Records.open(tmp_path / "p")
    assert e.value.text == copy.PROJECT_NOT_FOUND and e.value.status == 404
    assert list((tmp_path / "p").iterdir()) == []


def test_migration_upgrades_and_keeps_data(tmp_path, monkeypatch):
    rec = Records.create(tmp_path / "p", name="x", actor="engineer")
    with rec.write("engineer") as c:
        c.execute(ITEM, ("i1", "03/02", "{}"))
    rec.close()
    monkeypatch.setattr(
        schema, "MIGRATIONS", [*schema.MIGRATIONS, "ALTER TABLE items ADD COLUMN zone TEXT"]
    )
    rec = Records.open(tmp_path / "p")
    with rec.read() as c:
        assert c.execute("PRAGMA user_version").fetchone()[0] == 2
        assert c.execute("select code, zone from items").fetchall() == [("03/02", None)]
    rec.close()


def test_a_failed_migration_changes_nothing(tmp_path, monkeypatch):
    rec = Records.create(tmp_path / "p", name="x", actor="engineer")
    rec.close()
    broken = ["ALTER TABLE items ADD COLUMN zone TEXT", "ALTER TABLE nope ADD COLUMN x TEXT"]
    monkeypatch.setattr(schema, "MIGRATIONS", [*schema.MIGRATIONS, *broken])
    with pytest.raises(RecordsError) as e:
        Records.open(tmp_path / "p")
    assert e.value.text == copy.PROJECT_DAMAGED
    monkeypatch.undo()
    rec = Records.open(tmp_path / "p")
    with rec.read() as c:
        assert c.execute("PRAGMA user_version").fetchone()[0] == 1
        columns = [row[1] for row in c.execute("PRAGMA table_info(items)")]
        assert "zone" not in columns
    rec.close()


def test_newer_file_is_refused_untouched(tmp_path):
    rec = Records.create(tmp_path / "p", name="x", actor="engineer")
    with rec.write("engineer") as c:
        c.execute("PRAGMA user_version = 99")
    rec.close()
    path = tmp_path / "p" / "records.db"
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(RecordsError) as e:
        Records.open(tmp_path / "p")
    assert e.value.text == copy.PROJECT_TOO_NEW
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


def test_numbers_cannot_be_edited_or_deleted(tmp_path):
    rec = Records.create(tmp_path / "p", name="x", actor="engineer")
    with rec.write("engineer") as c:
        add_number(c)
    for sql in ["update numbers set value = '1' where id = 'n1'", "delete from numbers"]:
        with pytest.raises(db.IntegrityError), rec.write("engineer") as c:
            c.execute(sql)
    with rec.write("engineer") as c:
        c.execute("update numbers set valid_until = '2026-11-03' where id = 'n1'")
    with pytest.raises(db.IntegrityError), rec.write("engineer") as c:
        c.execute("update numbers set valid_until = '2026-11-04' where id = 'n1'")
    with rec.read() as c:
        assert c.execute("select value, valid_until from numbers").fetchall() == [
            ("39850.50", "2026-11-03")
        ]
    rec.close()


def test_a_correction_needs_a_reason(tmp_path):
    rec = Records.create(tmp_path / "p", name="x", actor="engineer")
    with rec.write("engineer") as c:
        add_number(c)
    with pytest.raises(db.IntegrityError), rec.write("engineer") as c:
        c.execute(
            "insert into numbers(id,item_id,name,value,unit,currency,source_id,dated,"
            "recorded_at,recorded_by,replaces,reason) values ('n2','i1','rate','40000',"
            "'m3','EGP','s1','2026-11-03','t','e','n1','  ')"
        )
    rec.close()


def test_sources_files_and_items_are_never_deleted(tmp_path):
    rec = Records.create(tmp_path / "p", name="x", actor="engineer")
    with rec.write("engineer") as c:
        add_number(c)
        c.execute(
            "insert into files(id,name,kind,size,sha256,status,added_at,added_by)"
            " values ('f1','عينة.pdf','pdf',1,'aa','read','t','e')"
        )
    for sql in [
        "update sources set title = 'x'",
        "delete from sources",
        "delete from files",
        "delete from items",
    ]:
        with pytest.raises(db.IntegrityError), rec.write("engineer") as c:
            c.execute(sql)
    with rec.write("engineer") as c:
        c.execute("update files set valid_until = 't2' where id = 'f1'")
        c.execute("update items set code = '03/03', version = 2 where id = 'i1'")
    rec.close()


def test_audit_is_append_only(tmp_path):
    rec = Records.create(tmp_path / "p", name="x", actor="engineer")
    with rec.write("engineer") as c:
        audit.record(
            c,
            at="t1",
            actor="engineer",
            action="create",
            table="items",
            row_id="i1",
            before=None,
            after={"code": "03/02", "description": "خرسانة"},
        )
        audit.record(
            c,
            at="t2",
            actor="estimator",
            action="update",
            table="items",
            row_id="i1",
            before={"code": "03/02"},
            after={"code": "03/03"},
        )
    with rec.read() as c:
        rows = audit.history(c, "i1")
        assert [(h["action"], h["actor"]) for h in rows] == [
            ("create", "engineer"),
            ("update", "estimator"),
        ]
        assert rows[0]["before"] is None and rows[0]["after"]["description"] == "خرسانة"
        assert rows[1]["table"] == "items" and rows[1]["at"] == "t2"
        assert [h["action"] for h in audit.history(c, rec.id)] == ["create"]
    for sql in ["update audit set actor = 'x'", "delete from audit"]:
        with pytest.raises(db.IntegrityError), rec.write("engineer") as c:
            c.execute(sql)
    rec.close()


def test_failed_write_leaves_nothing(tmp_path):
    rec = Records.create(tmp_path / "p", name="x", actor="engineer")
    with pytest.raises(ValueError), rec.write("engineer") as c:
        c.execute(ITEM, ("i1", "03/02", "{}"))
        raise ValueError("stop")
    with rec.read() as c:
        assert c.execute("select count(*) from items").fetchone()[0] == 0
    with rec.write("engineer") as c:
        c.execute(ITEM, ("i1", "03/02", "{}"))
    rec.close()


def test_closed_project_says_open_it_first(tmp_path):
    rec = Records.create(tmp_path / "p", name="x", actor="engineer")
    rec.close()
    rec.close()
    with pytest.raises(RecordsError) as e, rec.read():
        pass
    assert e.value.text == copy.PROJECT_NOT_OPEN


def test_create_with_key_store_down_leaves_nothing(tmp_path, failing_keyring):
    with pytest.raises(KeyringError):
        Records.create(tmp_path / "p", name="x", actor="engineer")
    assert not (tmp_path / "p").exists()


def test_failed_create_removes_folder_and_key(tmp_path, memory_keyring, monkeypatch):
    def broken_connect(path, key):
        raise db.DatabaseError("disk full")

    monkeypatch.setattr(db, "connect", broken_connect)
    with pytest.raises(db.DatabaseError):
        Records.create(tmp_path / "p", name="x", actor="engineer")
    assert not (tmp_path / "p").exists() and memory_keyring.store == {}


def test_create_never_reuses_a_folder(tmp_path, memory_keyring):
    rec = Records.create(tmp_path / "p", name="x", actor="engineer")
    rec.close()
    key = dict(memory_keyring.store)
    with pytest.raises(FileExistsError):
        Records.create(tmp_path / "p", name="y", actor="engineer")
    assert memory_keyring.store == key
    rec = Records.open(tmp_path / "p")
    assert rec.meta()["name"] == "x"
    rec.close()
