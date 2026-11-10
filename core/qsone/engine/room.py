"""The team room (Phase 1, C6): one conversation per tender, separate from the engineer's, where
the members assign, ask, object and resolve, citing the places in the tender's files. Its
messages are `team.messages`; routes 17 and 18 of the contract are here.

- A member writes with `send_message` (`member_says`). A message flagged as a money decision
  goes up to the engineer: a question card, and the Lead's message to the engineer with
  `raised` set to it. An objection is a round of a disagreement: after two rounds not settled,
  the next objection goes to the engineer with both views and their evidence, the same rule as
  the Checking QS's two rounds. The answer goes back to the member as its tool result.
- After a cut-off the store withdraws the waiting card (`messages.cards_withdrawn`): the Lead's
  message goes back to `raised` null, and the redone call reuses both messages and raises the
  Lead's again with the new card.
- Raising a Finding writes the Lead's message to the engineer (`finding_raised`); deciding it
  marks that message answered (`finding_decided`).
- The engineer's message (route 18) goes to the Lead only: a steer when the Lead's work runs in
  the tender, otherwise ONE starts the Lead's work on it. It never reaches the Checking QS.
- Every message written, or whose `raised` changes, is a `room` event; one written during a
  Brief is also a `data-room` part of its reply."""

import asyncio
import logging
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from qsone import copy
from qsone import phase1_contract as c
from qsone.engine import identity
from qsone.engine.team import messages
from qsone.engine.team.common import _ask, _join
from qsone.engine.team.stored import specialists
from qsone.engine.tools import ToolContext
from qsone.engine.types import Card, Text, read_answer
from qsone.home_block import project_block
from qsone.journey import setup_state
from qsone.records.project import RecordsError

log = logging.getLogger(__name__)
ROUNDS = 2  # objections a disagreement may take in the room before it goes to the engineer
SENT = "sent"  # a question card's one option (as ask_engineer's)


# The members' messages -------------------------------------------------------------------------


def _name(ctx: ToolContext, member_id: str) -> Text:
    """A member's short name: a fixed member's, a specialist's of this Brief, or the tender's."""
    fixed = {identity.LEAD: copy.LEAD_NAME, identity.CHECKER: copy.CHECKER_NAME}
    if member_id in fixed:
        return fixed[member_id]
    for spec in specialists(ctx.store, ctx.brief_id):
        if spec.id == member_id:
            return spec.name
    found = identity.project_member(ctx.rec, member_id)
    return found[0]["name"] if found else {"en": member_id, "ar": member_id}


def _show(ctx: ToolContext, message: dict) -> dict:
    """The room and the reply are told of the message."""
    ctx.host.emit(messages.part(ctx.brief_id, message))
    messages.publish(ctx.rec.id, [message])
    return message


async def _raise(ctx: ToolContext, card: Card, lead_message: dict) -> str:
    """Asks the card; the Lead's message follows it: raised, answered, or back to null when the
    card is withdrawn (the Brief stopped or was cut off)."""
    rec, message_id = ctx.rec, lead_message["id"]
    _show(ctx, messages.set_raised(rec, message_id, {"id": card.id, "answered": False}))
    try:
        value = await _ask(ctx, card)
    except BaseException:  # in this process; after a cut-off the store's withdrawal does it
        for message in messages.withdrawn(rec, [card.id]):
            _show(ctx, message)
        raise
    _show(ctx, messages.set_raised(rec, message_id, {"id": card.id, "answered": True}))
    return value


def _to_engineer(ctx: ToolContext, said: dict, text: str, sources: list) -> dict:
    """The Lead's message to the engineer for what `said` raises: `said` itself when the Lead
    wrote it to the engineer."""
    if said["from_id"] == identity.LEAD and said["to_id"] == messages.ENGINEER:
        return said
    thread = messages.thread_of(ctx.rec, said["id"])
    again = messages.withdrawn_raise(ctx.rec, ctx.brief_id, thread)
    if again is not None:  # the redone call raises the cut-off message again
        return again
    lead = messages.write(
        ctx.rec, from_id=identity.LEAD, to_id=messages.ENGINEER, text=text, sources=sources,
        brief_id=ctx.brief_id, reply_to=said["id"],
    )  # fmt: skip
    return _show(ctx, lead)


