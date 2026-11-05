"""Stand-ins for the services Plan 8 talks to, each on 127.0.0.1 in a thread: the QS Mind account
(OIDC and its key vault) and Umami (Usage Stats). Tests never reach the real ones.

The vault's wire format is One's proposal for the auth repo (Plan 8 O1): `PUT /api/vault/{name}`
with `{"value": str}` (at most 4 KB), `GET` answers `{"name", "value", "updated_at"}` or 404,
`DELETE` answers 204. Every vault call needs an access token with the scope `vault`.
"""

import base64
import hashlib
import re
import secrets
import socket
import threading
import time
import uuid
from datetime import UTC, datetime
from urllib.parse import urlencode

import httpx
import jwt
import uvicorn
from cryptography.hazmat.primitives.asymmetric import rsa
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, Response
from starlette.routing import Route

VAULT_MAX = 4096
DEVICE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class LoopbackServer:
    """An ASGI app on uvicorn on 127.0.0.1, in a thread. `down = True` stops it, so a call
    gets a refused connection, as when the computer is offline; `down = False` starts it again
    on the same port."""

    def __init__(self, app) -> None:
        self._app = app
        self.port = _free_port()
        self.base = f"http://127.0.0.1:{self.port}"
        self._server: uvicorn.Server | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        config = uvicorn.Config(self._app, host="127.0.0.1", port=self.port, log_level="warning")
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self._server.run, daemon=True)
        self._thread.start()
        deadline = time.monotonic() + 10
        while not self._server.started:
            assert time.monotonic() < deadline, "fake server did not start"
            time.sleep(0.01)

    def stop(self) -> None:
        if self._server is not None:
            self._server.should_exit = True
            self._thread.join(timeout=10)
            self._server = None

    @property
    def down(self) -> bool:
        return self._server is None

    @down.setter
    def down(self, value: bool) -> None:
        if value and not self.down:
            self.stop()
        elif not value and self.down:
            self.start()


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


