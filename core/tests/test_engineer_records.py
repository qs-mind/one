"""Engineer Records keep their own key per data folder (5 Nov 2026).

Before, every data folder kept this key under "project:engineer", so a core started with another
data folder (the smoke test of a packaged core) made its own file and wrote over the key of the
engineer's real one. The key store is in memory; "another data folder" is a second folder."""

import logging
import secrets
from datetime import UTC, datetime

import keyring
import pytest
from fastapi.testclient import TestClient

from qsone import copy
from qsone.app import create_app
from qsone.backup import keys
from qsone.journey import engineer as card
from qsone.keys import SERVICE
from qsone.records import engineer, vault
from qsone.records.project import FILE_NAME, Records, RecordsError
from tests.conftest import AUTH, SECRET
from tests.engine_fakes import FakeSleep

CARD = {"role": "contractor", "country": "EG", "city": "القاهرة", "currency": "EGP"}
CARD_IN = card.Card.model_validate(CARD)
OLD = (SERVICE, "project:engineer")
TODAY = datetime.now(UTC).strftime("%Y-%m-%d")


def entries(memory_keyring) -> set[str]:
    return {user for service, user in memory_keyring.store if service == SERVICE}


def old_style(data_dir) -> Records:
    """An Engineer Records file as One made it before: its key under "project:engineer"."""
    rec = Records.create(data_dir / "engineer", name=engineer.NAME, actor="engineer")
    card.save_card(rec, CARD_IN)
    return rec


def test_each_data_folder_has_its_own_key(tmp_path, memory_keyring):
    first = engineer.open_records(tmp_path / "a")
    card.save_card(first, CARD_IN)
    first.close()
    engineer.open_records(tmp_path / "b").close()  # a smoke test's core, say

    again = engineer.open_records(tmp_path / "a")
    assert card.card(again) == CARD
    eid = engineer.read_id(tmp_path / "a" / "engineer")
    assert again.key_id == f"engineer-{eid}" and again.meta()[engineer.META] == eid
    again.close()
    assert engineer.read_id(tmp_path / "b" / "engineer") != eid
    assert OLD not in memory_keyring.store
    assert len([u for u in entries(memory_keyring) if u.startswith("project:engineer-")]) == 2


def test_a_file_from_before_moves_to_its_own_key(data_dir, memory_keyring):
    old_style(data_dir).close()
    old_key = memory_keyring.store[OLD]

    rec = engineer.open_records(data_dir)
    eid = engineer.read_id(data_dir / "engineer")
    assert card.card(rec) == CARD and rec.meta()[engineer.META] == eid
    assert memory_keyring.store[(SERVICE, f"project:engineer-{eid}")] == old_key
    assert memory_keyring.store[OLD] == old_key  # another data folder may still need it
    doc = keys.read_doc(data_dir / "engineer" / keys.KEY_FILE)
    assert keys.unwrap(doc, backup_key=keys.backup_key()) == bytes.fromhex(old_key)
    rec.close()

    del memory_keyring.store[OLD]
    again = engineer.open_records(data_dir)  # opens by its own id now
    assert card.card(again) == CARD
    again.close()


def test_a_file_whose_old_key_was_overwritten_is_kept_aside(data_dir, memory_keyring, caplog):
    old_style(data_dir).close()
    mine = (data_dir / "engineer" / FILE_NAME).read_bytes()
    memory_keyring.store[OLD] = secrets.token_hex(32)  # another folder's core wrote its key

    caplog.set_level(logging.INFO)
    rec = engineer.open_records(data_dir)
    assert card.card(rec) == {}  # a new file
    rec.close()
    aside = data_dir / "engineer" / f"{FILE_NAME}.unreadable-{TODAY}"
    assert aside.read_bytes()[:4096] == mine[:4096]  # kept, never deleted
    assert "القاهرة" not in caplog.text and "contractor" not in caplog.text


def test_a_lost_key_comes_back_from_key_json(data_dir, memory_keyring):
    rec = engineer.open_records(data_dir)
    card.save_card(rec, CARD_IN)
    rec.close()
    del memory_keyring.store[(SERVICE, f"project:{rec.key_id}")]

    again = engineer.open_records(data_dir)
    assert card.card(again) == CARD and again.key_id == rec.key_id
    again.close()
    assert not list((data_dir / "engineer").glob("*.unreadable-*"))


def test_an_overwritten_old_key_comes_back_from_key_json(data_dir, memory_keyring):
    rec = old_style(data_dir)
    key = vault.get_key("engineer")
    doc = keys.wrap(key, project_id="engineer", backup_key=keys.ensure_backup_key())
    keys.write_doc(rec.folder / keys.KEY_FILE, doc)  # a backup ran before the key was lost
    rec.close()
    memory_keyring.store[OLD] = secrets.token_hex(32)

    again = engineer.open_records(data_dir)
    assert card.card(again) == CARD
    assert vault.get_key(again.key_id) == key
    again.close()


def test_a_key_json_with_another_files_key_is_written_again(data_dir, memory_keyring):
    rec = old_style(data_dir)
    stale = keys.wrap(
        secrets.token_bytes(32), project_id="engineer", backup_key=keys.ensure_backup_key()
    )
    keys.write_doc(
        rec.folder / keys.KEY_FILE, stale
    )  # what a backup made with another folder's key
    rec.close()

    again = engineer.open_records(data_dir)
    doc = keys.read_doc(again.folder / keys.KEY_FILE)
    assert keys.unwrap(doc, backup_key=keys.backup_key()) == vault.get_key(again.key_id)
    again.close()