async def _money(ctx: ToolContext, said: dict) -> dict:
    agent = _name(ctx, said["from_id"])
    question = {"id": "answer", "text": said["text"], "free_text": True}
    card = Card(
        uuid4().hex,
        "question",
        copy.fill(copy.ROOM_MONEY_TITLE, agent=agent),
        copy.ROOM_MONEY_DETAIL,
        (SENT,),
        payload={"questions": [question]},
    )
    lead = _to_engineer(ctx, said, said["text"], said["sources"])
    value = await _raise(ctx, card, lead)
    answer = read_answer(card, value)["answers"].get("answer")
    return {"sent": said["id"], "to": "engineer", "raised_to_engineer": True, "answer": answer}


def _evidence(sources: list) -> str:
    return "\n".join(f"- {s['file_name']} {s['locator']}" for s in sources)


async def _disagreement(ctx: ToolContext, said: dict, views: list) -> dict:
    """Both views (each side's latest objection, with every place it cited) to the engineer."""
    latest: dict[str, tuple[str, list]] = {}
    for from_id, text, sources in views:
        cited = latest.get(from_id, ("", []))[1]
        latest[from_id] = (text, cited + [s for s in sources if s not in cited])
    sides = list(latest)[-2:]
    names = [_name(ctx, side) for side in sides]
    labels = [copy.fill(copy.ROOM_VIEW, agent=name) for name in names]
    lang = setup_state.language()
    pieces: list[Text | str] = [copy.ROOM_DISAGREE_DETAIL]
    for label, side in zip(labels, sides, strict=True):
        text, sources = latest[side]
        pieces += [label, text, _evidence(sources) or copy.ROOM_NO_SOURCE]
    question = {
        "id": "view",
        "text": copy.ROOM_DISAGREE_ASK[lang],
        "options": [label[lang] for label in labels],
    }
    pair = {"first": names[0], "second": names[-1]}
    card = Card(
        uuid4().hex,
        "question",
        copy.fill(copy.ROOM_DISAGREE_TITLE, **pair),
        _join(*pieces),
        (SENT,),
        payload={"questions": [question]},
    )
    raised = copy.fill(copy.ROOM_DISAGREE_RAISED, **pair)[lang]
    evidence = [s for _, sources in latest.values() for s in sources]
    lead = _to_engineer(ctx, said, raised, evidence)
    value = await _raise(ctx, card, lead)
    chosen = read_answer(card, value)["answers"].get("view")
    settled = copy.fill(copy.ROOM_DISAGREE_SETTLED, view=chosen or "")[lang]
    resolve = messages.write(
        ctx.rec, from_id=identity.LEAD, to_id=messages.TEAM, text=settled,
        brief_id=ctx.brief_id, kind="resolve", reply_to=said["id"],
    )  # fmt: skip
    _show(ctx, resolve)
    return {"sent": said["id"], "engineer_decides": True, "engineer_chose": chosen}


async def member_says(ctx: ToolContext, args, message_id: str, to_id: str) -> dict | None:
    """`send_message` in a tender: the message in the room. When it goes up to the engineer
    (money, or a disagreement past two rounds), what the tool returns; None otherwise."""
    rec = ctx.rec
    if rec is None:  # the Home conversation has no room
        return None
    sources = messages.sources_of(rec, args.sources, args.finding_id)
    if args.money and ctx.agent.id == identity.LEAD:
        to_id = messages.ENGINEER
    said = messages.redone(
        rec, ctx.brief_id, from_id=ctx.agent.id, to_id=to_id, text=args.text, kind=args.kind
    ) or messages.write(
        rec, from_id=ctx.agent.id, to_id=to_id, text=args.text, sources=sources,
        brief_id=ctx.brief_id, kind=args.kind, reply_to=args.reply_to, message_id=message_id,
    )  # fmt: skip
    _show(ctx, said)
    if args.money:
        return await _money(ctx, said)
    if args.kind == "object":
        views = messages.objections(rec, messages.thread_of(rec, said["id"]))
        if len(views) > ROUNDS and len({side for side, _, _ in views}) > 1:
            return await _disagreement(ctx, said, views)
    return None


