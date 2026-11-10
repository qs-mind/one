"""Findings (Phase 1, C4): a source must be a real place in a file, raising never holds the run
and raises one at a time, route 14 settles it, and every member sees the team's Findings.

Scripted models and hosts only; synthetic «عينة» data only."""

# ruff: noqa: F811 (the engine fixtures, imported)

import asyncio
import json
import time

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic_ai import ModelRetry

from qsone import activity, copy
from qsone import phase1_contract as c
from qsone.app import create_app
from qsone.engine import agents, costs, finding_tools, findings  # noqa: F401 - the tools
from qsone.engine.findings_routes import router as findings_router
from qsone.engine.team import messages, specialist_tools
from qsone.engine.tools import call
from qsone.engine.types import AgentSpec, Data
from qsone.records import ledger
from qsone.records.files import add_file
from tests.conftest import AUTH, SECRET
from tests.engine_fakes import OPUS, scripted, text
from tests.engine_fakes import call as step
from tests.fakes_tools import tool_ctx
from tests.samples import sample_pdf, sample_xlsx
from tests.test_engine_runner import (  # noqa: F401 - fixtures
    FakeLink,
    finish,
    links,
    make_engine,
    project,
    registry,
    started,
    until,
)

TITLE = {"en": "Column concrete grade differs (sample)", "ar": "رتبة خرسانة الأعمدة مختلفة - عينة"}
OPTIONS = [
    {"en": "Price C40 as the specification says (sample)", "ar": "نسعّر C40 زي المواصفات - عينة"},
    {"en": "Price C35 as the BOQ says (sample)", "ar": "نسعّر C35 زي المقايسة - عينة"},
]
PLUMBER = AgentSpec(
    id="5a" + "0" * 29 + "c",
    name={"en": "Pricing QS (sample)", "ar": "مهندس التسعير - عينة"},
    role="specialist",
    instructions="Price the items - sample.",
    tools=("search_records", "record_finding"),
    tier="specialist",
)


@pytest.fixture(autouse=True)
def no_budget_card():
    costs.save_caps({"budget_above": "100"})


@pytest.fixture
def events(monkeypatch) -> list[tuple[str, dict]]:
    found: list[tuple[str, dict]] = []
    monkeypatch.setattr(activity, "publish", lambda channel, event: found.append((channel, event)))
    return found


def spec_file(rec) -> str:
    pdf = sample_pdf([["الخرسانة C40 - عينة"], ["حديد B500 - عينة"]])  # 2 pages
    return add_file(rec, "المواصفات - عينة.pdf", pdf, actor="engineer").id


def boq_file(rec) -> str:
    data = sample_xlsx({"BOQ": [["3/02", "خرسانة أعمدة C35 - عينة", "م3", 40]]})
    return add_file(rec, "جدول الكميات - عينة.xlsx", data, actor="engineer").id


def finding(file_id: str, n: int = 1) -> dict:
    text = f"المواصفات بتقول C40 والمقايسة بتقول C35 ({n}) - عينة"
    return {"title": TITLE, "text": text, "sources": [{"file_id": file_id, "locator": {"page": 1}}]}


def record(ctx, file_id: str, n: int = 1) -> str:
    return json.loads(asyncio.run(call("record_finding", finding(file_id, n), ctx)))["finding_id"]


def raise_(ctx, finding_id: str, opinion: str = "C40 أأمن - عينة") -> dict:
    asked = {"finding_id": finding_id, "opinion": opinion, "options": OPTIONS}
    return json.loads(asyncio.run(call("raise_finding", asked, ctx)))


# Sources ----------------------------------------------------------------------------------------


