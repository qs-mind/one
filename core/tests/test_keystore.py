"""The key file used when the computer has no key store. Fakes only: never the real key store."""

import json
import logging
import os
import stat

import keyring
import pytest
from fastapi.testclient import TestClient
from keyring.backend import KeyringBackend
from keyring.backends import chainer, fail
from keyring.errors import KeyringError, PasswordDeleteError

from qsone import __main__ as entry
from qsone import about, keys, keystore, settings
from qsone.app import create_app
from qsone.records import vault
from tests.conftest import AUTH, SECRET, MemoryKeyring

VALUE = "sk-ant-sample-never-logged"  # a sample, not a real key
posix_only = pytest.mark.skipif(os.name != "posix", reason="file modes are POSIX only")


@pytest.fixture
def no_key_store():
    keyring.set_keyring(fail.Keyring())  # the conftest fixture restores the memory keyring


def key_file(data_dir):
    return data_dir / keystore.FILE_NAME


def test_no_key_store_means_the_key_file(no_key_store, data_dir):
    assert keystore.choose() == "file"
    assert isinstance(keyring.get_keyring(), keystore.FileKeyring)
    assert keystore.kind() == "file"
    assert settings.load()["key_store"] == "file"
    assert about.native()["keyring_backend"] == "qsone.keystore.FileKeyring"


def test_an_empty_chainer_or_a_broken_priority_is_no_key_store():
    class Broken(MemoryKeyring):
        @property
        def priority(self):
            raise RuntimeError("The Secret Service daemon is neither running nor activatable")

    empty = type("EmptyChainer", (chainer.ChainerBackend,), {"backends": []})()
    assert not keystore.usable(empty)
    assert not keystore.usable(Broken())
    assert not keystore.usable(fail.Keyring())
    assert keystore.usable(MemoryKeyring())


def test_a_key_store_keeps_the_system_one_and_writes_nothing(memory_keyring, data_dir):
    assert keystore.choose() == "system"
    assert keyring.get_keyring() is memory_keyring
    assert keystore.kind() == "system"
    assert "key_store" not in settings.load()
    assert not key_file(data_dir).exists()


def test_values_round_trip(no_key_store, data_dir):
    keystore.choose()
    keys.set_key("anthropic", VALUE)
    keys.set_key("brave", "sample-search-key")
    assert keys.get_key("anthropic") == VALUE
    keys.delete_key("brave")
    assert keys.get_key("brave") is None
    keys.delete_key("brave")  # gone already: nothing happens
    with pytest.raises(PasswordDeleteError):
        keyring.delete_password(keys.SERVICE, "brave")
    saved = json.loads(key_file(data_dir).read_text(encoding="utf-8"))
    assert saved == {"version": 1, "keys": {keys.SERVICE: {"anthropic": VALUE}}}


@posix_only
def test_folder_and_file_are_private(no_key_store, data_dir):
    keystore.choose()
    keys.set_key("anthropic", VALUE)
    assert stat.S_IMODE(os.stat(data_dir).st_mode) == 0o700
    assert stat.S_IMODE(os.stat(key_file(data_dir)).st_mode) == 0o600


@posix_only
def test_a_file_copied_in_by_hand_is_made_private(no_key_store, data_dir):
    data_dir.mkdir(parents=True)
    key_file(data_dir).write_text('{"version": 1, "keys": {}}', encoding="utf-8")
    os.chmod(key_file(data_dir), 0o644)
    keystore.choose()
    assert stat.S_IMODE(os.stat(key_file(data_dir)).st_mode) == 0o600


@pytest.mark.parametrize("crash_in", ["fsync", "replace"])
def test_a_crash_mid_write_keeps_the_old_file(no_key_store, data_dir, monkeypatch, crash_in):
    keystore.choose()
    keys.set_key("anthropic", VALUE)
    before = key_file(data_dir).read_bytes()

    def crash(*args):
        raise OSError("power cut (simulated)")

    monkeypatch.setattr(keystore.os, crash_in, crash)
    with pytest.raises(KeyringError):
        keys.set_key("anthropic", "a-newer-sample")
    monkeypatch.undo()
    assert key_file(data_dir).read_bytes() == before
    assert keys.get_key("anthropic") == VALUE
    assert [p.name for p in data_dir.iterdir() if p.suffix == ".tmp"] == []


def test_a_damaged_file_is_never_written_over(no_key_store, data_dir):
    data_dir.mkdir(parents=True)
    key_file(data_dir).write_text('{"version": 1, "keys": {"QS Mind One": {"an', encoding="utf-8")
    keystore.choose()
    with pytest.raises(KeyringError) as raised:
        keyring.set_password(keys.SERVICE, "anthropic", VALUE)
    assert "QS Mind One" not in str(raised.value)
    assert key_file(data_dir).read_text(encoding="utf-8").endswith('"an')
    assert keys.get_key("anthropic") is None  # read as missing, as when a key store is down


