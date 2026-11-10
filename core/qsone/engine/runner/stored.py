import json
from datetime import datetime

from pydantic_ai.messages import ModelResponse, TextPart

from qsone import view
from qsone.deliverables import tools as outputs
from qsone.engine import agents, findings, general, numbers_guard
from qsone.engine.runner.engine import Engine
from qsone.engine.runner.histories import _load, _tool_results, lead_text
from qsone.engine.runner.truth_checks import _no_search_notice
from qsone.engine.store import Store
from qsone.engine.types import (
    Asked,
    Card,
    Data,
    Event,
    ModelChoice,
    Review,
    Reviewed,
    Settled,
    Status,
    TeamMessage,
    TextDelta,
    Unsourced,
)
from qsone.engine.worklog import WorkLog
from qsone.journey import understand


def reply_id(brief_id: str) -> str:
    """The stored id of a Brief's reply: the stream's `start.messageId`."""
    return f"{brief_id}-reply"


def question_id(brief_id: str) -> str:
    return f"{brief_id}-question"


def _with_reports(messages: list[dict], rec) -> list[dict]:
    """`messages` with each files report (records/report.py) as one message from ONE, after the
    Briefs that began before it."""
    from qsone.records import report

    kept = report.kept(rec)
    if not kept:
        return messages
    with rec.read() as c:
        began = dict(c.execute("SELECT id, created_at FROM briefs").fetchall())
    out, reports = [], iter(kept)
    nxt = next(reports, None)
    for m in messages:
        if m["role"] == "user":
            at = began.get(m["id"].removesuffix("-question"), "")
            while nxt is not None and nxt["at"] < at:
                out.append(_report_message(nxt))
                nxt = next(reports, None)
        out.append(m)
    while nxt is not None:
        out.append(_report_message(nxt))
        nxt = next(reports, None)
    return out


def _report_message(found: dict) -> dict:
    part = {"type": "data-files_read", "id": found["id"], "data": {"lines": found["lines"]}}
    return {"id": f"files-{found['id']}", "role": "assistant", "parts": [part]}


def _first_said(history: bytes | None) -> datetime | None:
    """When the Lead first said something: its first response with words."""
    for m in _load(history):
        if isinstance(m, ModelResponse) and any(
            isinstance(p, TextPart) and p.content for p in m.parts
        ):
            return m.timestamp
    return None


def _stored_events(
    store: Store, brief: dict, engine: Engine, *, unfinished: bool = False
) -> list[Event]:
    """A Brief as events again, from what is stored: the Lead's words, the Coordination Room,
    the cards and their answers, the Deliverable cards, the Reviews, the unsourced marks and the
    state. A card asked before the Lead first spoke comes before its words, as it did live.
    `unfinished`: the Brief waits for Continue, so a card still pending shows as withdrawn (no
    one waits on it; Continue asks it again)."""
    brief_id = brief["id"]
    events: list[Event] = []
    runs = store.runs(brief_id)
    lead = next((r for r in runs if r["parent_id"] is None and r["spec"].role == "lead"), None)
    reply = lead_text(_load(lead["history"])) if lead is not None else ""
    said_at = _first_said(lead["history"]) if reply and lead is not None else None
    cleaned = json.loads(brief["worklog"]).get("truth") if brief["worklog"] else None
    if isinstance(cleaned, dict) and isinstance(cleaned.get("reply"), str):
        reply = cleaned["reply"]  # the reply as the core cleaned it then (no JSON, no ids)
    with store.rec.read() as c:
        approvals = c.execute(
            "SELECT card, status, choice, asked_at, settled_at FROM approvals"
            " WHERE brief_id = ? ORDER BY asked_at, rowid",
            (brief_id,),
        ).fetchall()
    before: list[Event] = []  # the cards asked before the Lead spoke (a prefix: oldest first)
    after: list[Event] = []
    for card_text, status, choice, asked_at, settled_at in approvals:
        d = json.loads(card_text)
        card = Card(**{**d, "options": tuple(d["options"])})
        early = said_at is not None and not after and datetime.fromisoformat(asked_at) < said_at
        found = before if early else after
        found.append(Asked(brief_id, card))
        if status == "settled":
            found.append(Settled(brief_id, card.id, choice, settled_at))
        elif status == "withdrawn" or (unfinished and status == "pending"):
            found.append(Data(brief_id, "card", card.id, {"status": "withdrawn"}))
    events += before
    if reply:
        events.append(TextDelta(brief_id, reply))
    if lead is not None and lead["history"]:
        returns = agents.tool_returns(lead["history"])
        events += general.stored_cards(brief_id, returns)
        events += understand.stored_cards(brief_id, returns)  # Plan 8's card
        events += findings.stored_parts(brief_id, returns)  # Phase 1: data-finding
        events += view.stored_views(store.rec, brief_id, lead["history"])  # decision 16.1
    for run in runs:  # the Deliverable cards, from whichever agent made them (Plan 6)
        if run["history"]:
            events += outputs.stored_cards(brief_id, agents.tool_returns(run["history"]))
    for m in store.team(brief_id):
        events.append(TeamMessage(brief_id, m["id"], m["sender"], m["recipient"], m["text"]))
    with store.rec.read() as c:
        reviews = c.execute(
            "SELECT r.deliverable_id, r.code, r.comments, r.checker, r.same_provider, r.round"
            " FROM reviews r JOIN deliverable_drafts d ON d.id = r.deliverable_id"
            " WHERE d.brief_id = ? ORDER BY r.at, r.rowid",
            (brief_id,),
        ).fetchall()
    events += after
    for deliverable_id, code, comments, choice, same, round_ in reviews:
        review = Review(
            code=code,
            comments=tuple(json.loads(comments)),
            checker=ModelChoice(**json.loads(choice)),
            same_provider=bool(same),
            round=round_,
        )
        events.append(Reviewed(brief_id, deliverable_id, review))
    said = json.loads(brief["worklog"]).get("truth") if brief["worklog"] else None
    said = said if isinstance(said, dict) else {}
    if reply and brief["status"] == "done":
        results = _tool_results(runs)
        marked = said.get("unsourced")  # as the core marked them then
        if marked is None:
            marked = numbers_guard.unsourced(reply, numbers_guard.known_values(results))
        if marked:
            events.append(Unsourced(brief_id, tuple(marked)))
        named = numbers_guard.sourced(reply, results)
        if named:
            events.append(Data(brief_id, "sourced", brief_id, {"numbers": named}))
    if brief["worklog"]:
        worklog = WorkLog.load(brief["worklog"], stopped_at=brief["updated_at"])
        worklog.ended = json.loads(brief["worklog"]).get("ended")
        events.append(Data(brief_id, "worklog", brief_id, worklog.as_json()))
        said = worklog.truth or {}  # the facts the core put beside the reply, as they were then
        if said.get("facts"):
            events.append(Data(brief_id, "facts", brief_id, said["facts"]))
        if said.get("no_search"):
            events.append(_no_search_notice(brief_id))
        if said.get("step_limit"):
            limit = {"text": said["step_limit"]}
            events.append(Data(brief_id, "notice", f"{brief_id}-step-limit", limit))
    events.append(Status(brief_id, brief["status"], brief["step"]))
    return events
