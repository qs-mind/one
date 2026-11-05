"""The QS Mind account and its key vault (Plan 8, Task 5). The account is `FakeAccount` on
127.0.0.1, the key store is in memory and the browser is `no_browser`: no test reaches the real
account, the real key store or a real browser."""

import json
import logging
import threading
import time
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlencode, urlparse

import httpx
import pytest
from fastapi.testclient import TestClient

from qsone import copy, settings
from qsone.account import oidc, session
from qsone.account import vault as account_vault
from qsone.account.session import Account, AccountError
from qsone.app import create_app
from qsone.backup import keys
from qsone.backup.runner import Backups
from qsone.keys import SERVICE
from qsone.projects import Projects
from qsone.records import vault
from qsone.records.files import add_file
from tests.conftest import AUTH, SECRET
from tests.samples import sample_xlsx


def wait_until(check, timeout: float = 10.0):
    deadline = time.monotonic() + timeout
    while True:
        found = check()
        if found:
            return found
        assert time.monotonic() < deadline, "timed out"
        time.sleep(0.02)


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 11, 5, 8, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **delta) -> None:
        self.now += timedelta(**delta)


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def account(fake_account, data_dir, clock):
    a = Account(clock=clock)
    a.on_signed_in = lambda: account_vault.settle_backup_key(a.escrow(), data_dir)
    yield a
    a.close()


@pytest.fixture
def projects(data_dir, account):
    registry = Projects(data_dir)
    registry.backups = Backups(data_dir, registry, escrow_factory=account.escrow)
    yield registry
    registry.close_all()


def sign_in(fake_account, account, locale: str = "en") -> None:
    account.sign_in(locale)
    fake_account.approve_last()
    wait_until(lambda: account.state()["state"] == "signed_in")


def stored(memory_keyring, user: str) -> str | None:
    return memory_keyring.store.get((SERVICE, user))


def refresh_posts(fake_account) -> int:
    return fake_account.requests.count(("POST", "/oauth/token"))


def test_browser_sign_in_end_to_end(fake_account, account, memory_keyring, data_dir):
    answer = account.sign_in("ar")
    assert answer["state"] == "waiting" and fake_account.opened == [answer["url"]]
    query = parse_qs(urlparse(answer["url"]).query)
    assert query["scope"] == ["openid profile email offline_access vault"]
    assert query["code_challenge_method"] == ["S256"] and query["code_challenge"][0]
    assert query["state"][0] and query["nonce"][0] and query["ui_locales"] == ["ar"]
    assert urlparse(query["redirect_uri"][0]).hostname == "127.0.0.1"
    assert account.state()["state"] == "waiting"

    page = fake_account.approve_last()  # what the browser shows when it comes back
    assert page.status_code == 200
    assert copy.ACCOUNT_SIGNED_IN["ar"] in page.text and copy.ACCOUNT_SIGNED_IN["en"] in page.text
    assert page.text.index(copy.ACCOUNT_SIGNED_IN["ar"]) < page.text.index("Signed in.")
    assert "<script" not in page.text and "#F9F8F4" in page.text
    assert "default-src 'none'" in page.headers["content-security-policy"]

    wait_until(lambda: account.state()["state"] == "signed_in")
    state = account.state()
    assert state["email"] == fake_account.user["email"]
    assert state["name"] == fake_account.user["name"]
    assert settings.load()["signed_in"] is True
    saved = (data_dir / "settings.json").read_text(encoding="utf-8")
    assert "refresh" not in saved and fake_account.user["email"] not in saved
    token = stored(memory_keyring, session.REFRESH_USER)
    assert token and token not in saved
    assert json.loads(stored(memory_keyring, session.PROFILE_USER))["sub"] == "user-0001"


def test_device_sign_in_when_the_browser_cannot_come_back(fake_account, account):
    answer = account.sign_in("en", device=True)
    device = answer["device"]
    assert answer["state"] == "waiting" and device["user_code"] and device["verification_uri"]
    assert fake_account.opened == [answer["url"]] and device["user_code"] in answer["url"]
    assert account.state()["device"] == device
    fake_account.approve_device(device["user_code"])
    wait_until(lambda: account.state()["state"] == "signed_in")
    assert account.state()["email"] == fake_account.user["email"]


