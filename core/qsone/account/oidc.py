"""The QS Mind account's protocol, for One's own native (public) OpenID Connect client. No app
state here: httpx, PyJWT and truststore only. The session (`session.py`) keeps the tokens.

1. Discovery: `<issuer>/.well-known/openid-configuration` names every endpoint below, and must
   name this issuer.
2. Browser sign-in (RFC 8252): a listener on 127.0.0.1 at a free port takes the browser's one
   redirect back to `http://127.0.0.1:<port>/callback`. The request carries PKCE (S256), `state`
   and `nonce`, and the scope `openid profile email offline_access vault`.
3. The code is exchanged with the PKCE verifier. The ID token is checked against the JWKS (RS256,
   key by `kid`, issuer, audience, expiry, nonce); user info gives the email and the name.
4. Device sign-in (RFC 8628) is the fallback, for when the browser cannot come back.
5. Refresh tokens rotate: the answer's new one replaces the old. Sign-out revokes it.

HTTPS uses the system's certificates (truststore). Plain HTTP is allowed for a loopback issuer
only (the tests' FakeAccount). Never log a token, a code, an email or a name: errors carry OAuth
error codes and exception classes only.
"""

import base64
import hashlib
import html
import ipaddress
import os
import secrets
import ssl
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import httpx
import jwt
import truststore

from qsone import copy

ISSUER = "https://auth.qsmind.app"  # QSONE_AUTH_ISSUER overrides it (tests)
CLIENT_ID = ""  # One's native client id, registered by O1 in the auth repo; QSONE_AUTH_CLIENT_ID
SCOPE = "openid profile email offline_access vault"
DEVICE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"
TIMEOUT = httpx.Timeout(15.0, connect=5.0)
SIGN_IN_SECONDS = 10 * 60  # how long a browser sign-in waits for the redirect back


def issuer() -> str:
    return (os.environ.get("QSONE_AUTH_ISSUER") or ISSUER).rstrip("/")


def client_id() -> str:
    return os.environ.get("QSONE_AUTH_CLIENT_ID") or CLIENT_ID