# Findings ---------------------------------------------------------------------------------------


def finding_raised(ctx: ToolContext, finding: dict) -> None:
    """The Lead's message to the engineer for a Finding it raised."""
    said = messages.write(
        ctx.rec, from_id=identity.LEAD, to_id=messages.ENGINEER, text=finding["text"],
        sources=finding["sources"], brief_id=ctx.brief_id, raised_id=finding["id"],
    )  # fmt: skip
    _show(ctx, said)


def finding_decided(rec, finding_id: str) -> None:
    """The engineer decided the Finding: the messages that raised it are answered."""
    messages.publish(rec.id, messages.answered(rec, finding_id))


# The routes -------------------------------------------------------------------------------------


def _refusals(*codes: int) -> dict:
    bad = c.Refusal | c.BodyProblem  # 422: the engineer's value, or a body the screen built wrongly
    return {code: {"model": bad if code == 422 else c.Refusal} for code in codes}


def _for_lead(message: dict) -> str:
    return (
        f"The engineer wrote in the team room (message {message['id']}): «{message['text']}». "
        "Take it as the engineer's direction and direct the team on it."
    )


def _show_in_brief(engine, brief_id: str, message: dict) -> None:
    try:
        engine._brief(brief_id).emit(messages.part(brief_id, message))
    except LookupError:
        pass  # it ended already: the stored reply shows the message


async def _to_lead(engine, rec, message: dict) -> None:
    """A steer when the Lead's work runs in the tender; otherwise the Lead's work on it."""
    from qsone.engine.runner import BriefBusy, NoAI

    steer = _for_lead(message)
    for _ in range(2):  # a Brief may start or end between the two calls
        busy = engine.active(rec.id, include_mapping=False)
        try:
            if busy is not None:
                await engine.steer(busy, steer)
                brief_id = busy
            else:
                said = copy.ROOM_BRIEF[setup_state.language()]
                brief_id = await engine.start_brief(rec.id, said, instruction=steer)
        except (LookupError, BriefBusy):
            continue
        except NoAI:
            break
        await asyncio.to_thread(messages.set_brief, rec, message["id"], brief_id)
        _show_in_brief(engine, brief_id, message)
        return
    log.warning("the engineer's room message reached no work of the Lead")


def router(projects, engine) -> APIRouter:
    r = APIRouter()

    @r.get(
        "/projects/{project_id}/room", response_model=c.RoomPage, responses=_refusals(404, 409, 422)
    )
    async def room(
        project_id: str,
        cursor: Annotated[str | None, Query(max_length=200)] = None,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
    ):
        try:
            rec = projects.get(project_id)
            return await asyncio.to_thread(messages.page, rec, cursor, limit)
        except RecordsError as e:
            return c.refusal(e.text, e.status, field=e.field)

    @r.post(
        "/projects/{project_id}/room",
        status_code=201,
        response_model=c.RoomMessage,
        responses=_refusals(404, 409, 422, 423),
    )
    async def say_in_room(project_id: str, body: c.RoomMessageIn):
        from qsone.engine.runner import NoAI

        try:
            rec = projects.get(project_id)
            if rec.archived_at is not None:
                raise RecordsError(copy.PROJECT_ARCHIVED, status=423)
            text = messages.checked_text(body.text)
            if engine.active(project_id, include_mapping=False) is None:  # work would start
                blocked = project_block(engine, rec)
                if blocked is not None:
                    return c.refusal(blocked["reason"])
                await engine.sheet()
            said = await asyncio.to_thread(
                messages.write, rec, from_id=messages.ENGINEER, to_id=messages.TEAM, text=text
            )
        except RecordsError as e:
            return c.refusal(e.text, e.status, field=e.field)
        except NoAI as none:
            return c.refusal(none.text)
        messages.publish(project_id, [said])
        await _to_lead(engine, rec, said)
        return JSONResponse(said, status_code=201)

    return r
