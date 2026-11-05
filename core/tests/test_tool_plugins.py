"""Plan 5's plug-in points in Plan 4's engine (Task 2): a risk that depends on the arguments,
cards with a payload (questions, tickable rows), the tool services, results with their sources,
and the default tool lists.

Synthetic «عينة» data only; no test calls a real AI or the web."""

import json
from dataclasses import replace
from decimal import Decimal
from types import SimpleNamespace

import httpx
import pytest
from pydantic import BaseModel

from qsone import copy
from qsone.engine import agents, costs
from qsone.engine.store import Store
from qsone.engine.tools import REGISTRY, Denied, Tool, call
from qsone.engine.types import BadAnswer, Card, answer_value, choice_of, read_answer
from qsone.tools import cite
from qsone.tools.cite import SourceRef
from qsone.tools.services import Services, services_for
from tests.conftest import AUTH, SECRET
from tests.engine_fakes import FakeSleep, scripted
from tests.engine_fakes import call as tool_call
from tests.fakes_tools import fake_services, tool_ctx
from tests.test_engine_routes import message, read_until
from tests.test_engine_runner import links

QUESTIONS = {
    "questions": [
        {"id": "q1", "text": "الخرسانة جاهزة ولا موقع؟ - عينة", "options": ["جاهزة", "موقع"]},
        {"id": "q2", "text": "سعر الأسمنت عندك كام؟ - عينة", "free_text": True},
    ]
}
ROWS = {
    "columns": [
        {"key": "description", "label": {"en": "Item", "ar": "البند"}},
        {"key": "rate", "label": {"en": "Rate", "ar": "السعر"}},
    ],
    "rows": [
        {"description": "أسمنت - عينة", "rate": "3950"},
        {"description": "رمل - عينة", "rate": "250"},
        {"description": "زلط - عينة", "rate": "310"},
    ],
    "tick": True,
}
TITLE = {"en": "Sample", "ar": "عينة"}


def question_card(card_id: str = "c-question") -> Card:
    return Card(card_id, "question", TITLE, TITLE, ("sent",), payload=QUESTIONS)


def rows_card(card_id: str = "c-rows") -> Card:
    return Card(card_id, "rows", TITLE, TITLE, ("keep", "no"), payload=ROWS)


# A risk that depends on the arguments ------------------------------------------------------------


class TargetArgs(BaseModel):
    target: str


@pytest.fixture
def by_target():
    """A sample tool whose risk is "outside" for a target named "send…", else "read"."""
    ran: list[str] = []

    async def run(ctx, args):
        ran.append(args.target)
        return "done - sample"

    tool = Tool(
        "by_target_sample",
        "Uses a target - sample.",
        TargetArgs,
        "read",
        run,
        lambda a: {"en": f"use {a.target}", "ar": f"يستخدم {a.target}"},
        risk_for=lambda a: "outside" if a.target.startswith("send") else "read",
    )
    REGISTRY[tool.name] = tool
    yield ran
    REGISTRY.pop(tool.name)


async def test_risk_for_decides_the_card(rec, by_target):
    ctx = tool_ctx(rec, answers={"outside": "no"})
    assert await call("by_target_sample", {"target": "read_inbox"}, ctx) == "done - sample"
    assert ctx.host.cards == []
    with pytest.raises(Denied):  # "outside" asks even before any untrusted text
        await call("by_target_sample", {"target": "send_email"}, ctx)
    [card] = ctx.host.cards
    assert card.kind == "outside" and card.options == ("yes", "no")
    assert "use send_email" in card.detail["en"]
    assert by_target == ["read_inbox"]