def test_finding_needs_real_source(rec, events):
    pdf, sheet = spec_file(rec), boq_file(rec)
    ctx = tool_ctx(rec)
    wrong = [
        [],  # none at all
        [{"file_id": "0" * 32, "locator": {"page": 1}}],  # no such file
        [{"file_id": pdf, "locator": {"page": 9}}],  # the file has two pages
        [{"file_id": pdf, "locator": {}}],  # no place
        [{"file_id": sheet, "locator": {"sheet": "BOQ", "row": 99}}],  # no such row
        [{"file_id": sheet, "locator": {"sheet": "Nowhere", "row": 1}}],
    ]
    for sources in wrong:
        with pytest.raises(ModelRetry):
            asyncio.run(call("record_finding", finding(pdf) | {"sources": sources}, ctx))
    with pytest.raises(ModelRetry, match="not in the project's records"):
        asyncio.run(call("record_finding", finding(pdf) | {"item_ids": ["0" * 32]}, ctx))
    assert findings.listed(rec) == [] and events == []

    with rec.read() as conn:
        row = conn.execute(
            "SELECT locator FROM chunks WHERE file_id = ? ORDER BY seq", (sheet,)
        ).fetchone()
    place = {k: v for k, v in json.loads(row[0]).items() if k in ("sheet", "row")}
    with rec.write("engineer") as conn:
        item = ledger.write_item(
            conn, at=rec.clock(), actor="engineer", kind="boq_item", code="3/02", fields={}
        )
    sources = [{"file_id": pdf, "locator": {"page": "٢"}}, {"file_id": sheet, "locator": place}]
    asked = finding(pdf) | {"sources": sources, "item_ids": [item]}
    out = json.loads(asyncio.run(call("record_finding", asked, ctx)))
    [found] = findings.listed(rec)
    assert out == {"finding_id": found["id"], "status": "open"}
    assert found["sources"][0] == {
        "kind": "file",
        "title": "المواصفات - عينة.pdf",
        "file_name": "المواصفات - عينة.pdf",
        "file_id": pdf,
        "locator": {"page": 2},
        "url": None,
        "dated": None,
        "quote": None,
    }
    assert found["sources"][1]["locator"] == place and found["item_ids"] == [item]
    assert (found["status"], found["options"], found["chosen"], found["note"]) == (
        "open", None, None, None
    )  # fmt: skip
    assert events == [(rec.id, {"type": "finding", "finding": found})]
    c.Findings.model_validate_json(json.dumps({"findings": [found]}), strict=True)


def test_at_most_100_findings_wait_in_a_tender(rec, monkeypatch):
    monkeypatch.setattr(findings, "MAX_UNSETTLED", 3)
    pdf = spec_file(rec)
    ctx = tool_ctx(rec)
    ids = [record(ctx, pdf, n) for n in range(3)]
    with pytest.raises(ModelRetry, match="100 Findings"):
        record(ctx, pdf, 9)
    findings.close(rec, ids[0], {"en": "Closed (sample)", "ar": "اتقفلت - عينة"}, actor="Lead QS")
    record(ctx, pdf, 9)
    assert findings.MAX_UNSETTLED == 3 and len(findings.listed(rec)) == 4


# Raising and deciding ---------------------------------------------------------------------------


def lead_link():
    model = scripted(lambda messages, info: text("تمام - عينة"))
    return [FakeLink("anthropic", "Claude", "anthropic", {OPUS.choice.model: model}, [OPUS])]


