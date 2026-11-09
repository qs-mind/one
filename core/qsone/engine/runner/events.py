import asyncio
from collections.abc import AsyncIterator
from dataclasses import replace

from qsone.engine.runner.shared import log
from qsone.engine.types import (
    BriefState,
    Data,
    Event,
    Progress,
    Settled,
    Status,
    Text,
    TextDelta,
)


class _BriefEvents:
    """The Brief's event log, its state and its work log, and how the screen follows them."""

    # Events --------------------------------------------------------------------------------

    def _notify(self) -> None:
        self._news.set()
        self._news = asyncio.Event()

    def _now(self) -> str:
        return self.engine.clock().isoformat(timespec="milliseconds")

    def emit(self, event: Event) -> None:
        if isinstance(event, Progress) and event.lang is None:
            event = replace(event, lang=self.lang)
        if isinstance(event, Progress | Settled) and event.at is None:
            event = replace(event, at=self._now())
        if isinstance(event, TextDelta):
            self.said += len(event.text.encode("utf-16-le")) // 2
        self.log.append(event)
        if isinstance(event, Progress):
            self._agent(event.run_id, state="working", line=event.text, focus=event.focus)
            self.step = event.text
            if self.state == "running" and self.cancel_mode != "crash":
                self.store.set_status(self.brief_id, "running", event.text)
            self.worklog.add(event, event.at)
            self._worklog_changed()
        self._notify()

    def _worklog_changed(self) -> None:
        """Saves the work log and sends it whole (`data-worklog`, id: the Brief)."""
        if self.cancel_mode != "crash":
            self.store.set_worklog(self.brief_id, self.worklog.saved())
        self.log.append(Data(self.brief_id, "worklog", self.brief_id, self.worklog.as_json()))
        self._notify()

    def _tools_done(self, run_id: str) -> None:
        """The run's tools have returned: its tool steps end now."""
        if self.worklog.tools_done(run_id, self._now()):
            self._worklog_changed()

    async def events(self) -> AsyncIterator[Event]:
        i = 0
        while True:
            news = self._news
            while i < len(self.log):
                yield self.log[i]
                i += 1
            if self.finished:
                return
            await news.wait()

    def set_state(self, state: BriefState, step: Text | None = None) -> None:
        self.state = state
        if step is not None:
            self.step = step
        if self.cancel_mode != "crash":
            self.store.set_status(self.brief_id, state, self.step)
        log.info("brief %s %s", self.brief_id, state)
        if state in ("done", "failed", "stopped"):
            self.worklog.end(self._now())
            self._worklog_changed()
        self.emit(Status(self.brief_id, state, self.step))