async def test_without_risk_for_nothing_changes(rec):
    async def run(ctx, args):
        return "fetched - sample"

    tool = Tool(
        "plain_online_sample",
        "Fetch - sample.",
        TargetArgs,
        "online",
        run,
        lambda a: {"en": a.target, "ar": a.target},
    )
    REGISTRY[tool.name] = tool
    try:
        ctx = tool_ctx(rec, answers={"online": "yes"})
        await call("plain_online_sample", {"target": "a"}, ctx)
        assert ctx.host.cards == []  # online asks only after untrusted text, as before
        untrusted = tool_ctx(rec, untrusted=True, answers={"online": "yes"})
        await call("plain_online_sample", {"target": "b"}, untrusted)
        assert [c.kind for c in untrusted.host.cards] == ["online"]
    finally:
        REGISTRY.pop(tool.name)


# Cards with a payload ---------------------------------------------------------------------------


def test_question_answers_need_every_question():
    card = question_card()
    with pytest.raises(BadAnswer) as missing:
        answer_value(card, "sent", answers={"q1": "جاهزة"})
    assert missing.value.field == "answers"
    with pytest.raises(BadAnswer):  # blank is not an answer
        answer_value(card, "sent", answers={"q1": "جاهزة", "q2": "  "})
    with pytest.raises(BadAnswer):  # an options-only question takes one of its options
        answer_value(card, "sent", answers={"q1": "مش عارف", "q2": "3950"})
    with pytest.raises(BadAnswer):  # no question by that id
        answer_value(card, "sent", answers={"q1": "جاهزة", "q2": "3950", "q9": "x"})
    value = answer_value(card, "sent", answers={"q1": "جاهزة", "q2": "3950 جنيه"})
    assert json.loads(value) == {
        "choice": "sent",
        "answers": {"q1": "جاهزة", "q2": "3950 جنيه"},
        "rows_ok": [],
    }
    assert choice_of(card, value) == "sent"
    assert read_answer(card, value)["answers"]["q2"] == "3950 جنيه"


def test_rows_answers_tick_rows_that_exist():
    card = rows_card()
    assert json.loads(answer_value(card, "keep", rows_ok=[2, 0]))["rows_ok"] == [0, 2]
    for bad in ([3], [-1], [0, 0], [True]):
        with pytest.raises(BadAnswer) as refused:
            answer_value(card, "keep", rows_ok=bad)
        assert refused.value.field == "rows_ok"
    refused_all = json.loads(answer_value(card, "no", rows_ok=[0, 1]))
    assert refused_all == {"choice": "no", "answers": {}, "rows_ok": []}  # "no" keeps nothing
    with pytest.raises(ValueError):
        answer_value(card, "maybe")


def test_a_card_without_payload_settles_as_before():
    card = Card("c1", "outside", TITLE, TITLE, ("yes", "no"))
    assert answer_value(card, "yes", answers={"q": "ignored"}, rows_ok=[0]) == "yes"
    assert choice_of(card, "yes") == "yes"
    assert read_answer(card, "no") == {"choice": "no", "answers": {}, "rows_ok": []}
    with pytest.raises(ValueError):
        answer_value(card, "maybe")


def test_payload_cards_are_stored_with_their_payload(rec):
    store = Store(rec, project_id=rec.id)
    brief = store.new_brief(rec.id, "سؤال - عينة")
    store.add_approval(brief, question_card())
    store.add_approval(brief, rows_card())
    assert store.pending(brief) == [question_card(), rows_card()]
    with pytest.raises(ValueError):
        store.settle("c-rows", json.dumps({"choice": "maybe", "answers": {}, "rows_ok": []}))
    store.settle("c-rows", answer_value(rows_card(), "keep", rows_ok=[1]))
    store.settle("c-question", "sent")  # a bare choice is still a choice
    assert store.pending(brief) == []


def test_an_old_card_without_payload_still_loads(rec):
    store = Store(rec, project_id=rec.id)
    brief = store.new_brief(rec.id, "قديم - عينة")
    card = Card("c-old", "online", TITLE, TITLE, ("yes", "brief", "no"))
    store.add_approval(brief, card)
    with rec.write("engine") as c:  # as Plan 4 stored it, before Card had a payload
        c.execute("UPDATE approvals SET card = json_remove(card, '$.payload') WHERE id = 'c-old'")
    assert store.pending(brief) == [card]


