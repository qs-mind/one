"""The activity hub: what the agents and the Deliverables of a project are doing, as it happens.

`publish(project_id, event)` hands one JSON-ready event to every open subscriber of that project;
`subscribe(project_id)` gives them as they come. `GET /projects/{id}/activity` serves them as
server-sent events (Plan 7's `ActivityEvent`: `agent`, `agent-gone`, `desk`, `waiting`; Plan 6
adds `deliverable`). Nothing is kept: a screen that reconnects reloads the lists first.

The General chat has no project: its events go under "general"."""

import asyncio
from collections.abc import AsyncIterator, Callable

_QUEUE_LIMIT = 1000  # events waiting for one slow subscriber; older ones are dropped


class Hub:
    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue]] = {}

    def publish(self, project_id: str, event: dict) -> None:
        """Never blocks. Call it on the core's event loop."""
        for queue in tuple(self._subscribers.get(project_id, ())):
            if queue.full():
                queue.get_nowait()
            queue.put_nowait(event)

    async def subscribe(self, project_id: str) -> AsyncIterator[dict]:
        queue: asyncio.Queue = asyncio.Queue(_QUEUE_LIMIT)
        self._subscribers.setdefault(project_id, set()).add(queue)
        try:
            while True:
                yield await queue.get()
        finally:
            found = self._subscribers.get(project_id)
            if found is not None:
                found.discard(queue)
                if not found:
                    del self._subscribers[project_id]


HUB = Hub()
# Told of every event as it is published, on the publisher's thread (Home's `home_pulse`).
LISTENERS: list[Callable[[str, dict], None]] = []


def publish(project_id: str, event: dict) -> None:
    HUB.publish(project_id, event)
    for listen in tuple(LISTENERS):
        listen(project_id, event)


def subscribe(project_id: str) -> AsyncIterator[dict]:
    return HUB.subscribe(project_id)