class FakeAccount(LoopbackServer):
    """The QS Mind account: OIDC discovery, JWKS (RS256), authorize, token (code with PKCE,
    rotating refresh tokens, the device grant), userinfo, revoke, and `/api/vault/{name}`.

    Switches: `down` (offline), `deny` (the engineer says no in the browser), `revoked` (the
    account was signed out elsewhere: refresh tokens and access tokens stop working).
    `token_issuer` signs ID tokens with another issuer when set. `opened` is the list of URLs
    the app gave the browser (`no_browser`); `approve_last()` follows the last one."""

    client_id = "one-test-client"

    def __init__(self, opened: list[str] | None = None) -> None:
        super().__init__(self._make_app())
        self.issuer = self.base
        self.opened = opened if opened is not None else []
        self.user = {"sub": "user-0001", "email": "engineer@example.com", "name": "مهندس - عينة"}
        self.deny = False
        self.revoked = False
        self.token_issuer: str | None = None
        self.access_ttl = 3600
        self.device_interval = 1
        self.vault: dict[str, str] = {}
        self.vault_times: dict[str, str] = {}
        self.revocations: list[str] = []  # refresh tokens the app revoked
        self.requests: list[tuple[str, str]] = []  # (method, path), for tests that count calls
        self._key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self._kid = "test-key-1"
        self._codes: dict[str, dict] = {}
        self._refresh: dict[str, dict] = {}  # live refresh token -> grant
        self._access: dict[str, dict] = {}  # access token -> {sub, scope, exp}
        self._devices: dict[str, dict] = {}  # device_code -> {user_code, scope, state, exp}
        self._lock = threading.Lock()

    # --- what tests call -----------------------------------------------------------------

    def get(self, path: str) -> dict:
        return httpx.get(self.base + path, timeout=10).raise_for_status().json()

    def token_for(self, scope: str = "openid profile email offline_access vault") -> str:
        """An access token with `scope`, as the token endpoint would give."""
        return self._new_access(self.user["sub"], scope)

    def put_vault(
        self, name: str, value: str, *, scope: str = "openid vault", token: str | None = None
    ) -> httpx.Response:
        token = token or self.token_for(scope)
        return httpx.put(
            f"{self.base}/api/vault/{name}",
            json={"value": value},
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )

    def approve_last(self) -> httpx.Response:
        """Does what the browser does after the engineer signs in: opens the last authorize URL
        the app gave, then follows the redirect back to the app's loopback page."""
        assert self.opened, "the app opened no browser"
        answer = httpx.get(self.opened[-1], follow_redirects=False, timeout=10)
        assert answer.status_code in (302, 303), answer.text
        return httpx.get(answer.headers["location"], timeout=10)

    def approve_device(self, user_code: str | None = None) -> None:
        """The engineer types the device code on the account's page and approves it."""
        with self._lock:
            for device in self._devices.values():
                if user_code is None or device["user_code"] == user_code:
                    device["state"] = "denied" if self.deny else "approved"

    def expire_devices(self) -> None:
        with self._lock:
            for device in self._devices.values():
                device["exp"] = 0

    # --- the protocol ----------------------------------------------------------------------

    def _make_app(self) -> Starlette:
        return Starlette(
            routes=[
                Route("/.well-known/openid-configuration", self._discovery),
                Route("/.well-known/jwks.json", self._jwks),
                Route("/oauth/authorize", self._authorize),
                Route("/oauth/token", self._token, methods=["POST"]),
                Route("/oauth/device", self._device, methods=["POST"]),
                Route("/oauth/userinfo", self._userinfo),
                Route("/oauth/revoke", self._revoke, methods=["POST"]),
                Route("/api/vault/{name}", self._vault, methods=["GET", "PUT", "DELETE"]),
            ]
        )

    async def _discovery(self, request: Request) -> Response:
        self.requests.append(("GET", request.url.path))
        b = self.base
        return JSONResponse(
            {
                "issuer": self.issuer,
                "authorization_endpoint": f"{b}/oauth/authorize",
                "token_endpoint": f"{b}/oauth/token",
                "device_authorization_endpoint": f"{b}/oauth/device",
                "userinfo_endpoint": f"{b}/oauth/userinfo",
                "revocation_endpoint": f"{b}/oauth/revoke",
                "jwks_uri": f"{b}/.well-known/jwks.json",
                "response_types_supported": ["code"],
                "grant_types_supported": ["authorization_code", "refresh_token", DEVICE_GRANT],
                "code_challenge_methods_supported": ["S256"],
                "id_token_signing_alg_values_supported": ["RS256"],
                "scopes_supported": ["openid", "profile", "email", "offline_access", "vault"],
                "subject_types_supported": ["public"],
            }
        )

    async def _jwks(self, request: Request) -> Response:
        jwk = jwt.algorithms.RSAAlgorithm.to_jwk(self._key.public_key(), as_dict=True)
        return JSONResponse({"keys": [jwk | {"kid": self._kid, "use": "sig", "alg": "RS256"}]})

    async def _authorize(self, request: Request) -> Response:
        self.requests.append(("GET", request.url.path))
        q = request.query_params
        redirect = q.get("redirect_uri", "")
        if q.get("client_id") != self.client_id or not re.match(
            r"^http://127\.0\.0\.1:\d+/", redirect
        ):
            return JSONResponse({"error": "invalid_request"}, status_code=400)
        state = q.get("state", "")
        if self.deny:
            return RedirectResponse(
                f"{redirect}?{urlencode({'error': 'access_denied', 'state': state})}", 302
            )
        if q.get("response_type") != "code" or q.get("code_challenge_method") != "S256":
            return JSONResponse({"error": "invalid_request"}, status_code=400)
        code = secrets.token_urlsafe(24)
        with self._lock:
            self._codes[code] = {
                "redirect_uri": redirect,
                "challenge": q.get("code_challenge", ""),
                "scope": q.get("scope", "openid"),
                "nonce": q.get("nonce"),
            }
        return RedirectResponse(f"{redirect}?{urlencode({'code': code, 'state': state})}", 302)

    async def _token(self, request: Request) -> Response:
        self.requests.append(("POST", request.url.path))
        form = await request.form()
        if form.get("client_id") != self.client_id:
            return self._error("invalid_client", 401)
        grant = form.get("grant_type")
        with self._lock:
            if grant == "authorization_code":
                code = self._codes.get(str(form.get("code", "")))
                verifier = str(form.get("code_verifier", ""))
                if (
                    code is None
                    or code["redirect_uri"] != form.get("redirect_uri")
                    or _b64url(hashlib.sha256(verifier.encode()).digest()) != code["challenge"]
                ):
                    return self._error("invalid_grant")
                del self._codes[str(form["code"])]  # a code works once
                return JSONResponse(self._issue(code["scope"], nonce=code["nonce"]))
            if grant == "refresh_token":
                old = self._refresh.pop(str(form.get("refresh_token", "")), None)
                if old is None or self.revoked:
                    return self._error("invalid_grant")
                return JSONResponse(self._issue(old["scope"]))
            if grant == DEVICE_GRANT:
                device = self._devices.get(str(form.get("device_code", "")))
                if device is None:
                    return self._error("invalid_grant")
                if device["exp"] < time.time():
                    return self._error("expired_token")
                if device["state"] == "denied":
                    return self._error("access_denied")
                if device["state"] != "approved":
                    return self._error("authorization_pending")
                del self._devices[str(form["device_code"])]
                return JSONResponse(self._issue(device["scope"]))
        return self._error("unsupported_grant_type")

    async def _device(self, request: Request) -> Response:
        self.requests.append(("POST", request.url.path))
        form = await request.form()
        if form.get("client_id") != self.client_id:
            return self._error("invalid_client", 401)
        device_code = secrets.token_urlsafe(24)
        user_code = f"{secrets.randbelow(10**4):04d}-{secrets.randbelow(10**4):04d}"
        with self._lock:
            self._devices[device_code] = {
                "user_code": user_code,
                "scope": str(form.get("scope", "openid")),
                "state": "pending",
                "exp": time.time() + 600,
            }
        return JSONResponse(
            {
                "device_code": device_code,
                "user_code": user_code,
                "verification_uri": f"{self.base}/device",
                "verification_uri_complete": f"{self.base}/device?user_code={user_code}",
                "expires_in": 600,
                "interval": self.device_interval,
            }
        )

    async def _userinfo(self, request: Request) -> Response:
        grant = self._bearer(request)
        if grant is None:
            return self._error("invalid_token", 401)
        return JSONResponse(self.user)

    async def _revoke(self, request: Request) -> Response:
        self.requests.append(("POST", request.url.path))
        form = await request.form()
        token = str(form.get("token", ""))
        with self._lock:
            self._refresh.pop(token, None)
            self._access.pop(token, None)
        self.revocations.append(token)
        return Response(status_code=200)

    async def _vault(self, request: Request) -> Response:
        self.requests.append((request.method, request.url.path))
        grant = self._bearer(request)
        if grant is None:
            return self._error("invalid_token", 401)
        if "vault" not in grant["scope"].split():
            return self._error("insufficient_scope", 403)
        name = request.path_params["name"]
        if not re.fullmatch(r"[a-z0-9-]{1,64}", name):
            return self._error("invalid_request")
        if request.method == "GET":
            if name not in self.vault:
                return JSONResponse({"error": "not_found"}, status_code=404)
            return JSONResponse(
                {"name": name, "value": self.vault[name], "updated_at": self.vault_times[name]}
            )
        if request.method == "DELETE":
            self.vault.pop(name, None)
            self.vault_times.pop(name, None)
            return Response(status_code=204)
        body = await request.json()
        value = body.get("value") if isinstance(body, dict) else None
        if not isinstance(value, str):
            return self._error("invalid_request")
        if len(value.encode()) > VAULT_MAX:
            return JSONResponse({"error": "too_large"}, status_code=413)
        self.vault[name] = value
        self.vault_times[name] = datetime.now(UTC).isoformat(timespec="seconds")
        return JSONResponse({"name": name, "updated_at": self.vault_times[name]})

    # --- helpers ---------------------------------------------------------------------------

    def _error(self, code: str, status: int = 400) -> JSONResponse:
        return JSONResponse({"error": code}, status_code=status)

    def _bearer(self, request: Request) -> dict | None:
        header = request.headers.get("authorization", "")
        token = header.removeprefix("Bearer ").strip() if header.startswith("Bearer ") else ""
        with self._lock:
            grant = self._access.get(token)
        if grant is None or grant["exp"] < time.time() or self.revoked:
            return None
        return grant

    def _new_access(self, sub: str, scope: str) -> str:
        token = secrets.token_urlsafe(24)
        with self._lock:
            self._access[token] = {"sub": sub, "scope": scope, "exp": time.time() + self.access_ttl}
        return token

    def _issue(self, scope: str, *, nonce: str | None = None) -> dict:
        """Called with the lock held."""
        now = int(time.time())
        access = secrets.token_urlsafe(24)
        self._access[access] = {
            "sub": self.user["sub"],
            "scope": scope,
            "exp": time.time() + self.access_ttl,
        }
        claims = {
            "iss": self.token_issuer or self.issuer,
            "aud": self.client_id,
            "sub": self.user["sub"],
            "email": self.user["email"],
            "name": self.user["name"],
            "iat": now,
            "exp": now + 600,
            "jti": uuid.uuid4().hex,
        }
        if nonce is not None:
            claims["nonce"] = nonce
        id_token = jwt.encode(claims, self._key, "RS256", headers={"kid": self._kid})
        answer = {
            "access_token": access,
            "token_type": "Bearer",
            "expires_in": self.access_ttl,
            "scope": scope,
            "id_token": id_token,
        }
        if "offline_access" in scope.split():
            refresh = secrets.token_urlsafe(32)
            self._refresh[refresh] = {"scope": scope}
            answer["refresh_token"] = refresh
        return answer