# The cards route ---------------------------------------------------------------------------------


class AskArgs(BaseModel):
    kind: str


@pytest.fixture
def asking_lead(monkeypatch):
    """A sample tool that shows a payload card and returns the settled value, given to the
    Lead QS for this test."""

    async def run(ctx, args):
        card = question_card(f"c-{ctx.run_id[:8]}")
        if args.kind == "rows":
            card = rows_card(f"c-{ctx.run_id[:8]}")
        return await ctx.host.ask(card)

    tool = Tool(
        "ask_sample", "Ask - sample.", AskArgs, "read", run, lambda a: {"en": "ask", "ar": "يسأل"}
    )
    REGISTRY[tool.name] = tool
    spec = agents.lead_spec()
    monkeypatch.setattr(agents, "lead_spec", lambda: replace(spec, tools=(*spec.tools, tool.name)))
    yield
    REGISTRY.pop(tool.name)


def answered_lead(kind: str, seen: list):
    def reply(messages, info):
        seen.append(messages[-1].parts[-1].content)
        return "تم - عينة"

    return scripted(tool_call("ask_sample", {"kind": kind}), reply)


def app_for(lead):
    from qsone.app import create_app

    costs.save_caps({"budget_above": "100"})
    return create_app(SECRET, connectors=lambda: links(lead=lead), sleep=FakeSleep())


def test_question_card_needs_every_answer(serve_app, asking_lead):
    seen: list = []
    url = serve_app(app_for(answered_lead("question", seen)))
    with httpx.Client(timeout=10, headers=AUTH) as client:
        with client.stream("POST", f"{url}/chat", json=message("اسألني - عينة")) as r:
            lines = r.iter_lines()
            card = read_until(lines, "data-card")[-1]
            assert card["data"]["kind"] == "question"
            assert card["data"]["payload"] == QUESTIONS
            path = f"{url}/cards/{card['id']}"
            some = client.post(path, json={"choice": "sent", "answers": {"q1": "جاهزة"}})
            assert some.status_code == 422
            assert some.json() == {"error": copy.CARD_BAD_ANSWER, "field": "answers"}
            bad = client.post(path, json={"choice": "maybe"})
            assert bad.status_code == 422 and bad.json()["error"] == copy.CARD_CHOICE
            answers = {"q1": "موقع", "q2": "3950 جنيه"}
            ok = client.post(path, json={"choice": "sent", "answers": answers})
            assert ok.status_code == 204
            rest = read_until(lines, "finish")
    settled = [c for c in rest if c["type"] == "data-card" and c["id"] == card["id"]][-1]
    assert settled["data"]["status"] == "settled" and settled["data"]["choice"] == "sent"
    assert settled["data"]["answers"] == answers and settled["data"]["payload"] == QUESTIONS
    assert json.loads(seen[0]) == {"choice": "sent", "answers": answers, "rows_ok": []}


def test_rows_card_settles_with_the_ticked_rows(serve_app, asking_lead):
    seen: list = []
    url = serve_app(app_for(answered_lead("rows", seen)))
    with httpx.Client(timeout=10, headers=AUTH) as client:
        with client.stream("POST", f"{url}/chat", json=message("أسعار - عينة")) as r:
            lines = r.iter_lines()
            card = read_until(lines, "data-card")[-1]
            assert card["data"]["kind"] == "rows" and card["data"]["payload"] == ROWS
            path = f"{url}/cards/{card['id']}"
            beyond = client.post(path, json={"choice": "keep", "rows_ok": [5]})
            assert beyond.status_code == 422 and beyond.json()["field"] == "rows_ok"
            ok = client.post(path, json={"choice": "keep", "rows_ok": [2, 0]})
            assert ok.status_code == 204
            rest = read_until(lines, "finish")
        chat = client.get(f"{url}/chat/general/messages").json()["messages"]
    settled = [c for c in rest if c["type"] == "data-card" and c["id"] == card["id"]][-1]
    assert settled["data"]["choice"] == "keep" and settled["data"]["rows_ok"] == [0, 2]
    assert json.loads(seen[0]) == {"choice": "keep", "answers": {}, "rows_ok": [0, 2]}
    stored = [
        p for m in chat for p in m["parts"] if p["type"] == "data-card" and p["id"] == card["id"]
    ]
    assert stored[-1]["data"]["rows_ok"] == [0, 2]  # the rebuilt chat shows the same answer


