"""Phase 1 end to end on the real core (job C11): a tender's day from the files dropped to a member
kept, and a Confidential Project kept out of every other kit. The routes the screens call, the
plan driver, the Brief runner, the team room and encrypted Records are all real; only the models
are scripted (`engine_fakes`), never a real AI, a key or the network. Synthetic «عينة» data only.

Every step asserts what it leaves, so a scenario fails when any one of them breaks."""

# ruff: noqa: F811 (the engine fixtures, imported)

import json

import httpx
import pytest
from fastapi import FastAPI
from pydantic_ai.messages import ModelRequest, ToolReturnPart

from qsone import copy, home
from qsone.deliverables import review as deliverable_review
from qsone.deliverables import store as deliverables
from qsone.engine import findings, findings_routes, identity, kit, room
from qsone.engine.plan import routes as plan_routes
from qsone.engine.plan import store
from qsone.engine.runner import GENERAL
from qsone.engine.team import messages
from qsone.engine.team.stored import specialists
from qsone.engine.types import answer_value
from tests.engine_fakes import call, calls, scripted
from tests.engine_fakes import text as said
from tests.plan_driver_kit import MAP, Tender, drivers  # noqa: F401
from tests.samples import sample_boq_rows
from tests.test_engine_runner import (  # noqa: F401 - fixtures
    TAKE_OFF,
    finish,
    links,
    make_engine,
    no_budget_card,
    project,
    registry,
    started,
    store_of,
    until,
)
from tests.test_findings import boq_file, spec_file
from tests.test_tender_plan import draft, due_in, member, pair, stage

pytestmark = pytest.mark.anyio

CONTRACTS = member(
    ref="contracts-qs",
    name=pair("Contracts QS"),
    title={"en": "Contracts Quantity Surveyor (sample)", "ar": "مهندس كميات العقود (عينة)"},
    speciality={"en": "Contract conditions agent (sample)", "ar": "وكيل شروط العقد (عينة)"},
    tools=["search_records", "send_message"],
)
PRICING = member(tools=["search_records", "send_message"])  # ref "pricing-qs"
BUILD_CONTRACTS = TAKE_OFF | {"name_en": "Contracts QS", "name_ar": "مهندس العقود"}
BUILD_PRICING = TAKE_OFF | {"name_en": "Pricing QS", "name_ar": "مهندس التسعير"}
BOQ = {"kind": "deliverable", "title": {"en": "Priced BOQ (sample)", "ar": "جدول - عينة"}}
OPTIONS = [pair("Retention as clause 14"), pair("Retention as clause 9")]
CHECKED = call("final_result", {"code": "A", "comments": [], "checked": ["rates - sample"]})
MONEY = "تحليل سعر بند الخرسانة محتاج نسبة هالك للحديد: كام؟ - عينة"


def returned(messages_, tool: str) -> dict:
    """The latest result of `tool` in a model's messages."""
    found = [
        p.content
        for m in messages_
        if isinstance(m, ModelRequest)
        for p in m.parts
        if isinstance(p, ToolReturnPart) and p.tool_name == tool
    ]
    return json.loads(found[-1])


class Day:
    """The tender, its routes on the real engine, and the ids the scripted models need."""

    def __init__(self, engine, registry, project):
        self.engine, self.pid, self.rec = engine, project, registry.get(project)
        app = FastAPI()
        for router in (
            plan_routes.router(registry, engine),
            findings_routes.router(engine),
            room.router(registry, engine),
        ):
            app.include_router(router)
        self.http = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://one")

    def team(self) -> dict[str, str]:
        """The specialists the running stage Brief built, by English name."""
        brief = self.engine.active(self.pid)
        return {s.name["en"]: s.id for s in specialists(store_of(self.engine, self.pid), brief)}

    def room(self) -> list[dict]:
        return messages.page(self.rec, None, 50)["messages"][::-1]  # oldest first

    async def idle(self):
        await until(lambda: self.engine.active(self.pid) is None)

    def plan(self):
        return store.current(self.rec)