class Refused(Exception):
    """The account said no, with an OAuth error code: `invalid_grant` (a refresh token revoked or
    expired), `access_denied`, `expired_token`, `wrong_account`, ..."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class Failed(Exception):
    """The call did not complete: no connection (`offline`), a server error, or an answer that
    does not hold up (an ID token that does not verify). Trying again later may work."""

    def __init__(self, reason: str, offline: bool = False):
        super().__init__(reason)
        self.offline = offline


@dataclass(frozen=True)
class Tokens:
    access_token: str = field(repr=False)
    refresh_token: str | None = field(repr=False)
    profile: dict = field(repr=False)  # sub, email, name
    expires_in: int = 3600


def _loopback(url: str) -> bool:
    host = urlparse(url).hostname or ""
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


class Client:
    """One's connection to the account. Discovery and the key set are cached."""

    def __init__(
        self, client_id: str, issuer: str = ISSUER, http: httpx.Client | None = None
    ) -> None:
        self.client_id = client_id
        self.issuer = issuer.rstrip("/")
        scheme = urlparse(self.issuer).scheme
        if scheme != "https" and not (scheme == "http" and _loopback(self.issuer)):
            raise ValueError("the account's issuer must be https")
        self.http = http or httpx.Client(
            timeout=TIMEOUT, verify=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        )
        self._metadata: dict | None = None
        self._keys: dict[str, Any] = {}
        self._lock = threading.Lock()

    def close(self) -> None:
        self.http.close()

    # Plumbing ------------------------------------------------------------------------------------

    def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        """Raises `Failed` (offline, or a server error)."""
        try:
            answer = self.http.request(method, url, **kwargs)
        except httpx.TransportError as e:
            raise Failed(type(e).__name__, offline=True) from None
        if answer.status_code >= 500:
            raise Failed(f"the account answered {answer.status_code}")
        return answer

    def metadata(self) -> dict:
        with self._lock:
            if self._metadata is not None:
                return self._metadata
        answer = self.request("GET", f"{self.issuer}/.well-known/openid-configuration")
        try:
            data = answer.json() if answer.is_success else None
        except ValueError:
            data = None
        if not isinstance(data, dict) or str(data.get("issuer", "")).rstrip("/") != self.issuer:
            raise Failed("discovery did not name this issuer")
        with self._lock:
            self._metadata = data
        return data

    def endpoint(self, name: str) -> str:
        url = self.metadata().get(name)
        if not isinstance(url, str) or not url:
            raise Failed(f"the account publishes no {name}")
        return url

    def _token(self, form: dict[str, str]) -> dict:
        answer = self.request(
            "POST", self.endpoint("token_endpoint"), data=form | {"client_id": self.client_id}
        )
        try:
            data = answer.json()
        except ValueError:
            raise Failed(f"the token endpoint answered {answer.status_code}") from None
        if answer.is_success and isinstance(data, dict) and data.get("access_token"):
            return data
        if isinstance(data, dict) and isinstance(data.get("error"), str):
            raise Refused(data["error"])
        raise Failed(f"the token endpoint answered {answer.status_code}")

    def _key(self, kid: str | None) -> Any:
        with self._lock:
            if kid in self._keys:
                return self._keys[kid]
        # Keys rotate: an unknown kid means the set changed, so it is fetched again once.
        answer = self.request("GET", self.endpoint("jwks_uri"))
        try:
            found = jwt.PyJWKSet.from_dict(answer.json())
        except (ValueError, jwt.PyJWTError):
            raise Failed("the key set cannot be read") from None
        with self._lock:
            self._keys = {key.key_id: key for key in found.keys}
            if kid not in self._keys:
                raise Failed("the ID token's key is not in the key set")
            return self._keys[kid]

    def _claims(self, id_token: str, nonce: str | None) -> dict:
        try:
            key = self._key(jwt.get_unverified_header(id_token).get("kid"))
            claims = jwt.decode(
                id_token,
                key,
                algorithms=["RS256"],
                audience=self.client_id,
                issuer=self.issuer,
                leeway=60,
                options={"require": ["exp", "iat", "sub", "aud", "iss"]},
            )
        except jwt.PyJWTError as e:
            raise Failed(f"the ID token does not verify ({type(e).__name__})") from None
        if nonce is not None and not secrets.compare_digest(str(claims.get("nonce", "")), nonce):
            raise Failed("the ID token is for another sign-in")
        return claims

    def _finish(self, answer: dict, nonce: str | None, sub: str | None = None) -> Tokens:
        """Tokens from a token answer: the ID token checked, the profile from it and user info.
        With `sub` (a refresh), the account must be the same one."""
        id_token = answer.get("id_token")
        claims = self._claims(id_token, nonce) if isinstance(id_token, str) else {}
        if not claims and sub is None:
            raise Failed("no ID token in the answer")
        info_answer = self.request(
            "GET",
            self.endpoint("userinfo_endpoint"),
            headers={"Authorization": f"Bearer {answer['access_token']}"},
        )
        try:
            info = info_answer.json() if info_answer.is_success else None
        except ValueError:
            info = None
        if not isinstance(info, dict):
            raise Failed(f"user info answered {info_answer.status_code}")
        expected = claims.get("sub") or sub
        if info.get("sub") != expected or (sub is not None and expected != sub):
            raise Refused("wrong_account")
        profile = {
            "sub": expected,
            "email": info.get("email") or claims.get("email"),
            "name": info.get("name") or claims.get("name"),
        }
        expires = answer.get("expires_in")
        return Tokens(
            str(answer["access_token"]),
            answer.get("refresh_token") if isinstance(answer.get("refresh_token"), str) else None,
            profile,
            expires if type(expires) is int and expires > 0 else 3600,
        )

    # Sign-in, refresh, sign-out -----------------------------------------------------------------

    def browser_sign_in(
        self, locale: str, done: Callable[[Tokens | None, Exception | None], None]
    ) -> "Loopback":
        """Starts listening for the redirect back; open `.url` in the browser. Raises `Failed`."""
        return Loopback(self, locale, done)

    def exchange(self, code: str, redirect_uri: str, verifier: str, nonce: str) -> Tokens:
        answer = self._token(
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "code_verifier": verifier,
            }
        )
        return self._finish(answer, nonce)

    def refresh(self, refresh_token: str, sub: str) -> Tokens:
        """New tokens for the same account; keep the rotated refresh token in place of the old."""
        answer = self._token({"grant_type": "refresh_token", "refresh_token": refresh_token})
        return self._finish(answer, None, sub)

    def revoke(self, refresh_token: str) -> None:
        self.request(
            "POST",
            self.endpoint("revocation_endpoint"),
            data={
                "token": refresh_token,
                "token_type_hint": "refresh_token",
                "client_id": self.client_id,
            },
        )

    def device_code(self) -> dict:
        """{"device_code", "user_code", "verification_uri", "verification_uri_complete",
        "expires_in", "interval"}. Raises `Failed`."""
        answer = self.request(
            "POST",
            self.endpoint("device_authorization_endpoint"),
            data={"client_id": self.client_id, "scope": SCOPE},
        )
        try:
            data = answer.json() if answer.is_success else None
        except ValueError:
            data = None
        if not isinstance(data, dict) or not data.get("device_code") or not data.get("user_code"):
            raise Failed(f"device sign-in answered {answer.status_code}")
        return {
            "device_code": str(data["device_code"]),
            "user_code": str(data["user_code"]),
            "verification_uri": str(data.get("verification_uri", "")),
            "verification_uri_complete": data.get("verification_uri_complete"),
            "expires_in": int(data.get("expires_in", 600)),
            "interval": int(data.get("interval", 5)),
        }

    def wait_for_device(self, device: dict, stopped: threading.Event) -> Tokens | None:
        """Asks at the interval until the engineer approves (the tokens), refuses or lets the
        code expire (`Refused`), or `stopped` is set (None)."""
        interval, waited = max(int(device["interval"]), 1), 0
        while waited < device["expires_in"]:
            if stopped.wait(interval):
                return None
            waited += interval
            try:
                form = {"grant_type": DEVICE_GRANT, "device_code": device["device_code"]}
                return self._finish(self._token(form), None)
            except Refused as e:
                if e.code == "slow_down":
                    interval += 5
                elif e.code != "authorization_pending":
                    raise
        raise Refused("expired_token")


