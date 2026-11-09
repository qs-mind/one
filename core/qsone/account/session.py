"""The engineer's QS Mind account on this computer (decision 7).

- The refresh token and the profile (sub, email, name) live in the key store only, as
  "account-refresh-token" and "account-profile". settings.json keeps only `signed_in: true`, so a
  signed-out engineer's key store is never touched. The access token stays in memory.
- Refresh tokens rotate: the new one replaces the old in the key store. Refreshes are one at a
  time, so two never spend the same token.
- While the screen asks (`state()`), One refreshes at most once an hour (five minutes after a try
  that failed), in the background: the answer is the state before that refresh.
- A refusal from the account (signed out elsewhere, account disabled) signs out here. Offline
  keeps the state and says so (ACCOUNT_OFFLINE).
- Signing out revokes the refresh token and deletes it and the profile from the key store. The
  Backup key stays on this computer, and the vault keeps its copy.
- After a sign-in succeeds, `on_signed_in` runs before the state turns to signed_in (the app
  gives the Backup key to the vault, or adopts the vault's). It runs again after a later refresh
  if it failed. It is called without this object's lock held: it takes the Backups lock, and a
  backup run takes this lock through the escrow, so holding both the other way round would
  deadlock.

Never log a token, an email or a name.
"""

import json
import logging
import threading
import webbrowser
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import keyring
from keyring.errors import KeyringError, PasswordDeleteError

from qsone import copy, settings
from qsone.account import oidc
from qsone.account.vault import AccountEscrow
from qsone.keys import SERVICE
from qsone.records.project import RecordsError

log = logging.getLogger(__name__)

REFRESH_USER = "account-refresh-token"
PROFILE_USER = "account-profile"
SETTING = "signed_in"
REFRESH_EVERY = timedelta(hours=1)
RETRY_AFTER = timedelta(minutes=5)
ACCESS_MARGIN = timedelta(seconds=60)  # an access token this close to its end is refreshed


class AccountError(RecordsError):
    """A refusal the engineer can read; `text` is from `copy`."""


def _code(error: Exception) -> str:
    """What a log line may say about an account error: an OAuth code or a class name."""
    return error.code if isinstance(error, oidc.Refused) else type(error).__name__