async def test_scenario_tender_day(make_engine, registry, project, drivers):
    rec = registry.get(project)
    # The engineer drops a synthetic tender: its specification and its BOQ, with its date.
    spec = spec_file(rec)
    boq_file(rec)
    due = due_in(rec, 10)
    page = lambda n: [{"file_id": spec, "locator": {"page": n}, "kind": "contract"}]  # noqa: E731
    stages = [
        stage(rec, 1, title=pair("Conditions"), owner="contracts-qs", outputs=MAP),
        stage(rec, 3, title=pair("Pricing"), owner="pricing-qs", outputs=[BOQ]),
    ]
    finding = {
        "title": pair("Retention differs"),
        "text": "البند 9 بيقول محتجز 5% والبند 14 بيقول 10% - عينة",
        "sources": page(1) + page(2),
    }
    rows = sample_boq_rows(rec, 2)  # the items the priced sheet holds, with their rates
    sheet = {"kind": "sheet", "variant": "boq", "title": "جدول - عينة", "language": "ar"}

    def raise_it(messages_, info):
        found = returned(messages_, "record_finding")["finding_id"]
        return call("raise_finding", {"finding_id": found, "opinion": "البند 14 - عينة",
                                      "options": OPTIONS})  # fmt: skip

    def delegate(name: str):
        return lambda m, i: call("delegate", {"specialist_id": day.team()[name], "task": name})

    def object_(messages_, info):
        return call("send_message", {"to": day.team()["Pricing QS"], "kind": "object",
                    "text": "المحتجز 10% مش 5% - عينة", "sources": page(2)})  # fmt: skip

    def resolve(messages_, info):
        [objection] = [m for m in day.room() if m["from_id"] == day.team()["Contracts QS"]]
        return call("send_message", {"to": day.team()["Contracts QS"], "kind": "resolve",
                    "text": "تمام، 10% - عينة", "reply_to": objection["id"]})  # fmt: skip

    lead = scripted(
        # The tender read: a Finding recorded and raised, then the plan and its team.
        call("record_finding", finding),
        raise_it,
        call(
            "tender_plan_write",
            {"submission_date": due, "stages": stages, "team": [CONTRACTS, PRICING]},
        ),  # fmt: skip
        said("الخطة والفريق جاهزين لموافقتك، وفيه تعارض في المحتجز محتاج قرارك - عينة"),
        said("تمام، ماشيين على البند ده - عينة"),  # the decision on the Finding
        # Stage 1, started by the driver: two members, a conflict settled in the room.
        call(
            "plan_brief",
            {
                "steps": [
                    {"specialist": "Contracts QS", "task": "الشروط - عينة"},
                    {"specialist": "Pricing QS", "task": "الأسعار - عينة"},
                ]
            },
        ),
        calls(call("build_specialist", BUILD_CONTRACTS), call("build_specialist", BUILD_PRICING)),
        delegate("Contracts QS"),
        delegate("Pricing QS"),
        said("الشروط اتراجعت والفريق اتفق على المحتجز - عينة"),
        # Stage 2: a money question to the engineer, then the priced sheet.
        call(
            "plan_brief",
            {
                "steps": [{"specialist": "Pricing QS", "task": "الأسعار - عينة"}],
                "deliverables": ["جدول - عينة"],
            },
        ),  # fmt: skip
        call("build_specialist", BUILD_PRICING),
        delegate("Pricing QS"),
        call("deliverable_create", sheet | {"rows": rows}),
        said("الجدول المسعّر جاهز للمراجعة - عينة"),
        # The tender's end: one member kept.
        lambda m, i: call("keep_member", {"member_id": day.plan().team[3].id}),
        said("التسعير بقى في فريقك الدائم - عينة"),
    )
    specialist = scripted(
        object_, said("اعترضت على المحتجز - عينة"),
        resolve, said("اتفقنا - عينة"),
        call("send_message", {"to": "lead", "kind": "ask", "money": True, "text": MONEY}),
        said("سعرت بالنسبة دي - عينة"),
    )  # fmt: skip
    checker = scripted(CHECKED)
    engine = await started(make_engine(links(lead=lead, specialist=specialist, checker=checker)))
    t = Tender(engine, registry, project, propose=False)
    drivers.append(t.driver)
    day = Day(engine, registry, project)

    # 1. The engineer asks the Lead to read it: Findings first, then the plan and team proposed.
    await finish(engine, await engine.start_brief(project, "اقرا المناقصة دي - عينة"))
    [raised] = findings.listed(rec)
    assert (raised["status"], raised["opinion"]) == ("raised", "البند 14 - عينة")
    assert [s["locator"] for s in raised["sources"]] == [{"page": 1}, {"page": 2}]
    plan = day.plan()
    assert (plan.status, plan.version, len(plan.stages)) == ("proposed", 1, 2)
    team = [m.id for m in plan.team]
    assert team[:2] == ["lead-qs", "checking-qs"] and len(team) == 4
    assert [s.owner_member_id for s in plan.stages] == team[2:]
    joined = [(i, p) for i, _, _, p in identity._rows(rec)]
    assert joined == [(team[2], True), (team[3], True)]  # proposed with the plan, not joined
    assert all(s.status == "pending" for s in plan.stages) and lead.calls == 4

    # 2. The engineer decides the Finding (route 14): the Lead hears it; nothing else starts.
    decided = await day.http.post(f"/projects/{project}/findings/{raised['id']}/decide",
                                  json={"choice": 0})  # fmt: skip
    assert decided.status_code == 200 and decided.json()["status"] == "settled"
    await day.idle()
    assert lead.calls == 5 and day.plan().stages[0].status == "pending"

    # 3. One approval (route 10) covers plan and team; the driver starts stage 1 by itself.
    approved = await day.http.post(f"/projects/{project}/plan/approve", json={"version": 1})
    assert approved.status_code == 200, approved.text
    assert [p for _, _, _, p in identity._rows(rec)] == [False, False]  # the team joined
    await t.ready(1)
    first = t.claim(1)["brief_id"]
    by_name = {s.name["en"]: s.id for s in specialists(store_of(engine, project), first)}
    said_in_room = [(m["from_id"], m["to_id"], m["text"]) for m in day.room()]
    assert said_in_room == [
        (team[0], "engineer", finding["text"]),  # the raised Finding
        (by_name["Contracts QS"], by_name["Pricing QS"], "المحتجز 10% مش 5% - عينة"),
        (by_name["Pricing QS"], by_name["Contracts QS"], "تمام، 10% - عينة"),
    ]  # settled in the room: nothing went up to the engineer
    with rec.read() as conn:
        assert conn.execute("SELECT count(*) FROM approvals").fetchone() == (0,)
    assert t.stage(2).status == "pending" and specialist.calls == 4

    # 4. Stage 1 signed off (route 11): stage 2 starts and stops at a money question.
    signed = await day.http.post(f"/projects/{project}/plan/stages/{t.stage(1).id}/approve",
                                 json={"version": day.plan().version})  # fmt: skip
    assert signed.status_code == 200, signed.text
    await until(lambda: t.claim(2) and t.pending(2))
    [card] = t.pending(2)
    assert card.kind == "question" and card.payload["questions"][0]["text"] == MONEY
    pricing_qs = {"en": "Pricing QS", "ar": "مهندس التسعير"}
    assert card.title == copy.fill(copy.ROOM_MONEY_TITLE, agent=pricing_qs)
    assert t.stage(2).status == "now" and t.claim(2)["status"] == "waiting_engineer"
    up = day.room()[-1]
    assert (up["from_id"], up["to_id"], up["raised"]) == (
        "lead-qs",
        "engineer",
        {"id": card.id, "answered": False},
    )
    await engine.answer(card.id, answer_value(card, "sent", answers={"answer": "5% - عينة"}))

    # 5. The priced sheet is checked by the Checking QS; the stage waits for its sign-off.
    await t.ready(2)
    assert "5% - عينة" in str(specialist.seen[-1])  # the engineer's answer reached the member
    [made] = [d["id"] for d in deliverables.list_deliverables(rec)]
    assert [o.id for o in t.stage(2).outputs] == [made] and checker.calls == 1
    check = deliverable_review.closeout(rec, made)["check"]
    assert check["code"] == "A", check
    signed = await day.http.post(f"/projects/{project}/plan/stages/{t.stage(2).id}/approve",
                                 json={"version": day.plan().version})  # fmt: skip
    assert signed.status_code == 200, signed.text
    assert [s.status for s in day.plan().stages] == ["approved", "approved"]
    assert deliverables.status(rec, made)["status"] == "signed_off"

    # 6. The tender's end: the engineer keeps the Pricing QS; the Contracts QS ends with it.
    end = await engine.start_brief(project, "المناقصة خلصت - عينة")
    await until(lambda: store_of(engine, project).pending(end))
    [keep] = store_of(engine, project).pending(end)
    assert (keep.kind, keep.payload) == ("keep_member", {"member_id": team[3]})
    await engine.answer(keep.id, "yes")
    await finish(engine, end)
    kept = identity.permanent(engine.engineer_records())
    assert [(m.id, m.kind) for m in kept[2:]] == [(team[3], "permanent")]
    assert [k for _, _, k, _ in identity._rows(rec)] == ["temporary", "permanent"]
    assert lead.calls == 17 and specialist.calls == 6
    await day.http.aclose()