def test_device_sign_in_denied_or_expired_says_so(fake_account, account):
    fake_account.deny = True
    code = account.sign_in("en", device=True)["device"]["user_code"]
    fake_account.approve_device(code)
    note = wait_until(lambda: account.state().get("note"))
    assert note == copy.ACCOUNT_DENIED and account.state()["state"] == "signed_out"

    fake_account.deny = False
    account.sign_in("en", device=True)
    fake_account.expire_devices()
    assert wait_until(lambda: account.state().get("note")) == copy.ACCOUNT_EXPIRED


def test_denied_in_the_browser_says_so(fake_account, account, memory_keyring):
    fake_account.deny = True
    account.sign_in("en")
    page = fake_account.approve_last()
    assert copy.ACCOUNT_DENIED["en"] in page.text
    state = wait_until(lambda: "note" in account.state() and account.state())
    assert state == {"state": "signed_out", "note": copy.ACCOUNT_DENIED}
    assert stored(memory_keyring, session.REFRESH_USER) is None


def test_a_redirect_for_another_sign_in_is_ignored(fake_account, account):
    account.sign_in("en")
    redirect = parse_qs(urlparse(fake_account.opened[-1]).query)["redirect_uri"][0]
    forged = httpx.get(f"{redirect}?{urlencode({'code': 'x', 'state': 'not-ours'})}", timeout=10)
    assert forged.status_code == 400
    assert account.state()["state"] == "waiting"  # still waiting for the real one
    fake_account.approve_last()
    wait_until(lambda: account.state()["state"] == "signed_in")


def test_nobody_came_back_in_time(fake_account, account, monkeypatch):
    monkeypatch.setattr(oidc, "SIGN_IN_SECONDS", 0.1)
    account.sign_in("en")
    assert wait_until(lambda: account.state().get("note")) == copy.ACCOUNT_EXPIRED
    assert account.state()["state"] == "signed_out"


def test_cancel_stops_the_sign_in(fake_account, account):
    account.sign_in("en")
    assert account.cancel() == {"state": "signed_out"}
    with pytest.raises(httpx.TransportError):  # the loopback stopped listening
        wait_until(lambda: fake_account.approve_last() and False, timeout=2)
    assert account.state()["state"] == "signed_out"


def test_first_sign_in_puts_the_backup_key_in_the_vault(fake_account, account):
    assert keys.backup_key() is None
    sign_in(fake_account, account)
    local = keys.backup_key()
    assert local is not None  # made for the vault
    assert list(fake_account.vault) == [account_vault.NAME]
    assert account_vault.decode(fake_account.vault[account_vault.NAME]) == local


def test_an_existing_local_backup_key_goes_to_the_vault(fake_account, account, projects):
    projects.create("برج - عينة", "engineer")  # makes the Backup key and the key.json
    local = keys.backup_key()
    sign_in(fake_account, account)
    assert keys.backup_key() == local
    assert account_vault.decode(fake_account.vault[account_vault.NAME]) == local


def test_sign_in_on_a_second_computer_adopts_the_vault_key(
    fake_account, account, projects, tmp_path, memory_keyring
):
    pid = projects.create("برج - عينة", "engineer")["id"]
    add_file(
        projects.get(pid),
        "جدول - عينة.xlsx",
        sample_xlsx({"BOQ": [["1", "حفر", "م3", 5]]}),
        actor="engineer",
    )
    folder = tmp_path / "usb"
    folder.mkdir()
    projects.backups.set_folder(str(folder))
    assert projects.backups.run(reason="manual") >= 1
    old = keys.backup_key()
    project_key = vault.get_key(pid)

    other = b"B" * 32  # the key the account already keeps, from the first computer
    assert (
        fake_account.put_vault(account_vault.NAME, account_vault.encode(other)).status_code == 200
    )
    sign_in(fake_account, account)

    assert keys.backup_key() == other
    local_doc = keys.read_doc(projects.root / pid / keys.KEY_FILE)
    backed_doc = keys.read_doc(folder / "QS Mind ONE Backup" / pid / keys.KEY_FILE)
    for doc in (local_doc, backed_doc):
        assert doc["key_id"] == keys.key_id(other)
        assert keys.unwrap(doc, backup_key=other) == project_key
        with pytest.raises(keys.BackupError):
            keys.unwrap(doc, backup_key=old)
    assert (SERVICE, f"backup-key:{keys.key_id(old)}") not in memory_keyring.store  # all done
    assert account_vault.decode(fake_account.vault[account_vault.NAME]) == other