def test_no_value_is_logged(no_key_store, data_dir, caplog):
    caplog.set_level(logging.DEBUG)
    keystore.choose()
    keys.set_key("anthropic", VALUE)
    keys.get_key("anthropic")
    keyring.set_keyring(MemoryKeyring())
    keystore.choose()  # moves the key
    assert VALUE not in caplog.text
    assert "keyring.backends.fail.Keyring" in caplog.text
    assert keystore.FILE_NAME in caplog.text


def test_projects_and_ai_keys_work_on_the_key_file(no_key_store, data_dir):
    keystore.choose()
    with TestClient(create_app(SECRET, data_dir=data_dir)) as client:
        r = client.post("/projects", json={"name": "مدرسة - عينة"}, headers=AUTH)
        assert r.status_code == 201
        pid = r.json()["id"]
        assert client.post(f"/projects/{pid}/close", headers=AUTH).status_code == 200
        assert client.post(f"/projects/{pid}/open", headers=AUTH).status_code == 200
        r = client.put(
            "/settings/ai-key", json={"provider": "anthropic", "value": VALUE}, headers=AUTH
        )
        assert r.status_code == 200 and VALUE not in r.text
        assert client.get("/settings/ai-key", headers=AUTH).json() == {"set": True}
        assert client.get("/settings/ai", headers=AUTH).json()["key_store"] == "file"
    assert vault.get_key(pid) is not None
    assert keys.SERVICE in json.loads(key_file(data_dir).read_text(encoding="utf-8"))["keys"]


def test_settings_say_system_with_a_key_store(data_dir):
    with TestClient(create_app(SECRET, data_dir=data_dir)) as client:
        assert client.get("/settings/ai", headers=AUTH).json()["key_store"] == "system"


def test_the_core_chooses_before_the_app_is_built(no_key_store, tmp_path, monkeypatch):
    seen = {}

    def fake_create_app(secret, **kwargs):
        seen["store"] = keystore.kind()
        return create_app(secret, **kwargs)

    class FakeServer:
        def __init__(self, config):
            pass

        def run(self):
            pass

    monkeypatch.setenv("QSONE_SECRET", SECRET)
    monkeypatch.setattr(entry, "create_app", fake_create_app)
    monkeypatch.setattr(entry.uvicorn, "Server", FakeServer)
    entry.main(["--port", "0", "--data-dir", str(tmp_path / "elsewhere")])
    assert seen == {"store": "file"}
    assert (
        json.loads((tmp_path / "elsewhere" / "settings.json").read_text(encoding="utf-8"))[
            "key_store"
        ]
        == "file"
    )


def test_a_key_store_that_appears_later_gets_every_key(no_key_store, data_dir):
    keystore.choose()
    keys.set_key("anthropic", VALUE)
    pid = "a" * 32
    project_key = vault.create_key(pid)
    system = MemoryKeyring()
    system.store[(keys.SERVICE, "anthropic")] = "an-older-sample"  # the file's value is newer
    keyring.set_keyring(system)

    assert keystore.choose() == "system"
    assert keyring.get_keyring() is system
    assert system.store == {
        (keys.SERVICE, "anthropic"): VALUE,
        (keys.SERVICE, f"project:{pid}"): project_key.hex(),
    }
    assert not key_file(data_dir).exists()
    assert settings.load()["key_store"] == "system"
    assert vault.get_key(pid) == project_key


def test_a_move_that_fails_keeps_the_key_file(no_key_store, data_dir):
    keystore.choose()
    keys.set_key("anthropic", VALUE)

    class Forgetful(MemoryKeyring):
        def get_password(self, service, username):
            return None  # never reads back what was set

    keyring.set_keyring(Forgetful())
    assert keystore.choose() == "file"
    assert isinstance(keyring.get_keyring(), keystore.FileKeyring)
    assert key_file(data_dir).exists()
    assert settings.load()["key_store"] == "file"
    assert keys.get_key("anthropic") == VALUE


def test_a_key_store_that_refuses_keeps_the_key_file(no_key_store, data_dir):
    keystore.choose()
    keys.set_key("anthropic", VALUE)

    class Locked(KeyringBackend):
        priority = 1

        def get_password(self, service, username):
            raise KeyringError("locked")

        def set_password(self, service, username, password):
            raise KeyringError("locked")

        def delete_password(self, service, username):
            raise KeyringError("locked")

    keyring.set_keyring(Locked())
    assert keystore.choose() == "file"
    assert keys.get_key("anthropic") == VALUE