async def test_scenario_confidential_isolated(make_engine, registry, drivers):
    """A Confidential Project is in its own kit only: never in another tender's, never in the
    Home conversation's, and none of its members becomes permanent."""
    open_one = registry.create("مدرسة مكشوفة - عينة", "engineer")["id"]
    secret = registry.create("برج سري - عينة", "engineer")["id"]
    rec = registry.get(secret)
    with rec.write("engineer") as conn:
        rec.set_meta(conn, "confidential", "1")
    due_in(rec)
    store.propose(rec, draft(rec, stages=[stage(rec, 1, outputs=MAP)], team=[PRICING]))
    store.approve(rec)  # its team joins inside it
    pricing = store.current(rec).team[2].id
    lead = scripted(said("تمام أ - عينة"), said("تمام ب - عينة"),
                    call("keep_member", {"member_id": pricing}), said("تمام ج - عينة"))  # fmt: skip
    engine = await started(make_engine(links(lead=lead)))

    for place in (open_one, GENERAL):
        await finish(engine, await engine.start_brief(place, "إيه الأخبار؟ - عينة"))
    await engine.start_brief(secret, "احتفظ بمهندس التسعير - عينة")
    await until(lambda: engine.active(secret) is None)  # no keep_member card to wait on
    seen = [str(lead.seen[n]) for n in range(lead.calls)]
    assert "مدرسة مكشوفة - عينة" in seen[0] and "مدرسة مكشوفة - عينة" in seen[1]
    assert "برج سري" not in seen[0] and "برج سري" not in seen[1]  # another tender's, Home's
    assert "برج سري - عينة (this tender)" in seen[2]  # its own kit only
    assert "برج سري" not in kit.text(registry, engine, None)
    assert copy.KEEP_MEMBER_CONFIDENTIAL["en"] in seen[3] or (
        copy.KEEP_MEMBER_CONFIDENTIAL["ar"] in seen[3]
    )  # keeping its member is refused
    assert [m.id for m in identity.permanent(engine.engineer_records())] == [
        identity.LEAD, identity.CHECKER
    ]  # fmt: skip
    rows, _, _ = home.tenders(registry, engine, None)
    assert [r["confidential"] for r in rows if r["project_id"] == secret] == [True]
