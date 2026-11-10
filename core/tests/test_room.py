"""The team room (Phase 1, C6): one conversation per tender, paged newest first; the engineer's
message reaches the Lead only; a money question and a disagreement past two rounds go up to the
engineer.

Scripted models and hosts only; synthetic «عينة» data only."""

# ruff: noqa: F811 (the engine fixtures, imported)

import asyncio
import json
from dataclasses import replace

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from qsone import activity, copy
from qsone import phase1_contract as c
from qsone.app import create_app
from qsone.engine import room, stream
from qsone.engine.team import messages
from qsone.engine.tools import call
from qsone.engine.types import AgentSpec
from qsone.journey import setup_state
from tests.conftest import AUTH, SECRET
from tests.engine_fakes import OPUS, scripted, text
from tests.engine_fakes import call as step
from tests.fakes_tools import tool_ctx
from tests.test_engine_runner import (  # noqa: F401 - fixtures
    finish,
    links,
    make_engine,
    project,
    registry,
    started,
    until,
)
from tests.test_findings import spec_file


def member(n: str, en: str, ar: str) -> AgentSpec:
    return AgentSpec(
        id="5a" + "0" * 29 + n,
        name={"en": en, "ar": ar},
        role="specialist",
        instructions="Price the items - sample.",
        tools=("send_message", "search_records"),
        tier="specialist",
    )


CONTRACTS = member("1", "Contracts QS (sample)", "مهندس العقود - عينة")
PRICING = member("2", "Pricing QS (sample)", "مهندس التسعير - عينة")


@pytest.fixture
def events(monkeypatch) -> list[dict]:
    found: list[dict] = []
    monkeypatch.setattr(activity, "publish", lambda channel, event: found.append(event))
    return found


def said(ctx, to: str, words: str, **more) -> dict:
    asked = {"to": to, "text": words, **more}
    return json.loads(asyncio.run(call("send_message", asked, ctx)))


def answer(**answers) -> str:
    return json.dumps({"choice": room.SENT, "answers": answers}, ensure_ascii=False)


def test_room_lists_team_messages_paged(events):
    with TestClient(create_app(SECRET)) as client:
        pid = client.post("/projects", json={"name": "مناقصة - عينة"}, headers=AUTH).json()["id"]
        rec = client.app.state.projects.get(pid)
        written = [
            messages.write(rec, from_id=room.identity.LEAD, to_id=CONTRACTS.id, text=f"{n} - عينة")
            for n in range(120)
        ]

        def page(query: str = "") -> c.RoomPage:
            got = client.get(f"/projects/{pid}/room{query}", headers=AUTH)
            assert got.status_code == 200 and got.headers["cache-control"] == "no-store"
            return c.RoomPage.model_validate_json(got.text, strict=True)

        first = page()
        assert [m.text for m in first.messages] == [f"{n} - عينة" for n in range(119, 69, -1)]
        second = page(f"?cursor={first.next_cursor}")
        assert [m.text for m in second.messages] == [f"{n} - عينة" for n in range(69, 19, -1)]
        last = page(f"?cursor={second.next_cursor}&limit=50")
        assert [m.id for m in last.messages] == [m["id"] for m in reversed(written[:20])]
        assert last.next_cursor is None  # the start of the room
        assert (last.messages[0].from_id, last.messages[0].to_id) == ("lead-qs", CONTRACTS.id)
        assert page("?limit=2").messages == first.messages[:2]

        for cursor in ("abc", "cm9vbTow", "!!"):  # not ours; rowid 0; not base64
            bad = client.get(f"/projects/{pid}/room?cursor={cursor}", headers=AUTH)
            assert bad.status_code == 422
            assert bad.json() == {"error": copy.ROOM_CURSOR_INVALID, "field": "cursor"}


async def test_engineer_post_goes_to_lead(make_engine, project, registry, events):
    """Idle: ONE starts the Lead's work on the message. Running: it steers that work. Never the
    Checking QS. Refused, and nothing stored, when the Lead cannot work."""
    rec = registry.get(project)
    refused = await started(make_engine([]))
    app = FastAPI()
    app.include_router(room.router(registry, refused))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://one") as client:
        no_ai = await client.post(f"/projects/{project}/room", json={"text": "سؤال - عينة"})
    assert (no_ai.status_code, no_ai.json()) == (409, copy.error(copy.NO_AI))
    assert messages.page(rec, None, 50)["messages"] == []

    go = asyncio.Event()

    async def waits(messages_, info):
        await asyncio.wait_for(go.wait(), 5)
        return step("files_list", {})

    lead = scripted(waits, text("تمام - عينة"))
    checker = scripted(text("A"))
    engine = await started(make_engine(links(lead=lead, checker=checker)))
    app = FastAPI()
    app.include_router(room.router(registry, engine))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://one") as client:
        first = await client.post(
            f"/projects/{project}/room", json={"text": "  استخدموا 5% هالك للحديد - عينة "}
        )
        assert first.status_code == 201
        stored = c.RoomMessage.model_validate_json(first.text, strict=True)
        assert (stored.from_id, stored.to_id, stored.text, stored.sources, stored.raised) == (
            "engineer", "team", "استخدموا 5% هالك للحديد - عينة", [], None
        )  # fmt: skip
        brief = engine.active(project)
        assert brief is not None  # the Lead's work on it
        await until(lambda: lead.calls == 1)
        assert stored.text in str(lead.seen[0])

        steer = {"text": "ابدأ بالخرسانة - عينة"}
        second = await client.post(f"/projects/{project}/room", json=steer)
        assert second.status_code == 201
        assert engine.active(project) == brief  # a steer, not a second Brief
        long = await client.post(f"/projects/{project}/room", json={"text": "ا" * 20_001})
        assert long.json() == {"error": copy.ROOM_TOO_LONG, "field": "text"}
        go.set()
        await finish(engine, brief)
    assert "ابدأ بالخرسانة - عينة" in str(lead.seen[1])
    assert checker.calls == 0  # the Checking QS never hears it

    newest = [m["id"] for m in messages.page(rec, None, 50)["messages"]]
    assert newest == [second.json()["id"], stored.id]
    assert [e["message"]["id"] for e in events if e["type"] == "room"] == newest[::-1]
    [reply] = [m for m in engine.chat_messages(project) if m["id"] == f"{brief}-reply"]
    shown = [p["id"] for p in reply["parts"] if p["type"] == "data-room"]
    assert shown == newest[::-1]  # the stored reply shows both


