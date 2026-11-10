"""A tender's team as the screen sees it now (`TeamMember`), and its `member` events.

- `state`: `working` while one of the member's runs works; `waiting` for the Lead while a card in
  the tender waits for the engineer; `failed` when its last run failed and nothing has run since;
  else `idle`. `doing` is the run's Progress Line, or what it waits for.
- A `member` event follows the Progress Lines, so each member's is published at most once a
  second, and the last state is always sent (`Throttle`)."""

import asyncio
import math
import time
from collections.abc import Callable

from qsone import activity, copy
from qsone import phase1_contract as c
from qsone.engine import identity
from qsone.records.project import Records, RecordsError

_WORKING = ("thinking", "working")


def _live(engine, project_id: str) -> dict[str, tuple[str, dict | None]]:
    """(state, doing) of each member with a run in the tender's running Briefs."""
    found: dict[str, tuple[str, dict | None]] = {}
    if engine is None:
        return found
    for brief in engine._in(project_id):
        if brief.finished:
            continue
        cards = [card for card, _ in brief.waiting.values()]
        for agent in brief.agents.values():
            if agent.state in _WORKING:
                found[agent.spec.id] = ("working", agent.line)
            elif agent.state == "failed":
                found[agent.spec.id] = ("failed", None)
        if cards:
            what = copy.fill(copy.MEMBER_WAITING_FOR, what=cards[0].title)
            found[identity.LEAD] = ("waiting", what)
        elif any(a.state == "waiting" for a in brief.agents.values() if a.spec.id == identity.LEAD):
            found[identity.LEAD] = ("waiting", copy.MEMBER_WAITING)
    return found


def _last_failed(rec: Records, member_id: str) -> bool:
    with rec.read() as conn:
        row = conn.execute(
            "SELECT status FROM agent_runs WHERE json_extract(spec, '$.id') = ?"
            " ORDER BY created_at DESC, rowid DESC LIMIT 1",
            (member_id,),
        ).fetchone()
    return row is not None and row[0] == "failed"


def team_members(engine, rec: Records, engineer: Records) -> list[c.TeamMember]:
    """`GET /projects/{id}/members`: the Lead, the Checking QS, then the others as they joined."""
    live = _live(engine, rec.id)
    found = []
    for member, proposed in identity.members(rec, engineer):
        state, doing = live.get(member.id) or (
            ("failed", None) if _last_failed(rec, member.id) else ("idle", None)
        )
        found.append(
            c.TeamMember.model_validate(
                member.model_dump() | {"state": state, "doing": doing, "proposed": proposed}
            )
        )
    return found


class Throttle:
    """At most one send a second per key; a send that comes sooner waits for the second to end,
    and then sends what the last `make` given gives at that moment (the last state)."""

    def __init__(self, clock: Callable[[], float] = time.monotonic, gap: float = 1.0) -> None:
        self.clock = clock
        self.gap = gap
        self._last: dict[tuple[str, str], float] = {}
        self._due: dict[tuple[str, str], Callable[[], dict | None]] = {}

    def send(self, channel: str, key: str, make: Callable[[], dict | None]) -> None:
        """Call it on the core's event loop; elsewhere it sends nothing (the screen reloads the
        members on the `plan` and `brief` events anyway)."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        slot = (channel, key)
        if slot in self._due:
            self._due[slot] = make
            return
        wait = self._last.get(slot, -math.inf) + self.gap - self.clock()
        self._due[slot] = make
        if wait <= 0:
            self._fire(channel, slot)
        else:
            loop.call_later(wait, self._fire, channel, slot)

    def _fire(self, channel: str, slot: tuple[str, str]) -> None:
        make = self._due.pop(slot)
        self._last[slot] = self.clock()
        event = make()
        if event is not None:
            activity.publish(channel, event)


EVENTS = Throttle()


def changed(engine, project_id: str | None, member_id: str) -> None:
    """A member joined, or its state or doing changed, or it became permanent."""
    if engine is None or project_id is None:
        return

    def make() -> dict | None:
        try:
            rec = engine.projects.get(project_id)
            engineer = engine.engineer_records()
        except RecordsError:
            return None
        for member in team_members(engine, rec, engineer):
            if member.id == member_id:
                return c.MemberEvent(type="member", member=member).model_dump(mode="json")
        return None  # a run that is no member of the team (a specialist of an older Brief)

    EVENTS.send(project_id, member_id, make)
