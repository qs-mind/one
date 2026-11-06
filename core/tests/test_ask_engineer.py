"""ask_engineer (Plan 5, Task 3): several questions in one card, the Brief waits with no model
tokens spent, and the answers come back with the card as their source.

Scripted models only; synthetic «عينة» data only; no test reaches the web or a real AI."""

import asyncio
import json

import pytest
from pydantic_ai import ModelRetry
from pydantic_ai.messages import ModelRequest, ToolReturnPart

from qsone import copy
from qsone.engine import agents
from qsone.engine.tools import REGISTRY, call
from qsone.engine.types import Asked, Card, Progress, answer_value
from qsone.tools import engineer
from tests.engine_fakes import call as tool_call
from tests.engine_fakes import scripted
from tests.engine_fakes import text as said
from tests.fakes_tools import tool_ctx
from tests.team_samples import BRIEF
from tests.test_engine_runner import (  # noqa: F401 - the runner's fixtures
    finish,
    links,
    make_engine,
    no_budget_card,
    project,
    registry,
    started,
    states,
    store_of,
    until,
)

CONCRETE = {"id": "q1", "text": "الخرسانة جاهزة ولا موقع؟ - عينة", "options": ["جاهزة", "موقع"]}
CEMENT = {"id": "q2", "text": "سعر طن الأسمنت عندك كام؟ - عينة", "free_text": True}
TWO = {"questions": [CONCRETE, CEMENT]}


def sent(card, **answers) -> str:
    return answer_value(card, "sent", answers=answers)


async def asked(host):
    """The card the tool is waiting on."""
    for _ in range(500):
        if host.cards:
            return host.cards[-1]
        await asyncio.sleep(0.002)
    raise AssertionError("no card was asked")


async def test_questions_wait_then_return_the_answers(rec):
    ctx = tool_ctx(rec)
    host = ctx.host
    host.answers = {"question": json.dumps({"choice": "sent", "answers": {"q1": "جاهزة"}})}
    out = await call("ask_engineer", {"questions": [CONCRETE]}, ctx)
    [card] = host.cards
    assert '"q1": "جاهزة"' in out and f"card:{card.id}" in out
    assert card.kind == "question" and card.options == ("sent",)
    assert card.payload == {"questions": [CONCRETE]}
    assert card.title == copy.fill(copy.QUESTION_TITLE, agent=copy.ROLE_LEAD)
    assert card.detail == copy.QUESTION_DETAIL
    with rec.read() as c:
        status, run_id = c.execute(
            "SELECT status, run_id FROM approvals WHERE id = ?", (card.id,)
        ).fetchone()
    assert status == "settled" and run_id == ctx.run_id  # stored before it was shown


async def test_the_brief_waits_for_every_answer(rec):
    ctx = tool_ctx(rec)
    task = asyncio.create_task(call("ask_engineer", TWO, ctx))
    card = await asked(ctx.host)
    assert [c.id for c in ctx.store.pending(ctx.brief_id)] == [card.id]
    assert not task.done()
    ctx.host.settle(card.id, sent(card, q1="موقع", q2="3950 جنيه"))
    out = await task
    data = json.loads(out.split("data: ", 1)[1].splitlines()[0])
    assert data == {"answers": {"q1": "موقع", "q2": "3950 جنيه"}}
    assert ctx.store.pending(ctx.brief_id) == []


def test_the_job_card_says_it_waits_for_the_engineer():
    tool = REGISTRY["ask_engineer"]
    assert tool.activity(tool.args.model_validate(TWO)) == copy.TOOL_WORDS["ask_engineer"]
    assert tool.risk == "read" and not tool.untrusted and not tool.writes


