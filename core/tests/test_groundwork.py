"""Plan 8 groundwork: one version, /about, hashed locks, the journey texts and the test fakes."""

import base64
import hashlib
import json
import re
import tomllib
import webbrowser
from pathlib import Path

import httpx
import jwt
import pytest
from fastapi.testclient import TestClient

import qsone
from qsone import copy
from qsone.app import create_app
from tests.conftest import AUTH, SECRET

ROOT = Path(__file__).parents[2]
CORE = Path(__file__).parents[1]


@pytest.fixture
def client(data_dir):
    with TestClient(create_app(SECRET, data_dir=data_dir)) as client:
        yield client


def test_one_version_everywhere():
    v = qsone.__version__
    assert v == "0.1.0"
    assert json.loads((ROOT / "package.json").read_text())["version"] == v
    lock = json.loads((ROOT / "package-lock.json").read_text())
    assert lock["version"] == v and lock["packages"][""]["version"] == v
    assert json.loads((ROOT / "desktop/tauri.conf.json").read_text())["version"] == v
    assert tomllib.loads((CORE / "pyproject.toml").read_text())["project"]["version"] == v
    cargo = (ROOT / "desktop/Cargo.toml").read_text()
    assert re.search(r'^version = "([^"]+)"', cargo, re.M)[1] == v
    cargo_lock = (ROOT / "desktop/Cargo.lock").read_text()
    assert f'name = "qs-mind-one"\nversion = "{v}"' in cargo_lock


def test_about_says_version_and_mode(client, monkeypatch):
    assert client.get("/about").status_code == 401
    assert client.get("/about", headers=AUTH).json() == {
        "version": qsone.__version__,
        "release": False,
    }
    monkeypatch.setenv("QSONE_RELEASE", "1")
    assert client.get("/about", headers=AUTH).json()["release"] is True


def test_native_libraries_load(client):
    found = client.get("/about/native", headers=AUTH).json()
    assert found["sqlcipher"].startswith("4.") and found["sqlite_vec"] and found["keyring_backend"]
    assert found["pdfium"] and found["cryptography"] and found["tokenizers"]
    assert found["wasmtime"] and found["typst"]
    assert "onnxruntime" in found  # null on an Intel Mac, which has no wheel


def test_locks_have_hashes_and_the_runtime_has_no_dev_tools():
    for name in ("requirements.lock", "runtime.lock"):
        text = (CORE / name).read_text()
        pins = re.findall(r"^([a-z0-9][a-z0-9._-]*)==", text, re.M | re.I)
        assert pins, name
        # every pinned package carries its hashes
        blocks = re.split(r"^(?=[a-z0-9][a-z0-9._-]*==)", text, flags=re.M | re.I)[1:]
        assert all("--hash=sha256:" in block for block in blocks), name
    runtime = (CORE / "runtime.lock").read_text()
    for dev in ("pytest==", "ruff==", "xlwt=="):
        assert dev not in runtime
    for direct in ("pyjwt==", "cryptography==", "httpx==", "truststore=="):
        assert direct in runtime


def test_direct_dependencies_are_named():
    deps = tomllib.loads((CORE / "pyproject.toml").read_text())["project"]["dependencies"]
    names = {re.split(r"[\s\[<>=;!~]", d, maxsplit=1)[0].lower() for d in deps}
    assert {"pyjwt", "cryptography", "httpx", "truststore"} <= names


NEW_TEXTS = [
    "PROJECT_ARCHIVED",
    "AI_CONSENT_NEEDED",
    "ACCOUNT_OFFLINE",
    "ACCOUNT_REFUSED",
    "ACCOUNT_DENIED",
    "ACCOUNT_EXPIRED",
    "ACCOUNT_KEY_STORE_DOWN",
    "BACKUP_FOLDER_UNREACHABLE",
    "BACKUP_FOLDER_NOT_WRITABLE",
    "BACKUP_KEY_WRONG",
    "BACKUP_NEEDS_SIGN_IN",
    "BACKUP_NEEDS_CODE",
    "RECOVERY_CODE_WRONG",
    "RECOVERY_LAST_GROUP_WRONG",
    "PROJECT_KEY_RESTORED",
    "ZIP_TOO_BIG",
    "ZIP_UNSAFE",
    "FACT_NEEDS_SOURCE",
    "FACT_FILE_UNKNOWN",
    "COUNT_NEEDS_TRACE",
    "CLAUDE_CODE_NOT_FOUND",
    "UPDATE_FAILED",
    "UPDATE_OFFLINE",
]


def blanks(text: str) -> set[str]:
    return set(re.findall(r"\{(\w+)\}", text))


def test_every_new_text_has_both_languages():
    for name in NEW_TEXTS:
        text = getattr(copy, name)
        assert set(text) == {"en", "ar"}, name
        assert text["en"].strip() and text["ar"].strip(), name
        assert blanks(text["en"]) == blanks(text["ar"]), name
        assert re.search(r"[؀-ۿ]", text["ar"]), name
    assert blanks(copy.BACKUP_FOLDER_UNREACHABLE["en"]) == {"date"}
    assert blanks(copy.FACT_FILE_UNKNOWN["en"]) == {"file_id"}


