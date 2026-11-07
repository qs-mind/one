"""ask_engineer (Plan 5, Task 3): the Lead QS asks the engineer several questions in one card
and waits for the answers (Mizan rule 10).

- The card is stored as pending before it is shown, as the gate's are, so a restart withdraws
  it and the redone call asks again. While it waits, no model is called.
- The questions are in the engineer's language (the Brief's) and in plain QS words: a question
  that shows or asks for an internal id goes back to the model to reword.
- The answers come back with the card as their source (`card:<id>`), dated the day they were
  given, so a number the engineer gives is recorded with the card as its evidence (`answered`).

Importing this module registers the tool. No PydanticAI here."""

import json
import re
from datetime import datetime
from typing import Annotated
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from qsone import copy
from qsone.engine.store import Store
from qsone.engine.tools import ModelRetry, Tool, ToolContext, register
from qsone.engine.types import Card, read_answer
from qsone.records.arabic import normalise
from qsone.tools.cite import SourceRef, render

MAX_QUESTIONS = 20  # in one card (Mizan rule 10)
SENT = "sent"  # the card's one option: the engineer sends every answer at once

# An internal id: a long hex id, a UUID, a snake_case "…_id", or "<thing> id" in words.
_ID = re.compile(
    r"(?=[0-9]*[a-f])[0-9a-f]{16,}"
    r"|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}"
    r"|\b[a-z]+_ids?\b"
    r"|\b(?:file|chunk|source|item|number|card|brief|run|calc|calculation|deliverable|import)"
    r"\s+ids?\b",
    re.IGNORECASE,
)
_NO_IDS = (
    "never show the engineer an id or ask for one: ids are yours, from tool results. Name the "
    "file, sheet, page or item as the engineer knows it (its name, code or description)"
)
_ARABIC = re.compile(r"[؀-ۿݐ-ݿࢠ-ࣿﭐ-﷿ﹰ-﻿]")
_LATIN = re.compile(r"[A-Za-z]")
_LANGUAGE = {"ar": "Arabic", "en": "English"}

Line = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


def _plain(value: str) -> str:
    if _ID.search(value):
        raise ValueError(_NO_IDS)
    return value