def test_key_store_down_sets_nothing_aside(data_dir, memory_keyring, failing_keyring):
    keyring.set_keyring(memory_keyring)
    engineer.open_records(data_dir).close()
    keyring.set_keyring(failing_keyring)
    with pytest.raises(RecordsError) as e:
        engineer.open_records(data_dir)
    assert e.value.text == copy.PROJECT_KEY_STORE_DOWN and e.value.status == 503
    assert (data_dir / "engineer" / FILE_NAME).is_file()
    assert not list((data_dir / "engineer").glob("*.unreadable-*"))


@pytest.mark.parametrize("left", [[], ["key.json"], ["key.json", "records.db-wal", "id"]])
def test_a_folder_without_its_file_is_used(data_dir, left):
    folder = data_dir / "engineer"
    folder.mkdir(parents=True)
    for name in left:
        (folder / name).write_bytes(b"kept - sample")
    rec = engineer.open_records(data_dir)
    rec.close()
    for name in left:
        if name != "id":  # an id with no file is only written over
            kept = name.replace(FILE_NAME, f"{FILE_NAME}.unreadable-{TODAY}", 1)
            if kept == name:
                kept = f"{name}.unreadable-{TODAY}"
            assert (folder / kept).read_bytes() == b"kept - sample"


# The core ----------------------------------------------------------------------------------------


def client() -> TestClient:
    return TestClient(create_app(SECRET, connectors=lambda: [], sleep=FakeSleep()))


def test_card_saves_after_an_unreadable_file_was_set_aside(data_dir, memory_keyring):
    """The founder's core on 5 Nov 2026: the file did not open, it was moved aside by hand, and
    PUT /engineer/card answered 500 (`Records.create` refused the existing folder)."""
    old_style(data_dir).close()
    memory_keyring.store[OLD] = secrets.token_hex(32)
    with client() as c:
        assert c.put("/engineer/card", json=CARD, headers=AUTH).status_code == 200
        assert c.get("/engineer/card", headers=AUTH).json() == CARD
    assert (data_dir / "engineer" / f"{FILE_NAME}.unreadable-{TODAY}").is_file()


def test_card_saves_after_the_file_was_moved_by_hand(data_dir, memory_keyring, failing_keyring):
    keyring.set_keyring(memory_keyring)
    old_style(data_dir).close()
    keyring.set_keyring(failing_keyring)
    with client() as c:  # the key store is down: the file did not open at start
        keyring.set_keyring(memory_keyring)
        (data_dir / "engineer" / FILE_NAME).rename(data_dir / "aside.db")  # moved by hand
        r = c.put("/engineer/card", json=CARD, headers=AUTH)
        assert r.status_code == 200, r.text
        assert c.get("/engineer/card", headers=AUTH).json() == CARD


@pytest.mark.parametrize("left", [[], ["key.json"], ["records.db.unreadable-2026-11-05"]])
def test_core_starts_with_a_folder_without_its_file(data_dir, memory_keyring, left):
    folder = data_dir / "engineer"
    folder.mkdir(parents=True)
    for name in left:
        (folder / name).write_bytes(b"kept - sample")
    with client() as c:
        assert c.get("/health", headers=AUTH).status_code == 200
        assert c.put("/engineer/card", json=CARD, headers=AUTH).status_code == 200
    assert (folder / FILE_NAME).is_file() and engineer.read_id(folder) is not None


# Backup and restore -----------------------------------------------------------------------------


def test_restored_on_another_computer_they_keep_their_id(
    tmp_path, data_dir, monkeypatch, memory_keyring
):
    from tests.test_backup_store import Machine, other_computer

    usb = tmp_path / "usb"
    usb.mkdir()
    here = Machine(data_dir)
    mine = engineer.open_records(data_dir)
    card.save_card(mine, CARD_IN)
    here.backups.engineer = lambda: mine
    here.backups.set_folder(str(usb))
    assert here.backups.run(reason="manual") == 1
    eid, backup_key = engineer.read_id(mine.folder), keys.backup_key()
    mine.close()

    there = other_computer(tmp_path, monkeypatch, memory_keyring)
    keys.set_backup_key(backup_key)  # say, from the account
    assert there.backups.restore(str(usb), "engineer", None)["name"] == engineer.NAME
    assert engineer.read_id(there.data_dir / "engineer") == eid
    assert f"project:engineer-{eid}" in entries(memory_keyring)
    assert OLD not in memory_keyring.store
    rec = engineer.open_records(there.data_dir)
    assert card.card(rec) == CARD and rec.key_id == f"engineer-{eid}"
    rec.close()


def test_a_backup_from_before_restores_under_a_new_id(tmp_path, data_dir, memory_keyring):
    from qsone.backup import store

    usb = tmp_path / "usb"
    rec = old_style(data_dir)
    key = vault.get_key("engineer")
    backup_key = keys.ensure_backup_key()
    dest = store.base(usb) / "engineer"
    store.snapshot(rec, dest, key, now="2026-11-04T08:00:00+00:00")
    doc = keys.wrap(key, project_id="engineer", backup_key=backup_key)
    keys.write_doc(dest / keys.KEY_FILE, doc)
    rec.close()

    other = tmp_path / "other"
    store.restore(usb, "engineer", other, backup_key=backup_key, code=None)
    eid = engineer.read_id(other / "engineer")
    assert eid is not None and vault.get_key(f"engineer-{eid}") == key
    again = engineer.open_records(other)
    assert card.card(again) == CARD
    again.close()
