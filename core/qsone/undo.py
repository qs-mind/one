"""Undo instead of "are you sure?": a removal happens at once and can be taken back for
`WINDOW_S`, which the screen shows as a line shrinking over the same time.

The thing leaves use at once and is kept aside in settings ("trash"), so a core that stops inside
the window still has it. When the window ends (with a short grace, so an Undo pressed at its very
end still arrives) it is purged for good, which is when its key leaves the key store; whatever a
stopped core left is purged at the next start. A purge that fails stays aside and is tried again
then. Each kind of thing says how it is put back and how it is purged.

- `POST /undo/{token}` → 204, or 404 `{"error": UNDO_GONE}` once the window has ended."""

import asyncio
import logging
from collections.abc import Callable
from uuid import uuid4

from fastapi import APIRouter
from fastapi.responses import JSONResponse, Response

from qsone import copy, settings

log = logging.getLogger("qsone.undo")

WINDOW_S = 6.0  # what the screen shows
GRACE_S = 2.0  # an Undo pressed at the end of the window still arrives
SETTING = "trash"


class Trash:
    """`later(delay, callback)` runs the purge when the window ends (default: the running loop's
    `call_later`); tests pass their own."""

    def __init__(
        self,
        *,
        window_s: float = WINDOW_S,
        grace_s: float = GRACE_S,
        later: Callable[[float, Callable[[], None]], object] | None = None,
    ) -> None:
        self.window_s = window_s
        self.grace_s = grace_s
        self._later = later
        self._kinds: dict[str, tuple[Callable[[dict], bool], Callable[[dict], None]]] = {}

    def kind(
        self, name: str, *, restore: Callable[[dict], bool], purge: Callable[[dict], None]
    ) -> None:
        """`restore(entry)` puts it back (False when it cannot be, e.g. its name was taken
        again); `purge(entry)` drops what was kept aside."""
        self._kinds[name] = (restore, purge)

    def _held(self) -> dict[str, dict]:
        saved = settings.load().get(SETTING)
        return dict(saved) if isinstance(saved, dict) else {}

    def _keep(self, held: dict[str, dict]) -> None:
        settings.save(SETTING, held)

    def put(self, kind: str, entry: dict) -> dict:
        """Keeps `entry` aside for the window; the screen's answer: its Undo token and window."""
        token = uuid4().hex
        self._keep(self._held() | {token: {"kind": kind, "entry": entry}})
        later = self._later or asyncio.get_running_loop().call_later
        later(self.window_s + self.grace_s, lambda: self.purge(token))
        return {"undo": token, "window_ms": round(self.window_s * 1000)}

    def undo(self, token: str) -> bool:
        """Puts it back; False when the window has ended (or it was undone already)."""
        held = self._held()
        found = held.pop(token, None)
        if found is None or found["kind"] not in self._kinds:
            return False
        self._keep(held)
        restore, _ = self._kinds[found["kind"]]
        return restore(found["entry"])

    def purge(self, token: str) -> None:
        held = self._held()
        found = held.get(token)
        if found is None or found["kind"] not in self._kinds:
            return
        _, purge = self._kinds[found["kind"]]
        try:
            purge(found["entry"])
        except Exception:  # noqa: BLE001 - kept aside, tried again at the next start
            log.warning("purge of a removed %s failed; tried again at start", found["kind"])
            return
        held = self._held()
        held.pop(token, None)
        self._keep(held)

    def purge_all(self) -> None:
        """At start (what a stopped core left) and at close (the window ends with the core)."""
        for token in list(self._held()):
            self.purge(token)


def router(trash: Trash) -> APIRouter:
    r = APIRouter()

    @r.post("/undo/{token}")
    def undo(token: str) -> Response:
        if not trash.undo(token):
            return JSONResponse({"error": copy.UNDO_GONE}, status_code=404)
        return Response(status_code=204)

    return r