# Services ----------------------------------------------------------------------------------------


async def test_services_are_fakes_in_tests_and_on_device_reads_the_meta(rec):
    ctx = tool_ctx(rec)
    assert isinstance(ctx.services, Services)
    assert not ctx.services.on_device(rec) and not ctx.services.on_device(None)
    reply = await ctx.services.http.get("https://site-sample.example/")
    assert reply.status_code == 404  # the fake web: nothing leaves the computer
    on_device = tool_ctx(rec, on_device=True)
    assert on_device.services.on_device(rec)


async def test_services_for_uses_the_engines_engineer_records(general):
    state = SimpleNamespace(engine=SimpleNamespace(engineer_records=lambda: general))
    services = services_for(state)
    try:
        assert services.engineer() is general and services.clock().tzinfo is not None
        assert services.http.follow_redirects is False
        assert services.search is None and services.transcriber is None
    finally:
        await services.close()


def test_a_briefs_tools_get_its_models_through_the_services(serve_app, monkeypatch):
    """Each tool run's services carry the Brief's page reader and native search."""

    async def run(ctx, args):
        return json.dumps(
            {
                "transcriber": type(ctx.services.transcriber).__name__,
                "model": ctx.services.transcriber.model_id,
                "search": ctx.services.native_search.name,
                "run": ctx.services.transcriber.models.run_id == ctx.run_id,
            }
        )

    tool = Tool(
        "services_sample", "Sample.", AskArgs, "read", run, lambda a: {"en": "s", "ar": "s"}
    )
    monkeypatch.setitem(REGISTRY, tool.name, tool)
    spec = agents.lead_spec()
    monkeypatch.setattr(agents, "lead_spec", lambda: replace(spec, tools=(*spec.tools, tool.name)))
    seen: list = []

    def reply(messages, info):
        seen.append(messages[-1].parts[-1].content)
        return "تم - عينة"

    app = app_for(scripted(tool_call("services_sample", {"kind": "x"}), reply))
    app.state.engine.services = fake_services()
    url = serve_app(app)
    with httpx.Client(timeout=10, headers=AUTH) as client:
        with client.stream("POST", f"{url}/chat", json=message("خدمات - عينة")) as r:
            read_until(r.iter_lines(), "finish")
    assert json.loads(seen[0]) == {
        "transcriber": "PageReader",
        "model": "claude-sonnet-5-5",  # the specialist tier reads images on the sample sheet
        "search": "native",
        "run": True,
    }


def test_tool_ctx_takes_the_services_given(rec):
    mine = fake_services()
    assert tool_ctx(rec, services=mine).services is mine


# Results with their sources ----------------------------------------------------------------------


def test_render_has_sources_and_stays_small():
    out = cite.render(
        "x" * 10_000, sources=[SourceRef("file:a#page=1", "عينة.pdf", "2026-11-05T10:00")]
    )
    assert len(out.encode()) <= 8 * 1024 and "sources:" in out
    assert "- file:a#page=1 | عينة.pdf | no date | read 2026-11-05T10:00" in out


