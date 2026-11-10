"""Deliverable events on the activity stream: `{"type": "deliverable", "deliverable": <entry>}`.

The activity hub (`GET /projects/{id}/activity`) listens here with `listen`; until it does, a
publish goes nowhere. Publish only after the write has committed, never from a dry run.
"""

import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager

from qsone.deliverables import store
from qsone.records.project import Records

Listener = Callable[[str, dict], None]  # (project id, event)
_listeners: list[Listener] = []
_held = threading.local()  # .events: what this thread publishes inside `held`, or None


def listen(listener: Listener) -> Callable[[], None]:
    """Calls `listener(project_id, event)` for every Deliverable event; returns the call that
    stops it."""
    _listeners.append(listener)
    return lambda: _listeners.remove(listener)


@contextmanager
def held() -> Iterator[None]:
    """Around one outer `rec.write`: what this thread publishes inside waits, and is sent when
    the block ends without an error (the write has committed), or dropped when it raises."""
    if getattr(_held, "events", None) is not None:  # inside another `held`: that one sends
        yield
        return
    _held.events = []
    try:
        yield
        found = _held.events
    finally:
        _held.events = None
    for project_id, event in found:
        _send(project_id, event)


def _send(project_id: str, event: dict) -> None:
    waiting = getattr(_held, "events", None)
    if waiting is not None:
        waiting.append((project_id, event))
        return
    for listener in list(_listeners):
        listener(project_id, event)


def publish(project_id: str, event: dict) -> None:
    """Any activity event from a worker thread to every listener (a file read in the background)."""
    _send(project_id, event)


def publish_deliverable(rec: Records, project_id: str, deliverable_id: str) -> None:
    """The Deliverable's list entry, as it is now, to every listener."""
    if not _listeners:
        return
    event = {"type": "deliverable", "deliverable": store.entry(rec, deliverable_id)}
    _send(project_id, event)