def test_raise_makes_one_decision_card(events):
    links: list = []
    with TestClient(create_app(SECRET, connectors=lambda: links)) as client:
        pid = client.post("/projects", json={"name": "مناقصة - عينة"}, headers=AUTH).json()["id"]
        rec = client.app.state.projects.get(pid)
        pdf = spec_file(rec)
        ctx = tool_ctx(rec)
        first, second, third = (record(ctx, pdf, n) for n in range(3))

        raised = raise_(ctx, first)
        queued = raise_(ctx, second)
        assert (raised["status"], raised["queued_ahead"]) == ("raised", 0)
        assert (queued["status"], queued["queued_ahead"]) == ("queued", 0)
        said = [(e["finding"]["id"], e["finding"]["status"]) for _, e in events if "finding" in e]
        assert said[-2:] == [(first, "raised"), (second, "queued")]  # the team sees it at once
        assert ctx.host.cards == []  # no card: raising never holds the Lead's run
        parts = [e for e in ctx.host.events if isinstance(e, Data) and e.name == "finding"]
        assert [(p.id, p.data) for p in parts] == [
            (first, {"finding_id": first}),
            (second, {"finding_id": second}),
        ]
        lead_says = messages.page(rec, None, 50)["messages"][-1]  # the team room (C6)
        assert (lead_says["from_id"], lead_says["to_id"]) == ("lead-qs", "engineer")
        assert lead_says["raised"] == {"id": first, "answered": False}
        assert raise_(ctx, first) == raised  # the same call again is the same answer
        with pytest.raises(ModelRetry, match="raise each Finding once"):
            raise_(ctx, first, "رأي تاني - عينة")

        got = client.get(f"/projects/{pid}/findings", headers=AUTH)
        assert got.status_code == 200 and got.headers["cache-control"] == "no-store"
        listed = c.Findings.model_validate_json(got.text, strict=True).findings
        assert [(f.id, f.status) for f in listed] == [
            (first, "raised"), (second, "queued"), (third, "open")
        ]  # fmt: skip
        assert listed[0].note.model_dump() == copy.FINDING_WAITING and listed[1].note is None
        assert [o.model_dump() for o in listed[0].options] == OPTIONS

        def decide(finding_id: str, choice: int):
            path = f"/projects/{pid}/findings/{finding_id}/decide"
            return client.post(path, json={"choice": choice}, headers=AUTH)

        for finding_id, status, text_ in (
            (second, 409, copy.FINDING_NOT_RAISED),
            (third, 409, copy.FINDING_NOT_RAISED),
            ("0" * 32, 404, copy.FINDING_NOT_FOUND),
        ):
            refused = decide(finding_id, 0)
            assert (refused.status_code, refused.json()) == (status, {"error": text_})
        no_ai = decide(first, 0)  # the Lead's work would start, and no AI is connected
        assert no_ai.status_code == 409 and c.Refusal.model_validate(no_ai.json())
        assert findings.listed(rec)[0]["status"] == "raised"  # nothing stored

        links[:] = lead_link()
        events.clear()
        done = decide(first, 0)
        assert done.status_code == 200
        settled = c.Finding.model_validate_json(done.text, strict=True)
        assert (settled.status, settled.chosen, settled.note) == ("settled", 0, None)
        assert settled.settled_at is not None
        said = [e["finding"] for _, e in events if e["type"] == "finding"]
        assert [(f["id"], f["status"]) for f in said] == [
            (first, "settled"), (second, "raised")
        ]  # fmt: skip
        brief = client.app.state.engine.active(pid)
        assert brief is not None  # the Lead's work on the decision
        answered = [e["message"] for _, e in events if e["type"] == "room"]
        assert [(m["id"], m["raised"]) for m in answered][:1] == [
            (lead_says["id"], {"id": first, "answered": True})
        ]
        assert messages.page(rec, None, 50)["messages"][-1]["raised"]["answered"] is True

        assert decide(first, 0).json() == done.json()  # the same choice again
        other = decide(first, 1)
        assert (other.status_code, other.json()) == (409, {"error": copy.FINDING_SETTLED})
        [now] = [f for f in findings.listed(rec) if f["id"] == second]
        assert (now["status"], now["note"]) == ("raised", copy.FINDING_WAITING)

        archived = client.post(f"/projects/{pid}/archive", headers=AUTH)
        while archived.status_code == 409:  # the Lead's work ends first
            time.sleep(0.05)
            archived = client.post(f"/projects/{pid}/archive", headers=AUTH)
        locked = decide(second, 0)
        assert locked.status_code == 423