def test_money_question_is_raised(rec, events):
    ctx = tool_ctx(rec, agent=PRICING, answers={"question": answer(answer="5% - عينة")})
    pdf = spec_file(rec)
    place = {"file_id": pdf, "locator": {"page": 1}, "kind": "specification"}
    words = "تحليل سعر بند 3/02 محتاج نسبة هالك للحديد: كام؟ - عينة"
    out = said(ctx, "lead", words, kind="ask", money=True, sources=[place])
    assert (out["raised_to_engineer"], out["answer"]) == (True, "5% - عينة")

    [card] = ctx.host.cards
    assert card.kind == "question" and card.payload["questions"][0]["text"] == words
    assert card.title == copy.fill(copy.ROOM_MONEY_TITLE, agent=PRICING.name)
    assert ctx.host.posted == []  # it went up to the engineer, not to the Lead's inbox

    lead_says, asked = messages.page(rec, None, 50)["messages"]
    assert (asked["from_id"], asked["to_id"], asked["raised"]) == (PRICING.id, "lead-qs", None)
    assert asked["sources"][0]["file_id"] == pdf and asked["sources"][0]["locator"] == {"page": 1}
    assert (lead_says["from_id"], lead_says["to_id"]) == ("lead-qs", "engineer")
    assert lead_says["raised"] == {"id": card.id, "answered": True}
    assert lead_says["sources"] == asked["sources"]
    raised = [e["message"]["raised"] for e in events if e["message"]["id"] == lead_says["id"]]
    assert raised == [None, {"id": card.id, "answered": False}, {"id": card.id, "answered": True}]

    parts = stream.message_parts(ctx.host.events)
    room_parts = [p for p in parts if p["type"] == "data-room"]
    assert [p["id"] for p in room_parts] == [asked["id"], lead_says["id"]]
    assert room_parts[1]["data"] == lead_says  # the part carries the message as it is now


def test_disagreement_goes_to_engineer_after_two_rounds(rec, events):
    lang = setup_state.language()
    views = [copy.fill(copy.ROOM_VIEW, agent=m.name)[lang] for m in (CONTRACTS, PRICING)]
    contracts = tool_ctx(rec, agent=CONTRACTS, answers={"question": answer(view=views[1])})
    run = contracts.store.new_run(contracts.brief_id, PRICING, OPUS.choice, None)
    pricing = replace(contracts, agent=PRICING, run_id=run)
    pdf = spec_file(rec)

    def where(page: int) -> list[dict]:
        return [{"file_id": pdf, "locator": {"page": page}, "kind": "contract"}]

    one = said(contracts, PRICING.id, "المحتجز 5% في البند 9 - عينة", kind="object",
               sources=where(1))  # fmt: skip
    two = said(pricing, CONTRACTS.id, "البند 14 بيقول 10% - عينة", kind="object",
               reply_to=one["sent"], sources=where(2))  # fmt: skip
    assert contracts.host.cards == [] and len(contracts.host.posted) == 2  # two rounds: theirs

    three = said(contracts, PRICING.id, "لسه شايف 5% - عينة", kind="object", reply_to=two["sent"])
    assert (three["engineer_decides"], three["engineer_chose"]) == (True, views[1])
    [card] = contracts.host.cards
    assert card.payload["questions"][0]["options"] == views
    assert card.title == copy.fill(
        copy.ROOM_DISAGREE_TITLE, first=CONTRACTS.name, second=PRICING.name
    )
    for both in ("لسه شايف 5% - عينة", "البند 14 بيقول 10% - عينة", "المواصفات - عينة.pdf"):
        assert both in card.detail["en"] and both in card.detail["ar"]  # both views, evidence
    assert len(contracts.host.posted) == 2  # the third objection did not go to the member

    settled, lead_says, *_ = messages.page(rec, None, 50)["messages"]
    assert (lead_says["from_id"], lead_says["to_id"]) == ("lead-qs", "engineer")
    assert lead_says["raised"] == {"id": card.id, "answered": True}
    assert [s["locator"] for s in lead_says["sources"]] == [{"page": 1}, {"page": 2}]
    assert (settled["from_id"], settled["to_id"]) == ("lead-qs", "team")
    assert views[1] in settled["text"]

    four = said(pricing, CONTRACTS.id, "تمام، 10% - عينة", kind="object", reply_to=three["sent"])
    assert "engineer_decides" not in four and len(contracts.host.cards) == 1  # settled: new rounds