@pytest.mark.parametrize(
    ("questions", "said_words"),
    [
        ([{"id": f"q{i}", "text": f"سؤال {i} - عينة؟"} for i in range(21)], ("questions", "20")),
        ([], ("questions", "1")),
        ([CONCRETE | {"options": ["جاهزة"]}], ("options", "2 to 6")),
        ([CONCRETE | {"options": [f"اختيار {i}" for i in range(7)]}], ("options", "2 to 6")),
        ([CONCRETE | {"options": ["جاهزة", "جاهزة"]}], ("options", "twice")),
        ([CONCRETE, CONCRETE | {"text": "سؤال تاني - عينة؟"}], ("questions", "q1")),
        ([{"id": "q1", "text": "  "}], ("text",)),
    ],
)
async def test_a_wrong_shape_is_a_model_retry(rec, questions, said_words):
    ctx = tool_ctx(rec)
    with pytest.raises(ModelRetry) as e:
        await call("ask_engineer", {"questions": questions}, ctx)
    for word in said_words:
        assert word in str(e.value)
    assert ctx.host.cards == []  # nothing reached the engineer


@pytest.mark.parametrize(
    "text",
    [
        "ابعتلي file_id بتاع المقايسة - عينة؟",
        "إيه رقم الملف 3f9a1c2b7d4e4f60a1b2c3d4e5f60718؟ - عينة",
        "الـ source id بتاع العرض كام؟ - عينة",
    ],
)
async def test_never_asks_the_engineer_for_an_internal_id(rec, text):
    ctx = tool_ctx(rec)
    with pytest.raises(ModelRetry) as e:
        await call("ask_engineer", {"questions": [{"id": "q1", "text": text}]}, ctx)
    assert "id" in str(e.value) and "never" in str(e.value)
    assert ctx.host.cards == []


async def test_an_option_naming_an_id_is_refused_too(rec):
    ctx = tool_ctx(rec)
    question = CONCRETE | {"options": ["chunk_id 12", "موقع"]}
    with pytest.raises(ModelRetry):
        await call("ask_engineer", {"questions": [question]}, ctx)


async def test_questions_come_in_the_engineers_language(rec):
    ctx = tool_ctx(rec)  # the Brief is in Arabic
    english = {"id": "q1", "text": "Is the concrete ready-mixed or site-mixed? - sample"}
    with pytest.raises(ModelRetry) as e:
        await call("ask_engineer", {"questions": [english]}, ctx)
    assert "Arabic" in str(e.value)
    ctx.brief_id = ctx.store.new_brief(rec.id, "Price the BOQ - sample")  # now in English
    ctx.host.answers = {"question": "sent"}
    await call("ask_engineer", {"questions": [english]}, ctx)
    with pytest.raises(ModelRetry) as e:
        await call("ask_engineer", {"questions": [CONCRETE]}, ctx)
    assert "English" in str(e.value)


async def test_card_answer_is_evidence(rec):
    ctx = tool_ctx(rec)
    task = asyncio.create_task(call("ask_engineer", TWO, ctx))
    card = await asked(ctx.host)
    assert engineer.answered(ctx.store, card.id) is None  # not answered yet
    ctx.host.settle(card.id, sent(card, q1="موقع", q2="3950"))
    out = await task
    found = engineer.answered(ctx.store, card.id)
    assert found["answers"] == {"q1": "موقع", "q2": "3950"}
    assert found["questions"] == TWO["questions"]
    assert f"dated {found['dated']}" in out and f"read {found['read']}" in out
    assert f'"card_id": "{card.id}"' in out  # how to cite it, so no id is asked of anyone
    source = await call(
        "add_source", {"kind": "engineer", "card_id": card.id, "question": "q2"}, ctx
    )
    assert "source_id" in source and f'"dated": "{found["dated"]}"' in source
    assert engineer.answered(ctx.store, "no-such-card") is None