class Question(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str = Field(min_length=1, max_length=40, pattern=r"^[A-Za-z0-9_-]+$")
    text: str = Field(min_length=1, max_length=1000)
    options: list[Line] = Field(default_factory=list)
    free_text: bool = False

    @field_validator("text")
    @classmethod
    def _text(cls, value: str) -> str:
        return _plain(value)

    @field_validator("options")
    @classmethod
    def _options(cls, value: list[str]) -> list[str]:
        if len(value) == 1 or len(value) > 6:
            raise ValueError("give no options, or 2 to 6")
        if len(set(value)) != len(value):
            raise ValueError("an option appears twice")
        return [_plain(v) for v in value]


class AskArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    questions: list[Question] = Field(min_length=1, max_length=MAX_QUESTIONS)

    @field_validator("questions")
    @classmethod
    def _ids(cls, value: list[Question]) -> list[Question]:
        seen: set[str] = set()
        for q in value:
            if q.id in seen:
                raise ValueError(f"the id «{q.id}» is used twice; give each question its own id")
            seen.add(q.id)
        return value


_EXAMPLE = {
    "questions": [
        {
            "id": "q1",
            "text": "الخرسانة جاهزة ولا خلط في الموقع؟",
            "options": ["جاهزة", "خلط في الموقع"],
        },
        {"id": "q2", "text": "سعر طن الأسمنت اللي عندك كام، وتاريخه إيه؟", "free_text": True},
    ]
}

_DOC = f"""Ask the engineer what only they can answer, and wait: their choice, a rate no file \
gives, a missing document. Look in the records first.
- questions: all in one call ({MAX_QUESTIONS} at most), each with an id ("q1", …), its text, \
and 2 to 6 options, or free_text: true.
- Write in the engineer's language, in plain QS words. Never show or ask for an id: name the \
file or item as the engineer knows it.
Returns the answers by id, with the card as source and date for add_source.
Example:
{json.dumps(_EXAMPLE, ensure_ascii=False)}"""


def _language(text: str) -> str | None:
    arabic, latin = len(_ARABIC.findall(text)), len(_LATIN.findall(text))
    if arabic == latin:
        return None
    return "ar" if arabic > latin else "en"


def _check_language(ctx: ToolContext, args: AskArgs) -> None:
    wanted = _language(ctx.store.brief(ctx.brief_id)["text"])
    if wanted is None:
        return
    for q in args.questions:
        found = _language(q.text)
        if found is not None and found != wanted:
            raise ModelRetry(
                f"ask_engineer: question «{q.id}» is in {_LANGUAGE[found]}; write every "
                f"question in {_LANGUAGE[wanted]}, the engineer's language (the Brief's). "
                f"Example: {json.dumps(_EXAMPLE, ensure_ascii=False)}"
            )


def answered(store: Store, card_id: str) -> dict | None:
    """A question card the engineer answered, as evidence: {"card_id", "questions", "answers"
    (by question id), "dated" (the local day it was answered), "read" (local "YYYY-MM-DD
    HH:MM")}. None when there is no such card in this Records file, it is not a question card,
    or it is not settled (still waiting, or withdrawn)."""
    with store.rec.read() as c:
        row = c.execute(
            "SELECT card, choice, settled_at FROM approvals WHERE id = ? AND status = 'settled'",
            (card_id,),
        ).fetchone()
    if row is None:
        return None
    d = json.loads(row[0])
    if d["kind"] != "question":
        return None
    card = Card(**{**d, "options": tuple(d["options"])})
    moment = datetime.fromisoformat(row[2]).astimezone()
    return {
        "card_id": card_id,
        "questions": list((card.payload or {}).get("questions") or ()),
        "answers": read_answer(card, row[1])["answers"],
        "dated": moment.date().isoformat(),
        "read": moment.strftime("%Y-%m-%d %H:%M"),
    }


async def _ask(ctx: ToolContext, args: AskArgs) -> str:
    brief = ctx.store.brief(ctx.brief_id)["text"]

    # Compare the question against the whole Brief: a requested sub-fact can
    # be a small part of a multi-part engineer request.
    framing = set(
        normalise(
            "what is are the a an and or can could would you me tell give show please "
            "how many much in on of from all every this that to for does do "
            "ما هو هي هل ممكن قول لي لو سمحت من فضلك ايه كام في من علي ده دي"
        ).split()
    )
    extensions = {"dwg", "dxf", "pdf", "xlsx", "xls", "csv", "docx", "doc"}

    def tokens(text: str) -> set[str]:
        words = normalise(text).split()
        # Fold regular English plurals, including block labels (BREAKERS).
        return {
            word[:-1] if word.isascii() and word.endswith("s") and not word.endswith("ss") else word
            for word in words
            if word not in framing and word not in extensions
        }

    original = tokens(brief)
    for q in args.questions:
        proposed = tokens(q.text)
        overlap = len(original & proposed) / max(1, len(proposed))
        owned_rate = bool(proposed & tokens("your عندك سعرك اسعارك")) and bool(
            proposed & tokens("rate rates price prices سعر اسعار سعرك اسعارك")
        )
        # These ask for an engineer action/decision, rather than a fact in files.
        decision = bool(
            proposed
            & tokens(
                "choose prefer choice approve approval permission upload attach provide "
                "supply send تفضل اختيارك اختار توافق موافق موافقه ارفع ابعت ارسل ارفق وفر"
            )
        )
        choice = bool(
            re.search(
                r"\b(which|whether)\b.*\b(should|use|price|version|versions|option|options)\b"
                r"|\b(?:or|ولا|ام)\b",
                normalise(q.text, stem=False),
            )
        )
        if proposed and overlap >= 0.6 and not (owned_rate or decision or choice):
            raise ModelRetry(copy.QUESTION_OWN_REQUEST["en"])
    _check_language(ctx, args)
    questions = [q.model_dump(exclude_defaults=True) for q in args.questions]
    card = Card(
        id=uuid4().hex,
        kind="question",
        title=copy.fill(copy.QUESTION_TITLE, agent=ctx.agent.name),
        detail=copy.QUESTION_DETAIL,
        options=(SENT,),
        payload={"questions": questions},
    )
    ctx.store.add_approval(ctx.brief_id, card, run_id=ctx.run_id)  # stored before it is shown
    value = await ctx.host.ask(card)
    try:
        ctx.store.settle(card.id, value)
    except LookupError:
        pass  # the Brief Runner saved the answer itself
    found = answered(ctx.store, card.id)
    assert found is not None  # just settled
    cite = (
        "To record a number from an answer: add_source "
        f'{{"kind": "engineer", "card_id": "{card.id}", "question": "<its id>"}}; '
        f"it is dated {found['dated']}, the day of the answer."
    )
    return render(
        "The engineer answered.",
        data={"answers": found["answers"]},
        notes=[cite],
        sources=[
            SourceRef(
                ref=f"card:{card.id}",
                title="The engineer's answers",
                read=found["read"],
                dated=found["dated"],
            )
        ],
    )


register(
    Tool(
        name="ask_engineer",
        description=_DOC,
        args=AskArgs,
        risk="read",
        run=_ask,
        activity=lambda _: copy.TOOL_WORDS["ask_engineer"],
        lead_only=True,
        example=_EXAMPLE,
        roles=frozenset({"lead"}),
        group="engineer",
    )
)