# Umami (and the `isbot` package it uses) does not count a bot: it answers 200 and drops the
# event. These are the parts of isbot's pattern that matter here: tools and libraries, and a
# User-Agent that is a bare "name/version".
_BOT = re.compile(
    r"bot|crawl|spider|slurp|headless|python|httpx|requests|curl|wget|okhttp|go-http|java/|"
    r"node-fetch|axios|undici|libwww|^[\w.\-]+(?:/v?\d+(?:\.\d+)*)?$",
    re.I,
)


def is_bot(user_agent: str) -> bool:
    return not user_agent.strip() or bool(_BOT.search(user_agent))


class FakeUmami(LoopbackServer):
    """Umami's `POST /api/send`. `received` holds every event it counted, `agents` their
    User-Agents; a bot's event is answered like Umami does and not kept."""

    def __init__(self) -> None:
        super().__init__(Starlette(routes=[Route("/api/send", self._send, methods=["POST"])]))
        self.endpoint = f"{self.base}/api/send"
        self.received: list[dict] = []
        self.agents: list[str] = []
        self.status = 200  # set 4xx/5xx to make Umami refuse every event

    async def _send(self, request: Request) -> Response:
        if self.status != 200:
            return JSONResponse({"error": "refused"}, status_code=self.status)
        user_agent = request.headers.get("user-agent", "")
        body = await request.json()
        if is_bot(user_agent):
            return JSONResponse({"beep": "boop"})
        self.received.append(body)
        self.agents.append(user_agent)
        return JSONResponse({"cache": "", "sessionId": uuid.uuid4().hex, "visitId": ""})