async def test_a_withdrawn_or_other_card_is_not_an_answer(rec):
    ctx = tool_ctx(rec)
    task = asyncio.create_task(call("ask_engineer", TWO, ctx))
    card = await asked(ctx.host)
    ctx.store.withdraw_pending(ctx.brief_id)
    assert engineer.answered(ctx.store, card.id) is None
    task.cancel()
    approval = Card("c-online", "online", copy.ROLE_LEAD, copy.ROLE_LEAD, ("yes", "brief", "no"))
    ctx.store.add_approval(ctx.brief_id, approval, run_id=ctx.run_id)
    ctx.store.settle(approval.id, "yes")
    assert engineer.answered(ctx.store, approval.id) is None  # only a question card answers


async def test_question_text_not_readable_on_disk(rec, data_dir):
    ctx = tool_ctx(rec)
    secret_q = {"id": "q1", "text": "سعر الحديد السري عندك كام؟ - عينة", "free_text": True}
    task = asyncio.create_task(call("ask_engineer", {"questions": [secret_q]}, ctx))
    card = await asked(ctx.host)
    ctx.host.settle(card.id, sent(card, q1="٤١٠٠٠ جنيه سري"))
    await task
    needles = ["الحديد السري".encode(), "جنيه سري".encode()]
    for path in data_dir.rglob("*"):
        if path.is_file():
            data = path.read_bytes()
            assert not any(n in data for n in needles), path


def test_the_lead_asks_and_the_checking_qs_does_not():
    assert "ask_engineer" in agents.lead_spec().tools
    assert "ask_engineer" not in agents.checker_spec().tools
    assert REGISTRY["ask_engineer"].lead_only  # a specialist asks through the Lead


# A Brief that waits on a question survives a restart -------------------------------------------


def _returns(messages) -> list[str]:
    return [
        p.content
        for m in messages
        if isinstance(m, ModelRequest)
        for p in m.parts
        if isinstance(p, ToolReturnPart) and p.tool_name == "ask_engineer"
    ]


async def test_kill_and_continue_while_a_question_waits(make_engine, project, data_dir):  # noqa: F811
    lead1 = scripted(tool_call("ask_engineer", TWO))
    e1 = await started(make_engine(links(lead=lead1)))
    brief = await e1.start_brief(project, BRIEF)
    store = store_of(e1, project)
    await until(lambda: store.pending(brief))
    [old] = store.pending(brief)
    assert old.kind == "question" and old.payload == TWO
    assert store.brief(brief)["status"] == "waiting_engineer"
    for _ in range(5):
        await asyncio.sleep(0.01)
    assert lead1.calls == 1  # no model request while the engineer is asked
    await e1.crash()
    needles = [CONCRETE["text"].encode(), CEMENT["text"].encode()]
    for path in data_dir.rglob("*"):  # the Checkpoint and the card are in the encrypted file
        if path.is_file():
            assert not any(n in path.read_bytes() for n in needles), path

    lead2 = scripted(tool_call("ask_engineer", TWO), said("الخرسانة موقع - عينة"))
    e2 = await started(make_engine(links(lead=lead2)))
    store = store_of(e2, project)
    await e2.continue_brief(brief)
    await until(lambda: store.pending(brief))
    [new] = store.pending(brief)
    assert new.id != old.id and new.kind == "question" and new.payload == TWO
    with store.rec.read() as c:
        (status,) = c.execute("SELECT status FROM approvals WHERE id = ?", (old.id,)).fetchone()
    assert status == "withdrawn"
    await e2.answer(new.id, sent(new, q1="موقع", q2="3950 جنيه"))
    events = await finish(e2, brief)
    assert states(events)[-1] == "done"
    assert "waiting_engineer" in states(events)
    assert any(isinstance(e, Asked) and e.card.id == new.id for e in events)
    assert not any(isinstance(e, Progress) and e.text == copy.DOING_ASK for e in events)
    card_at = next(i for i, e in enumerate(events) if isinstance(e, Asked) and e.card.id == new.id)
    waiting_at = next(
        i for i, e in enumerate(events) if getattr(e, "state", None) == "waiting_engineer"
    )
    assert card_at < waiting_at
    [answer] = _returns(lead2.seen[-1])
    assert '"q1": "موقع"' in answer and f"card:{new.id}" in answer