class Account:
    def __init__(
        self,
        on_signed_in: Callable[[], None] | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.on_signed_in = on_signed_in
        self.clock = clock
        self._lock = threading.RLock()
        self._refresh_lock = threading.Lock()  # one refresh at a time: tokens rotate
        self._client: oidc.Client | None = None
        self._attempt = 0  # each sign-in, cancel and sign-out counts on: late answers are dropped
        self._pending: dict | None = None  # the sign-in under way: {"url", "device"?}
        self._cancel: Callable[[], None] | None = None
        self._note: dict[str, str] | None = None  # why the last sign-in or refresh failed
        self._cached: tuple[str, dict] | None = None  # (refresh token, profile) once read
        self._access: tuple[str, datetime] | None = None  # (access token, good until)
        self._checked_at: datetime | None = None  # the last refresh try
        self._failed = False  # that try failed (offline)
        self._refreshing = False
        self._synced = False  # on_signed_in succeeded since the sign-in or this start
        self._escrow: AccountEscrow | None = None

    # The protocol client --------------------------------------------------------------------------

    def client(self) -> oidc.Client:
        """Raises `AccountError` (ACCOUNT_UNAVAILABLE) when this build has no client id yet."""
        with self._lock:
            if self._client is None:
                client_id = oidc.client_id()
                if not client_id:
                    raise AccountError(copy.ACCOUNT_UNAVAILABLE, status=503)
                self._client = oidc.Client(client_id, oidc.issuer())
            return self._client

    def close(self) -> None:
        """At core stop: a sign-in under way stops, and the HTTP client closes."""
        with self._lock:
            self._attempt += 1
            self._stop_pending()
            if self._client is not None:
                self._client.close()
                self._client = None

    # What is kept ---------------------------------------------------------------------------------

    def _load(self) -> tuple[str, dict] | None:
        """(refresh token, profile), or None when signed out. Raises `KeyringError`."""
        if settings.load().get(SETTING) is not True:
            return None
        if self._cached is None:
            token = keyring.get_password(SERVICE, REFRESH_USER)
            raw = keyring.get_password(SERVICE, PROFILE_USER)
            try:
                profile = json.loads(raw) if raw else None
            except ValueError:
                profile = None
            if not token or not isinstance(profile, dict) or not profile.get("sub"):
                return None
            self._cached = (token, profile)
        return self._cached

    def _keep(self, tokens: oidc.Tokens) -> None:
        """Raises `KeyringError`. A settings.json that cannot be written is logged: the session
        then lasts until the core stops."""
        assert tokens.refresh_token is not None
        keyring.set_password(SERVICE, REFRESH_USER, tokens.refresh_token)
        keyring.set_password(SERVICE, PROFILE_USER, json.dumps(tokens.profile))
        self._cached = (tokens.refresh_token, tokens.profile)
        self._access = (
            tokens.access_token,
            self.clock() + timedelta(seconds=tokens.expires_in) - ACCESS_MARGIN,
        )
        try:
            if settings.load().get(SETTING) is not True:
                settings.save(SETTING, True)
        except OSError as e:
            log.warning("settings.json not written (%s)", type(e).__name__)

    def _forget(self) -> None:
        """Signed out here: the token and the profile leave the key store; the Backup key stays."""
        self._cached = None
        self._access = None
        self._synced = False
        self._escrow = None
        for user in (REFRESH_USER, PROFILE_USER):
            try:
                keyring.delete_password(SERVICE, user)
            except PasswordDeleteError:
                pass
            except KeyringError as e:
                log.warning("The key store did not delete the account (%s)", type(e).__name__)
        try:
            settings.remove(SETTING)
        except OSError as e:
            log.warning("settings.json not written (%s)", type(e).__name__)

    def signed_in(self) -> bool:
        with self._lock:
            try:
                return self._load() is not None
            except KeyringError:
                return False

    # What the screen asks -------------------------------------------------------------------------

    def state(self) -> dict:
        """The GET /account answer: {"state", "email"?, "name"?, "url"?, "device"?, "note"?}.
        `note` ({en, ar}) says why the last sign-in or refresh failed."""
        self._refresh_if_due()
        with self._lock:
            if self._pending is not None:
                return {"state": "waiting", **self._pending}
            try:
                loaded = self._load()
            except KeyringError:
                return {"state": "signed_out", "note": copy.ACCOUNT_KEY_STORE_DOWN}
            if loaded is None:
                answer = {"state": "signed_out"}
            else:
                profile = loaded[1]
                answer = {
                    "state": "signed_in",
                    "email": profile.get("email"),
                    "name": profile.get("name"),
                }
            if self._note is not None:
                answer["note"] = self._note
            return answer

    def sign_in(self, locale: str, device: bool = False) -> dict:
        """Starts a sign-in and opens the browser at the account. Already signed in: the state
        as it is. Raises `AccountError` (ACCOUNT_OFFLINE, ACCOUNT_REFUSED, ACCOUNT_UNAVAILABLE)."""
        with self._lock:
            if self.signed_in():
                return self.state()
            self._stop_pending()
            self._attempt += 1
            attempt = self._attempt
            self._note = None
            client = self.client()
            try:
                if device:
                    pending = self._start_device(client, attempt)
                else:
                    flow = client.browser_sign_in(
                        locale, lambda tokens, problem: self._finished(attempt, tokens, problem)
                    )
                    self._cancel = flow.cancel
                    pending = {"url": flow.url}
            except oidc.Failed as e:
                log.warning("Sign-in did not start (%s)", _code(e))
                raise AccountError(oidc.problem_text(e), status=503) from None
            self._pending = pending
        try:
            webbrowser.open(pending["url"])  # the url is in the answer too, if no browser opens
        except Exception as e:  # noqa: BLE001 - the screen shows the link instead
            log.warning("The browser did not open (%s)", type(e).__name__)
        return {"state": "waiting", **pending}

    def _start_device(self, client: oidc.Client, attempt: int) -> dict:
        device = client.device_code()
        stopped = threading.Event()
        self._cancel = stopped.set

        def wait() -> None:
            try:
                tokens, problem = client.wait_for_device(device, stopped), None
            except (oidc.Refused, oidc.Failed) as e:
                tokens, problem = None, e
            if not stopped.is_set():
                self._finished(attempt, tokens, problem)

        threading.Thread(target=wait, name="account-device", daemon=True).start()
        return {
            "url": device["verification_uri_complete"] or device["verification_uri"],
            "device": {
                "user_code": device["user_code"],
                "verification_uri": device["verification_uri"],
            },
        }

    def cancel(self) -> dict:
        with self._lock:
            self._attempt += 1
            self._stop_pending()
        return self.state()

    def sign_out(self) -> dict:
        """Revokes the refresh token when the account can be reached, and forgets it here
        either way."""
        with self._lock:
            self._attempt += 1
            self._stop_pending()
            self._note = None
            try:
                loaded = self._load()
            except KeyringError:
                loaded = None
        if loaded is not None:
            try:
                self.client().revoke(loaded[0])
            except (oidc.Failed, AccountError) as e:
                log.info("The refresh token was not revoked (%s); it is forgotten here", _code(e))
        with self._lock:
            self._forget()
        log.info("Signed out of the QS Mind account")
        return {"state": "signed_out"}

    def _stop_pending(self) -> None:
        if self._cancel is not None:
            self._cancel()
        self._cancel, self._pending = None, None

    def _finished(
        self, attempt: int, tokens: oidc.Tokens | None, problem: Exception | None
    ) -> None:
        """A sign-in ended (in the loopback's or the device wait's thread)."""
        with self._lock:
            if attempt != self._attempt:
                return  # cancelled, or another sign-in started
            if tokens is not None and problem is None and not tokens.refresh_token:
                problem = oidc.Failed("no refresh token")
            if problem is None and tokens is not None:
                try:
                    self._keep(tokens)
                except KeyringError as e:
                    problem = e
                    self._revoke_quietly(tokens.refresh_token)
            if problem is not None:
                self._cancel, self._pending = None, None
                self._note = (
                    copy.ACCOUNT_KEY_STORE_DOWN
                    if isinstance(problem, KeyringError)
                    else oidc.problem_text(problem)
                )
                log.warning("Sign-in did not finish (%s)", _code(problem))
                return
            self._checked_at, self._failed, self._synced = self.clock(), False, False
            log.info("Signed in to the QS Mind account")
        self._sync()  # still "waiting" on the screen until the Backup key is settled
        with self._lock:
            if attempt == self._attempt:
                self._cancel, self._pending = None, None

    def _revoke_quietly(self, refresh_token: str | None) -> None:
        if not refresh_token:
            return
        client = self._client

        def revoke() -> None:
            try:
                if client is not None:
                    client.revoke(refresh_token)
            except oidc.Failed:
                pass

        threading.Thread(target=revoke, daemon=True).start()

    def _sync(self) -> None:
        if self.on_signed_in is None or not self.signed_in():
            return
        try:
            self.on_signed_in()
        except Exception as e:  # noqa: BLE001 - tried again after the next refresh
            log.warning("The Backup key was not settled with the account (%s)", type(e).__name__)
            return
        with self._lock:
            self._synced = True

    # Tokens ---------------------------------------------------------------------------------------

    def access_token(self) -> str | None:
        """A good access token, refreshed when needed; None when signed out, offline, or after
        a refusal (which signs out here)."""
        with self._lock:
            if self._access is not None and self.clock() < self._access[1]:
                return self._access[0]
        with self._refresh_lock:
            with self._lock:  # another thread may have just refreshed
                if self._access is not None and self.clock() < self._access[1]:
                    return self._access[0]
            return self._refresh()

    def drop_access(self) -> None:
        """The account refused this access token: the next call refreshes."""
        with self._lock:
            self._access = None

    def _refresh(self) -> str | None:
        """Called with the refresh lock held, never this object's lock: the call is slow."""
        with self._lock:
            try:
                loaded = self._load()
            except KeyringError as e:
                log.warning("The key store is not available (%s)", type(e).__name__)
                self._note = copy.ACCOUNT_KEY_STORE_DOWN
                return None
            attempt = self._attempt
        if loaded is None:
            return None
        token, profile = loaded
        try:
            tokens = self.client().refresh(token, profile["sub"])
        except oidc.Refused as e:
            log.info("The account refused the refresh (%s): signed out here", e.code)
            with self._lock:
                if attempt == self._attempt:
                    self._forget()
                    self._note = copy.ACCOUNT_REFUSED
            return None
        except oidc.Failed as e:
            log.info("The account was not refreshed (%s)", _code(e))
            with self._lock:
                self._failed = True
                self._note = oidc.problem_text(e)
            return None
        except AccountError:
            return None
        with self._lock:
            if attempt != self._attempt:
                return None  # signed out meanwhile
            if not tokens.refresh_token:
                tokens = oidc.Tokens(tokens.access_token, token, tokens.profile, tokens.expires_in)
            try:
                self._keep(tokens)
            except KeyringError as e:
                log.warning("The new refresh token was not kept (%s)", type(e).__name__)
                self._note = copy.ACCOUNT_KEY_STORE_DOWN
                return None
            self._failed, self._note = False, None
            return tokens.access_token

    def _refresh_if_due(self) -> None:
        with self._lock:
            if self._pending is not None or self._refreshing:
                return
            now = self.clock()
            wait = RETRY_AFTER if self._failed else REFRESH_EVERY
            if self._checked_at is not None and now - self._checked_at < wait:
                return
            if not self.signed_in():
                return
            self._checked_at, self._refreshing = now, True

        def refresh() -> None:
            try:
                with self._refresh_lock:
                    access = self._refresh()
                if access is not None and not self._synced:
                    self._sync()
            finally:
                with self._lock:
                    self._refreshing = False

        # In the background: asking for the account never waits on the network.
        threading.Thread(target=refresh, name="account-refresh", daemon=True).start()

    # The vault ------------------------------------------------------------------------------------

    def escrow(self) -> AccountEscrow | None:
        """The account's vault, which keeps the Backup key; None when signed out."""
        with self._lock:
            if not self.signed_in():
                return None
            if self._escrow is None:
                self._escrow = AccountEscrow(self)
            return self._escrow
