import logging

from fastapi.testclient import TestClient

from qsone import keys
from qsone.app import create_app
from tests.conftest import AUTH, SECRET


def test_set_and_get_key_use_the_system_store(memory_keyring):
    assert keys.get_key("anthropic") is None
    keys.set_key("anthropic", "sk-ant-x")
    assert keys.get_key("anthropic") == "sk-ant-x"
    assert memory_keyring.store[("QS Mind One", "anthropic")] == "sk-ant-x"


def test_key_never_returned_or_logged(caplog):
    caplog.set_level(logging.DEBUG)
    client = TestClient(create_app(SECRET))
    assert client.get("/settings/ai-key", headers=AUTH).json() == {"set": False}
    r = client.put(
        "/settings/ai-key", json={"provider": "anthropic", "value": "sk-ant-x"}, headers=AUTH
    )
    assert r.status_code == 200 and "sk-ant-x" not in r.text
    assert client.get("/settings/ai-key", headers=AUTH).json() == {"set": True}
    assert "sk-ant-x" not in caplog.text


def test_bad_key_request_does_not_echo_the_key():
    client = TestClient(create_app(SECRET))
    r = client.put("/settings/ai-key", json={"provider": "nope", "value": "sk-ant-x"}, headers=AUTH)
    assert r.status_code == 422 and "sk-ant-x" not in r.text
    r = client.put("/settings/ai-key", json={"value": "sk-ant-x"}, headers=AUTH)
    assert r.status_code == 422 and "sk-ant-x" not in r.text
    r = client.put("/settings/ai-key", json={"provider": "anthropic", "value": "  "}, headers=AUTH)
    assert r.status_code == 422 and keys.get_key("anthropic") is None


def test_settings_need_the_secret():
    client = TestClient(create_app(SECRET))
    assert client.get("/settings/ai-key").status_code == 401
    r = client.put("/settings/ai-key", json={"provider": "anthropic", "value": "sk-ant-x"})
    assert r.status_code == 401
    assert keys.get_key("anthropic") is None
