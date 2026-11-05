"""The Backup key, key wraps and recovery codes (Plan 8, Task 4). The key store is in memory."""

import json
import re
import secrets

import pytest

from qsone import copy
from qsone.backup import keys
from qsone.backup.keys import BackupError
from qsone.keys import SERVICE


class RecordingEscrow:
    """Stands in for the account vault: keeps one Backup key and records each put."""

    def __init__(self, held: bytes | None = None):
        self.held = held
        self.puts: list[bytes] = []

    def get(self) -> bytes | None:
        return self.held

    def put(self, backup_key: bytes) -> None:
        self.puts.append(backup_key)
        self.held = backup_key


class DownEscrow:
    def get(self):
        raise ConnectionError("offline")

    def put(self, backup_key):
        raise ConnectionError("offline")


@pytest.fixture
def bk() -> bytes:
    return secrets.token_bytes(32)


def test_a_wrap_opens_only_for_its_project(bk):
    doc = keys.wrap(b"k" * 32, project_id="a" * 32, backup_key=bk)
    assert keys.unwrap(doc, backup_key=bk) == b"k" * 32
    with pytest.raises(BackupError) as e:
        keys.unwrap({**doc, "project_id": "b" * 32}, backup_key=bk)
    assert e.value.text == copy.BACKUP_KEY_WRONG
    with pytest.raises(BackupError):
        keys.unwrap(doc, backup_key=b"x" * 32)


def test_a_wrap_holds_no_key_in_the_clear(bk):
    key = secrets.token_bytes(32)
    text = json.dumps(keys.wrap(key, project_id="a" * 32, backup_key=bk))
    assert key.hex() not in text and bk.hex() not in text
    assert json.loads(text)["key_id"] == keys.key_id(bk) and len(keys.key_id(bk)) == 16


def test_recovery_code_reads_forgivingly():
    code = keys.new_recovery_code()
    assert re.fullmatch(r"([0-9A-HJKMNP-TV-Z]{5}-){4}[0-9A-HJKMNP-TV-Z]{5}", code)
    assert keys.normalise_code(code.lower().replace("-", " ")) == keys.normalise_code(code)
    assert keys.normalise_code("oOiIlL") == "001111"
    assert keys.last_group(code) == code[-5:]
    assert len({keys.new_recovery_code() for _ in range(50)}) == 50


def test_a_code_wrap_opens_with_the_code_typed_loosely():
    code = keys.new_recovery_code()
    doc = keys.wrap_with_code(b"k" * 32, project_id="a" * 32, code=code)
    loose = code.lower().replace("-", "  ").replace("0", "o").replace("1", "l")
    assert keys.unwrap(doc, code=loose) == b"k" * 32
    assert code not in json.dumps(doc) and keys.normalise_code(code) not in json.dumps(doc)


def test_wrong_code_says_so():
    doc = keys.wrap_with_code(b"k" * 32, project_id="a" * 32, code=keys.new_recovery_code())
    with pytest.raises(BackupError) as e:
        keys.unwrap(doc, code=keys.new_recovery_code())
    assert e.value.text == copy.RECOVERY_CODE_WRONG and e.value.status == 400
    with pytest.raises(BackupError) as e:
        keys.unwrap(doc)
    assert e.value.text == copy.BACKUP_NEEDS_CODE
    with pytest.raises(BackupError) as e:  # a damaged file is a wrong code, not a traceback
        keys.unwrap({**doc, "nonce": "not base64!"}, code="x")
    assert e.value.text == copy.RECOVERY_CODE_WRONG


def test_backup_key_is_made_once_and_the_escrow_gets_it(memory_keyring):
    escrow = RecordingEscrow()
    first = keys.ensure_backup_key(escrow)
    assert keys.ensure_backup_key(escrow) == first and escrow.puts == [first]
    assert memory_keyring.store[(SERVICE, "backup-key")] == first.hex()


def test_a_new_computer_takes_the_escrow_key(bk):
    escrow = RecordingEscrow(held=bk)
    assert keys.ensure_backup_key(escrow) == bk and escrow.puts == []
    assert keys.backup_key() == bk


def test_an_escrow_that_fails_never_blocks():
    made = keys.ensure_backup_key(DownEscrow())
    assert keys.backup_key() == made


def test_adopt_wraps_every_key_file_again(tmp_path, data_dir, bk, memory_keyring):
    old = keys.ensure_backup_key()
    local = data_dir / "projects" / ("a" * 32)
    folder = tmp_path / "usb" / "QS Mind One Backup" / ("a" * 32)
    for place in (local, folder):
        place.mkdir(parents=True)
        keys.write_doc(
            place / keys.KEY_FILE, keys.wrap(b"k" * 32, project_id="a" * 32, backup_key=old)
        )
    secret = data_dir / "projects" / ("c" * 32)
    secret.mkdir(parents=True)
    code_doc = keys.wrap_with_code(b"s" * 32, project_id="c" * 32, code=keys.new_recovery_code())
    keys.write_doc(secret / keys.KEY_FILE, code_doc)

    assert keys.adopt_backup_key(bk, data_dir, tmp_path / "usb") == 2
    assert keys.backup_key() == bk
    for place in (local, folder):
        doc = keys.read_doc(place / keys.KEY_FILE)
        assert keys.unwrap(doc, backup_key=bk) == b"k" * 32
        with pytest.raises(BackupError):
            keys.unwrap(doc, backup_key=old)
    assert keys.read_doc(secret / keys.KEY_FILE) == code_doc  # a code wrap is left alone
    assert (SERVICE, f"backup-key:{keys.key_id(old)}") not in memory_keyring.store  # done


def test_adopt_keeps_the_old_key_until_every_file_is_done(
    data_dir, bk, memory_keyring, monkeypatch
):
    old = keys.ensure_backup_key()
    local = data_dir / "projects" / ("a" * 32)
    local.mkdir(parents=True)
    keys.write_doc(local / keys.KEY_FILE, keys.wrap(b"k" * 32, project_id="a" * 32, backup_key=old))
    monkeypatch.setattr(keys, "write_doc", lambda path, doc: (_ for _ in ()).throw(OSError()))
    assert keys.adopt_backup_key(bk, data_dir, None) == 0
    assert keys.known_key(keys.key_id(old)) == old  # still here, by its id