# The page the browser shows after the redirect back: both languages, QS Mind colours, no script.
_PAGE = """<!doctype html>
<html lang="{lang}" dir="{dir}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>QS Mind One</title>
<style>
:root {{ color-scheme: light dark; }}
body {{ margin: 0; min-height: 100vh; display: grid; place-items: center; background: #F9F8F4;
  color: #0E0F12; font-family: "Kumbh Sans", "Thmanyah Sans", system-ui, sans-serif; }}
main {{ max-width: 32rem; padding: 2rem 1.5rem; border-top: 3px solid #A6491B; }}
p {{ margin: 0 0 1rem; font-size: 1.25rem; line-height: 1.6; }}
p.other {{ color: #6E6A64; font-size: 1.05rem; }}
@media (prefers-color-scheme: dark) {{ body {{ background: #0E0F12; color: #F2EEE7; }} }}
</style></head>
<body><main><p>{first}</p><p class="other" lang="{other_lang}" dir="{other_dir}">{second}</p>
</main></body></html>
"""


def page(text: dict[str, str], locale: str) -> bytes:
    """The loopback page for `text` (an {en, ar} pair), the engineer's language first."""
    first, other = ("ar", "en") if locale == "ar" else ("en", "ar")
    return _PAGE.format(
        lang=first,
        dir="rtl" if first == "ar" else "ltr",
        first=html.escape(text[first]),
        other_lang=other,
        other_dir="rtl" if other == "ar" else "ltr",
        second=html.escape(text[other]),
    ).encode("utf-8")