def test_render_puts_each_part_in_its_place():
    source = SourceRef(
        "web:7f2c",
        "Rebar prices - sample",
        "2026-11-05 10:42 Cairo",
        dated="2026-10-30 (page)",
        link="https://steel-sample.example/p",
    )
    out = cite.render(
        "Two prices - sample.",
        sources=[
            source,
            SourceRef(
                "file:b#sheet=BOQ&row=41",
                "عينة.xlsx",
                "2026-11-05",
                locator={"sheet": "BOQ", "row": 41},
            ),
        ],
        data={"rate": Decimal("39850.00"), "n": 2},
        notes=["old: 30 days"],
        defaults_used={"pages": '[3, 4, 5] (from "٣-٥")'},
        more='call files_read {"file_id": "b", "pages": "6-10"}',
    )
    assert out.splitlines() == [
        "Two prices - sample.",
        'data: {"rate": "39850.00", "n": 2}',
        "old: 30 days",
        'defaults used: pages=[3, 4, 5] (from "٣-٥")',
        "sources:",
        "- web:7f2c | Rebar prices - sample | https://steel-sample.example/p"
        " | dated 2026-10-30 (page) | read 2026-11-05 10:42 Cairo",
        '- file:b#sheet=BOQ&row=41 | عينة.xlsx | {"sheet": "BOQ", "row": 41} | no date'
        " | read 2026-11-05",
        'more: call files_read {"file_id": "b", "pages": "6-10"}',
    ]


def test_render_never_writes_a_float():
    with pytest.raises(TypeError):
        cite.render("x", data={"rate": 0.1})


def test_render_keeps_sources_when_the_text_is_cut():
    sources = [SourceRef(f"file:a#page={n}", "عينة.pdf", "2026-11-05") for n in range(1, 4)]
    out = cite.render("نص " * 5_000, sources=sources, more="call again with page=2")
    assert len(out.encode()) <= 8 * 1024
    assert out.count("- file:a#page=") == 3 and out.rstrip().endswith("page=2")


def test_not_done_is_a_result_not_an_error():
    assert cite.not_done(copy.WEB_OFFLINE, retry_online=True).startswith("not done:")
    out = cite.not_done(copy.WEB_OFFLINE, retry_online=True, instead="read the saved snapshot")
    assert out.splitlines() == [
        f"not done: {copy.WEB_OFFLINE['en']}",
        "retry: when online",
        "instead: read the saved snapshot",
    ]
    assert cite.not_done(copy.OCR_NEEDS_MODEL) == f"not done: {copy.OCR_NEEDS_MODEL['en']}"


# The default tool lists --------------------------------------------------------------------------


def _sample(name: str, risk: str) -> Tool:
    async def run(ctx, args):
        return "sample"

    return Tool(name, "Sample.", TargetArgs, risk, run, lambda a: {"en": name, "ar": name})


def test_default_tool_lists_take_plan_5_tools_once_registered(monkeypatch):
    before_lead, before_checker = agents.lead_spec().tools, agents.checker_spec().tools
    for name in ("files_list", "files_read", "sandbox_rerun", "ask_engineer"):
        monkeypatch.setitem(REGISTRY, name, _sample(name, "read"))
    monkeypatch.setitem(REGISTRY, "web_search", _sample("web_search", "online"))
    lead, checker = agents.lead_spec().tools, agents.checker_spec().tools
    assert set(before_lead) <= set(lead)  # in LEAD_TOOLS order, so not always a prefix
    assert {"files_list", "files_read", "ask_engineer"} <= set(lead)
    assert "web_search" not in lead and "sandbox_rerun" not in lead  # specialists' tools
    assert {"files_list", "files_read", "sandbox_rerun"} <= set(checker)
    assert set(before_checker) <= set(checker) and "ask_engineer" not in checker
    assert all(REGISTRY[name].risk == "read" for name in checker)


def test_default_tool_lists_skip_tools_not_yet_registered():
    for name in agents.LEAD_TOOLS + agents.CHECKER_TOOLS:
        assert (
            name in REGISTRY or name not in agents.lead_spec().tools + agents.checker_spec().tools
        )