async def test_a_decision_steers_the_running_lead(make_engine, project, registry, events):
    """Work runs in the tender: the decision is a steer into it, not a second Brief; and the
    stored reply places the Finding again."""
    rec = registry.get(project)
    pdf = spec_file(rec)
    first = json.loads(await call("record_finding", finding(pdf), tool_ctx(rec)))["finding_id"]
    go = asyncio.Event()

    def briefs() -> int:
        with rec.read() as conn:
            return conn.execute("SELECT count(*) FROM briefs").fetchone()[0]

    async def waits(messages, info):
        await asyncio.wait_for(go.wait(), 5)
        return step("files_list", {})

    asked = {"finding_id": first, "opinion": "C40 أأمن - عينة", "options": OPTIONS}
    lead = scripted(step("raise_finding", asked), waits, text("تمام - عينة"))
    engine = await started(make_engine(links(lead=lead)))
    before = briefs()
    brief = await engine.start_brief(project, "سعّر الخرسانة - عينة")
    await until(lambda: lead.calls == 2)
    said = [(e["finding"]["id"], e["finding"]["status"]) for _, e in events if "finding" in e]
    assert said[-1] == (first, "raised")  # raise_finding in the Brief told the team

    app = FastAPI()
    app.include_router(findings_router(engine))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://one") as client:
        done = await client.post(f"/projects/{project}/findings/{first}/decide", json={"choice": 0})
    assert done.status_code == 200 and done.json()["status"] == "settled"
    assert engine.active(project) == brief
    go.set()
    await finish(engine, brief)
    assert "The engineer decided the Finding" in str(lead.seen[2])
    assert engine.active(project) is None

    assert briefs() == before + 1  # the decision started no second Brief
    [message] = [m for m in engine.chat_messages(project) if m["id"] == f"{brief}-reply"]
    part = {"type": "data-finding", "id": first, "data": {"finding_id": first}}
    assert part in message["parts"]


def test_closed_without_the_engineer(rec, events):
    pdf = spec_file(rec)
    ctx = tool_ctx(rec)
    first, second = record(ctx, pdf, 1), record(ctx, pdf, 2)
    raise_(ctx, first)
    raise_(ctx, second)
    note = {"en": "Closed: Addendum 2 gives the grade (sample)", "ar": "اتقفلت: الملحق 2 - عينة"}
    changed = findings.close(rec, first, note, actor="Lead QS")
    assert [(f["id"], f["status"]) for f in changed] == [(first, "settled"), (second, "raised")]
    closed = findings.listed(rec)[0]
    assert (closed["chosen"], closed["note"]) == (None, note) and closed["settled_at"]
    with pytest.raises(Exception, match="already settled"):
        findings.close(rec, first, note, actor="Lead QS")


def test_a_stored_reply_places_the_finding_again():
    returns = [
        ("record_finding", json.dumps({"finding_id": "a" * 32, "status": "open"})),
        ("raise_finding", json.dumps({"finding_id": "b" * 32, "status": "queued"})),
        ("raise_finding", "not done: sample"),
    ]
    assert findings.stored_parts("brief", returns) == [
        Data("brief", "finding", "b" * 32, {"finding_id": "b" * 32})
    ]


# Shared with the team ---------------------------------------------------------------------------


def test_findings_shared(rec, events):
    pdf = spec_file(rec)
    lead = tool_ctx(rec)
    first = record(lead, pdf)

    specialist = tool_ctx(rec, agent=PLUMBER)
    said = asyncio.run(call("search_records", {"query": "C35"}, specialist))
    out = json.loads(said.split("\n", 1)[1].rsplit("\n", 1)[0])  # inside the data fence
    [shared] = out["findings"]
    assert shared["finding_id"] == first and shared["title"] == TITLE
    assert shared["sources"] == [
        {"file_id": pdf, "file": "المواصفات - عينة.pdf", "locator": {"page": 1}}
    ]
    nothing = asyncio.run(call("search_records", {"query": "عزل"}, specialist))
    assert '"findings"' not in nothing

    second = record(specialist, pdf, 2)  # a specialist records one too
    assert [f["id"] for f in findings.listed(rec)] == [first, second]


def test_who_has_the_finding_tools():
    lead = agents.lead_spec().tools
    assert {"record_finding", "raise_finding"} <= set(lead)
    tools = specialist_tools()
    assert "record_finding" in tools and "raise_finding" not in tools
    assert not {"record_finding", "raise_finding"} & set(agents.checker_spec().tools)