def test_refresh_rotates_and_a_revoked_account_signs_out_here(
    fake_account, account, memory_keyring, clock
):
    sign_in(fake_account, account)
    first = stored(memory_keyring, session.REFRESH_USER)
    account.drop_access()
    assert account.access_token()
    second = stored(memory_keyring, session.REFRESH_USER)
    assert second and second != first  # rotated, and the new one kept

    posts = refresh_posts(fake_account)
    account.state()  # refreshed at sign-in: not again within the hour
    clock.advance(minutes=30)
    account.state()
    time.sleep(0.2)
    assert refresh_posts(fake_account) == posts
    clock.advance(minutes=31)
    account.state()
    account.state()
    wait_until(lambda: refresh_posts(fake_account) == posts + 1)
    time.sleep(0.2)
    assert refresh_posts(fake_account) == posts + 1  # once, though asked twice
    wait_until(lambda: stored(memory_keyring, session.REFRESH_USER) != second)

    fake_account.revoked = True  # signed out everywhere, from the account's page
    clock.advance(hours=2)
    account.state()
    state = wait_until(lambda: account.state()["state"] == "signed_out" and account.state())
    assert state["note"] == copy.ACCOUNT_REFUSED
    assert stored(memory_keyring, session.REFRESH_USER) is None
    assert stored(memory_keyring, session.PROFILE_USER) is None
    assert "signed_in" not in settings.load()


