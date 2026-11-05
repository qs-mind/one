"""Undo instead of "are you sure?": a removal happens at once and can be taken back for
`WINDOW_S`, which the screen shows as a line shrinking over the same time.

The thing leaves use at once and is kept aside in settings ("trash"), so a core that stops inside
the window still has it. When the window ends (with a short grace, so an Undo pressed at its very
end still arrives) it is purged for good, which is when its key leaves the key store; whatever a
stopped core left is purged at the next start. A purge that fails stays aside and is tried again
then. While the engineer points at the Undo (or it has focus) the screen pauses its line, and the
window here pauses with it, so the time shown is the time there is. Each kind of thing says how it
is put back and how it is purged.

- `POST /undo/{token}` → 204, or 404 `{"error": UNDO_GONE}` once the window has ended, or 409
  `{"error": text}` when the kind's restore says why it cannot be put back.
- `POST /undo/{token}/pause` and `/resume` → 204 (404 once it has ended)."""

import asyncio
import logging
import time
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
    """`later(delay, callback)` runs the purge when the window ends and returns a handle with
    `cancel()` (default: the running loop's `call_later`, so `put` and `resume` run on the
    core's loop); `clock` is in seconds. Tests pass their own."""

    def __init__(
        self,
        *,
        window_s: float = WINDOW_S,
        grace_s: float = GRACE_S,
        later: Callable[[float, Callable[[], None]], object] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.window_s = window_s
        self.grace_s = grace_s
        self._later = later
        self._clock = clock
        self._kinds: dict[str, tuple[Callable[[dict], bool | dict], Callable[[dict], None]]] = {}
        # token -> (purge handle, deadline) while it runs, or (None, seconds left) while paused
        self._windows: dict[str, tuple[object | None, float]] = {}

    def kind(
        self,
        name: str,
        *,
        restore: Callable[[dict], bool | dict],
        purge: Callable[[dict], None],
    ) -> None:
        """`restore(entry)` puts it back (False when it cannot be, e.g. its name was taken
        again, or the {en, ar} words that say why); `purge(entry)` drops what was kept aside."""
        self._kinds[name] = (restore, purge)

    def _held(self) -> dict[str, dict]:
        saved = settings.load().get(SETTING)
        return dict(saved) if isinstance(saved, dict) else {}

    def _keep(self, held: dict[str, dict]) -> None:
        settings.save(SETTING, held)

    def _run(self, token: str, seconds: float) -> None:
        later = self._later or asyncio.get_running_loop().call_later
        handle = later(seconds + self.grace_s, lambda: self.purge(token))
        self._windows[token] = (handle, self._clock() + seconds)

    def _stop(self, token: str) -> None:
        handle, _ = self._windows.pop(token, (None, 0.0))
        if handle is not None:
            handle.cancel()

    def put(self, kind: str, entry: dict) -> dict:
        """Keeps `entry` aside for the window; the screen's answer: its Undo token and window."""
        token = uuid4().hex
        self._keep(self._held() | {token: {"kind": kind, "entry": entry}})
        self._run(token, self.window_s)
        return {"undo": token, "window_ms": round(self.window_s * 1000)}

    def undo(self, token: str) -> bool | dict:
        """Puts it back; False when the window has ended (or it was undone already), or the
        restore's own words when it could not be."""
        held = self._held()
        found = held.pop(token, None)
        if found is None or found["kind"] not in self._kinds:
            return False
        self._stop(token)
        self._keep(held)
        restore, _ = self._kinds[found["kind"]]
        return restore(found["entry"])

    def pause(self, token: str) -> bool:
        window = self._windows.get(token)
        if window is None:
            return False
        handle, deadline = window
        if handle is not None:  # running: keep the time it has left
            handle.cancel()
            self._windows[token] = (None, max(0.0, deadline - self._clock()))
        return True

    def resume(self, token: str) -> bool:
        window = self._windows.get(token)
        if window is None:
            return False
        handle, left = window
        if handle is None:
            self._run(token, left)
        return True

    def purge(self, token: str) -> None:
        self._stop(token)
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

    def gone() -> JSONResponse:
        return JSONResponse({"error": copy.UNDO_GONE}, status_code=404)

    @r.post("/undo/{token}")
    async def undo(token: str) -> Response:
        done = trash.undo(token)
        if isinstance(done, dict):
            return JSONResponse({"error": done}, status_code=409)
        return Response(status_code=204) if done else gone()

    @r.post("/undo/{token}/pause")
    async def pause(token: str) -> Response:
        return Response(status_code=204) if trash.pause(token) else gone()

    @r.post("/undo/{token}/resume")
    async def resume(token: str) -> Response:
        return Response(status_code=204) if trash.resume(token) else gone()

    return r
