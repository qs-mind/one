"""Deliverable events on the activity stream: `{"type": "deliverable", "deliverable": <entry>}`.

The activity hub (`GET /projects/{id}/activity`) listens here with `listen`; until it does, a
publish goes nowhere. Publish only after the write has committed, never from a dry run.
"""

from collections.abc import Callable

from qsone.deliverables import store
from qsone.records.project import Records

Listener = Callable[[str, dict], None]  # (project id, event)
_listeners: list[Listener] = []


def listen(listener: Listener) -> Callable[[], None]:
    """Calls `listener(project_id, event)` for every Deliverable event; returns the call that
    stops it."""
    _listeners.append(listener)
    return lambda: _listeners.remove(listener)


def publish_deliverable(rec: Records, project_id: str, deliverable_id: str) -> None:
    """The Deliverable's list entry, as it is now, to every listener."""
    if not _listeners:
        return
    event = {"type": "deliverable", "deliverable": store.entry(rec, deliverable_id)}
    for listener in list(_listeners):
        listener(project_id, event)