def test_two_refreshes_never_spend_the_same_token(fake_account, account):
    sign_in(fake_account, account)
    account.drop_access()
    found: list[str | None] = []
    threads = [
        threading.Thread(target=lambda: found.append(account.access_token())) for _ in range(4)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert all(found) and len(set(found)) == 1
    assert account.state()["state"] == "signed_in"


def test_offline_keeps_the_state_and_says_so(fake_account, account, clock):
    sign_in(fake_account, account)
    fake_account.down = True
    clock.advance(hours=2)
    account.state()
    assert wait_until(lambda: account.state().get("note")) == copy.ACCOUNT_OFFLINE
    state = account.state()
    assert state["state"] == "signed_in" and state["email"] == fake_account.user["email"]

    fake_account.down = False  # back online: tried again five minutes later
    clock.advance(minutes=6)
    account.state()
    wait_until(lambda: "note" not in account.state())
    assert account.state()["state"] == "signed_in"


def test_offline_sign_in_says_so(fake_account, account):
    fake_account.down = True
    with pytest.raises(AccountError) as e:
        account.sign_in("en")
    assert e.value.text == copy.ACCOUNT_OFFLINE and e.value.status == 503
    assert account.state()["state"] == "signed_out"


def test_id_token_from_another_issuer_is_refused(fake_account, account, memory_keyring):
    fake_account.token_issuer = "https://not-the-account.example"
    account.sign_in("en")
    page = fake_account.approve_last()
    assert copy.ACCOUNT_REFUSED["en"] in page.text
    assert wait_until(lambda: account.state().get("note")) == copy.ACCOUNT_REFUSED
    assert account.state()["state"] == "signed_out"
    assert stored(memory_keyring, session.REFRESH_USER) is None
    assert fake_account.vault == {}


def test_the_issuer_must_be_https():
    with pytest.raises(ValueError):
        oidc.Client("one", "http://auth.example.com")
    oidc.Client("one", "https://auth.example.com").close()
    oidc.Client("one", "http://127.0.0.1:9").close()


def test_the_key_store_down_at_sign_in_says_so(fake_account, account, failing_keyring):
    account.sign_in("en")
    fake_account.approve_last()
    note = wait_until(lambda: account.state().get("note"))
    assert note == copy.ACCOUNT_KEY_STORE_DOWN and account.state()["state"] == "signed_out"
    assert "signed_in" not in settings.load()
    wait_until(lambda: len(fake_account.revocations) == 1)  # the token it could not keep


def test_vault_never_gets_a_project_key(fake_account, account, projects, tmp_path):
    sign_in(fake_account, account)
    plain = projects.create("برج - عينة", "engineer")["id"]
    secret = projects.create("فيلا - عينة", "engineer")["id"]
    projects.backups.set_confidential(secret, True)
    folder = tmp_path / "usb"
    folder.mkdir()
    projects.backups.set_folder(str(folder))
    projects.backups.run(reason="manual")

    assert list(fake_account.vault) == [account_vault.NAME]  # exactly one value: the Backup key
    value = fake_account.vault[account_vault.NAME]
    assert account_vault.decode(value) == keys.backup_key()
    for pid in (plain, secret):
        key = vault.get_key(pid)
        assert key.hex() not in value and key.hex().upper() not in value
        import base64

        assert base64.b64encode(key).decode() not in value


def test_sign_out_revokes_and_forgets(fake_account, account, memory_keyring):
    sign_in(fake_account, account)
    token = stored(memory_keyring, session.REFRESH_USER)
    local = keys.backup_key()
    assert account.sign_out() == {"state": "signed_out"}
    assert token in fake_account.revocations
    assert stored(memory_keyring, session.REFRESH_USER) is None
    assert stored(memory_keyring, session.PROFILE_USER) is None
    assert "signed_in" not in settings.load()
    assert keys.backup_key() == local  # the Backup key stays here
    assert account_vault.NAME in fake_account.vault  # and the vault keeps its copy
    assert account.escrow() is None and account.access_token() is None


def test_sign_out_offline_still_forgets(fake_account, account, memory_keyring):
    sign_in(fake_account, account)
    fake_account.down = True
    assert account.sign_out() == {"state": "signed_out"}
    assert stored(memory_keyring, session.REFRESH_USER) is None


def test_the_vault_offline_is_never_taken_for_empty(fake_account, account):
    sign_in(fake_account, account)
    escrow = account.escrow()
    fake_account.down = True
    escrow._known = None  # nothing remembered from the sign-in
    with pytest.raises(account_vault.VaultError):
        escrow.get()


def test_a_vault_value_that_is_not_a_backup_key_is_refused():
    good = account_vault.encode(b"k" * 32)
    assert account_vault.decode(good) == b"k" * 32
    doc = json.loads(good)
    for bad in ("x", "{}", json.dumps(doc | {"key_id": "0" * 16}), json.dumps(doc | {"v": 2})):
        with pytest.raises(account_vault.VaultError):
            account_vault.decode(bad)


def test_nothing_secret_in_the_log(fake_account, account, memory_keyring, caplog, clock):
    caplog.set_level(logging.DEBUG)
    sign_in(fake_account, account)
    token = stored(memory_keyring, session.REFRESH_USER)
    access = account.access_token()
    account.drop_access()
    account.access_token()
    account.sign_out()
    for secret in (token, access, fake_account.user["email"], fake_account.user["name"]):
        assert secret not in caplog.text


@pytest.fixture
def client(fake_account, data_dir):
    with TestClient(create_app(SECRET, data_dir=data_dir)) as c:
        yield c


def test_routes(client, fake_account, memory_keyring):
    assert client.get("/account").status_code == 401  # the secret, as every route
    assert client.get("/account", headers=AUTH).json() == {"state": "signed_out"}
    assert client.post("/account/sign-in", json={"locale": "xx"}, headers=AUTH).status_code == 422

    answer = client.post("/account/sign-in", json={"locale": "en", "device": False}, headers=AUTH)
    assert answer.status_code == 200 and answer.headers["cache-control"] == "no-store"
    assert answer.json() == {"state": "waiting", "url": fake_account.opened[-1]}
    fake_account.approve_last()
    signed_in = wait_until(
        lambda: (a := client.get("/account", headers=AUTH).json())["state"] == "signed_in" and a
    )
    assert signed_in == {
        "state": "signed_in",
        "email": fake_account.user["email"],
        "name": fake_account.user["name"],
    }
    token = stored(memory_keyring, session.REFRESH_USER)
    backup = client.get("/backup", headers=AUTH).json()
    assert backup["backup_key"] == {"local": True, "in_account": True, "code_saved": False}

    answers = [
        client.get("/account", headers=AUTH),
        client.post("/account/cancel", headers=AUTH),
        client.delete("/account", headers=AUTH),
    ]
    for a in answers:
        assert token not in a.text and "access_token" not in a.text
    assert answers[1].json()["state"] == "signed_in"  # nothing to cancel
    assert answers[2].json() == {"state": "signed_out"}
    assert client.get("/account", headers=AUTH).json() == {"state": "signed_out"}

    device = client.post("/account/sign-in", json={"locale": "ar", "device": True}, headers=AUTH)
    assert set(device.json()["device"]) == {"user_code", "verification_uri"}
    assert client.post("/account/cancel", headers=AUTH).json() == {"state": "signed_out"}


def test_a_build_without_a_client_id_says_sign_in_is_not_ready(client, monkeypatch):
    monkeypatch.delenv("QSONE_AUTH_CLIENT_ID")
    monkeypatch.setattr(oidc, "CLIENT_ID", "")
    answer = client.post("/account/sign-in", json={"locale": "en"}, headers=AUTH)
    assert answer.status_code == 503 and answer.json() == {"error": copy.ACCOUNT_UNAVAILABLE}