def test_fake_account_signs_tokens_and_guards_the_vault(fake_account):
    meta = fake_account.get("/.well-known/openid-configuration")
    assert meta["issuer"] == fake_account.issuer
    assert fake_account.put_vault("one-backup-key", "x", scope="openid").status_code == 403
    assert fake_account.put_vault("one-backup-key", "x").status_code == 200
    assert fake_account.vault == {"one-backup-key": "x"}
    assert fake_account.put_vault("one-backup-key", "x" * 4097).status_code == 413


def pkce() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(b"v" * 40).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
    return verifier, challenge.rstrip(b"=").decode()


def test_fake_account_code_flow_with_pkce_and_rotating_refresh(fake_account, serve_app):
    got: dict = {}

    async def loopback(scope, receive, send):  # the app's loopback page, at its simplest
        got.update(dict(httpx.QueryParams(scope["query_string"].decode())))
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    redirect = serve_app(loopback) + "/callback"
    meta = fake_account.get("/.well-known/openid-configuration")
    verifier, challenge = pkce()
    url = httpx.URL(meta["authorization_endpoint"]).copy_merge_params(
        {
            "response_type": "code",
            "client_id": fake_account.client_id,
            "redirect_uri": redirect,
            "scope": "openid profile email offline_access vault",
            "state": "st",
            "nonce": "nn",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )
    webbrowser.open(str(url))  # recorded by no_browser, never opened
    assert fake_account.approve_last().status_code == 200
    assert got["state"] == "st"

    token = meta["token_endpoint"]
    form = {
        "grant_type": "authorization_code",
        "code": got["code"],
        "redirect_uri": redirect,
        "client_id": fake_account.client_id,
    }
    assert httpx.post(token, data=form | {"code_verifier": "wrong"}).status_code == 400
    tokens = httpx.post(token, data=form | {"code_verifier": verifier}).json()
    jwks = jwt.PyJWKClient(meta["jwks_uri"])
    key = jwks.get_signing_key_from_jwt(tokens["id_token"]).key
    claims = jwt.decode(
        tokens["id_token"], key, ["RS256"], audience=fake_account.client_id, issuer=meta["issuer"]
    )
    assert claims["nonce"] == "nn" and claims["email"] == fake_account.user["email"]

    refresh = {"grant_type": "refresh_token", "client_id": fake_account.client_id}
    first = tokens["refresh_token"]
    second = httpx.post(token, data=refresh | {"refresh_token": first}).json()["refresh_token"]
    assert second != first
    reused = httpx.post(token, data=refresh | {"refresh_token": first})
    assert reused.status_code == 400 and reused.json()["error"] == "invalid_grant"

    fake_account.revoked = True
    gone = httpx.post(token, data=refresh | {"refresh_token": second})
    assert gone.json()["error"] == "invalid_grant"


def test_fake_account_device_flow_and_switches(fake_account):
    meta = fake_account.get("/.well-known/openid-configuration")
    device = httpx.post(
        meta["device_authorization_endpoint"],
        data={"client_id": fake_account.client_id, "scope": "openid vault"},
    ).json()
    grant = {
        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        "device_code": device["device_code"],
        "client_id": fake_account.client_id,
    }
    token = meta["token_endpoint"]
    assert httpx.post(token, data=grant).json()["error"] == "authorization_pending"
    fake_account.approve_device(device["user_code"])
    assert "access_token" in httpx.post(token, data=grant).json()

    fake_account.down = True
    with pytest.raises(httpx.ConnectError):
        httpx.get(fake_account.issuer + "/.well-known/openid-configuration")
    fake_account.down = False
    assert fake_account.get("/.well-known/openid-configuration")["issuer"]


def test_fake_umami_records_events_and_refuses_bots(fake_umami):
    event = {"type": "event", "payload": {"website": "w", "name": "app_start", "data": {}}}
    ua = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) QSMindOne/0.1.0"}
    assert httpx.post(fake_umami.endpoint, json=event, headers=ua).status_code == 200
    httpx.post(fake_umami.endpoint, json=event, headers={"User-Agent": "python-httpx/0.28.1"})
    httpx.post(fake_umami.endpoint, json=event, headers={"User-Agent": "QSMindOne/0.1.0"})
    assert fake_umami.received == [event]
    assert fake_umami.agents == [ua["User-Agent"]]


def test_the_journey_fixtures_stand_in(fake_account, fake_umami, no_browser):
    import os

    assert os.environ["QSONE_AUTH_ISSUER"] == fake_account.issuer
    assert os.environ["QSONE_AUTH_CLIENT_ID"] == fake_account.client_id
    assert os.environ["QSONE_USAGE_ENDPOINT"] == fake_umami.endpoint
    webbrowser.open("https://qsmind.app/ar/one/terms")
    assert no_browser == ["https://qsmind.app/ar/one/terms"]


def test_scrypt_is_fast_in_tests():
    # fast_scrypt (autouse) caps n at 2**10, so a recovery code costs milliseconds here
    a = hashlib.scrypt(b"code", salt=b"s" * 16, n=2**17, r=8, p=1, maxmem=256 * 1024**2, dklen=32)
    b = hashlib.scrypt(b"code", salt=b"s" * 16, n=2**10, r=8, p=1, dklen=32)
    assert a == b
