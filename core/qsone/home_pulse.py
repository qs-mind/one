"""The `home` and `tender` events (Phase 1, C7; contract section 3.4): each at most once a second
(`tender` per tender), and the last state always sent.

Anything published on a tender's activity channel or on `general` may move what Home or that
tender's header shows, and so does a project whose remembered row changed (`changed`, called by
`Projects._remember`). Each is a poke. The first poke after a quiet second sends at once; pokes
within the second wait for its end and then send one event, made at that moment. A `tender`
event carries the whole `TenderView`; `home` says "reload GET /home"."""

import asyncio
import math
import time
from collections.abc import Callable

from qsone import activity
from qsone.records.project import RecordsError

GAP_S = 1.0
GENERAL = "general"
_OWN = ("home", "tender")  # what the pulse itself publishes

_running: "Pulse | None" = None


class Pulse:
    """`tender_view(project_id)` makes the `TenderView` JSON (raises `RecordsError` for a project
    that is gone). One for the app, started on the core's loop."""

    def __init__(
        self,
        tender_view: Callable[[str], dict],
        *,
        gap_s: float = GAP_S,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.tender_view = tender_view
        self.gap_s = gap_s
        self.clock = clock
        self._loop: asyncio.AbstractEventLoop | None = None
        self._due: dict[str | None, asyncio.TimerHandle] = {}  # None: Home
        self._last: dict[str | None, float] = {}
        self._tasks: set[asyncio.Task] = set()  # kept until done, so none is collected early

    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        global _running
        self._loop = loop
        activity.LISTENERS.append(self._heard)
        _running = self

    def stop(self) -> None:
        global _running
        if self._heard in activity.LISTENERS:
            activity.LISTENERS.remove(self._heard)
        for handle in self._due.values():
            handle.cancel()
        self._due.clear()
        self._loop = None
        if _running is self:
            _running = None

    def _heard(self, channel: str, event: dict) -> None:
        if event.get("type") in _OWN:
            return
        if channel != GENERAL:
            self.poke(channel)
        self.poke(None)

    def poke(self, project_id: str | None) -> None:
        """From any thread: `project_id`'s `tender` event, or Home's (None), is due."""
        loop = self._loop
        if loop is not None and not loop.is_closed():
            loop.call_soon_threadsafe(self._plan, project_id)

    def _plan(self, key: str | None) -> None:
        if key in self._due or self._loop is None:
            return
        wait = max(0.0, self._last.get(key, -math.inf) + self.gap_s - self.clock())
        self._due[key] = self._loop.call_later(wait, self._send, key)

    def _send(self, key: str | None) -> None:
        self._due.pop(key, None)
        self._last[key] = self.clock()
        if key is None:
            activity.publish(GENERAL, {"type": "home"})
        elif self._loop is not None:
            task = self._loop.create_task(self._tender(key))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

    async def _tender(self, project_id: str) -> None:
        try:
            view = await asyncio.to_thread(self.tender_view, project_id)
        except RecordsError:
            return  # removed or unreadable meanwhile: Home says so
        activity.publish(project_id, {"type": "tender", **view})


def changed(project_id: str) -> None:
    """A project's remembered row changed: its header and Home are due."""
    found = _running
    if found is not None:
        found.poke(project_id)
        found.poke(None)