def problem_text(error: Exception) -> dict[str, str]:
    """What a failed sign-in or refresh says to the engineer, as an {en, ar} pair."""
    if isinstance(error, Refused):
        if error.code == "access_denied":
            return copy.ACCOUNT_DENIED
        if error.code == "expired_token":
            return copy.ACCOUNT_EXPIRED
        return copy.ACCOUNT_REFUSED
    if isinstance(error, Failed) and error.offline:
        return copy.ACCOUNT_OFFLINE
    return copy.ACCOUNT_REFUSED


class Loopback:
    """One browser sign-in: the authorize URL to open, and a listener on 127.0.0.1 for the one
    redirect back. `done` is called once, with the tokens or why it failed (`Refused
    ("expired_token")` when nobody came back in time); never after `cancel()`."""

    def __init__(
        self,
        client: Client,
        locale: str,
        done: Callable[[Tokens | None, Exception | None], None],
    ) -> None:
        self.client, self.locale, self._done = client, locale, done
        authorize = client.endpoint("authorization_endpoint")  # first: discovery may fail
        self._state = secrets.token_urlsafe(32)
        self._nonce = secrets.token_urlsafe(32)
        self._verifier = secrets.token_urlsafe(64)
        self._answered = threading.Event()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self.redirect_uri = f"http://127.0.0.1:{self.server.server_address[1]}/callback"
        query = {
            "response_type": "code",
            "client_id": client.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": SCOPE,
            "state": self._state,
            "nonce": self._nonce,
            "code_challenge": _challenge(self._verifier),
            "code_challenge_method": "S256",
            "ui_locales": locale,
        }
        self.url = f"{authorize}?{urlencode(query)}"
        threading.Thread(target=self.server.serve_forever, name="account-loopback", daemon=True).start()
        self._timer = threading.Timer(SIGN_IN_SECONDS, self._expire)
        self._timer.daemon = True
        self._timer.start()

    def cancel(self) -> None:
        if not self._answered.is_set():
            self._answered.set()
            self._close()

    def _expire(self) -> None:
        if not self._answered.is_set():
            self._answered.set()
            self._close()
            self._done(None, Refused("expired_token"))

    def _close(self) -> None:
        self._timer.cancel()
        # Not from the handler's own thread: shutdown waits for serve_forever to return.
        threading.Thread(target=self._shut, daemon=True).start()

    def _shut(self) -> None:
        self.server.shutdown()
        self.server.server_close()

    def _callback(self, query: dict[str, list[str]]) -> tuple[int, dict[str, str]]:
        """The redirect back: the status and the text to answer with."""
        state = (query.get("state") or [""])[0]
        if self._answered.is_set() or not secrets.compare_digest(
            state.encode(), self._state.encode()
        ):
            return 400, copy.ACCOUNT_REFUSED  # not this sign-in's redirect: keep waiting
        self._answered.set()
        tokens: Tokens | None = None
        problem: Exception | None = None
        try:
            if query.get("error"):
                raise Refused(query["error"][0][:64])
            code = (query.get("code") or [""])[0]
            if not code:
                raise Failed("no code in the redirect")
            tokens = self.client.exchange(code, self.redirect_uri, self._verifier, self._nonce)
        except (Refused, Failed) as e:
            problem = e
        finally:
            self._close()
        self._done(tokens, problem)
        if problem is not None:
            return 200, problem_text(problem)
        return 200, copy.ACCOUNT_SIGNED_IN

    def _handler(self) -> type[BaseHTTPRequestHandler]:
        sign_in = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 - the standard library's name
                url = urlparse(self.path)
                if url.path != "/callback":
                    self.send_error(404)  # a favicon or a stray request
                    return
                status, text = sign_in._callback(parse_qs(url.query))
                body = page(text, sign_in.locale)
                self.send_response(status)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("Referrer-Policy", "no-referrer")
                self.send_header(
                    "Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'"
                )
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: Any) -> None:
                pass  # the redirect carries the code: never logged

        return Handler
