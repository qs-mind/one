"""The plan driver's hard cases and Try again (route 25), beside test_plan_driver.py: events twice,
a watcher's fault, no AI, an archived tender, a Finding that waits, the database's own rules.
Scripted models only; synthetic «عينة» data only."""

import asyncio
import json
import threading

import httpx
import pytest
from fastapi import FastAPI

from qsone import copy
from qsone import phase1_contract as c
from qsone.engine.plan import retry as retry_routes
from qsone.engine.plan import store
from qsone.journey import closing, setup_state
from qsone.records import db
from tests.engine_fakes import scripted
from tests.engine_fakes import text as said
from tests.plan_driver_kit import (  # noqa: F401 - fixtures
    Tender,
    blocks,
    drivers,
    english,
    tender,
)
from tests.test_engine_runner import (  # noqa: F401 - fixtures
    links,
    make_engine,
    no_budget_card,
    project,
    registry,
    started,
    until,
)

pytestmark = pytest.mark.anyio


async def test_plan_approved_twice_and_from_threads_starts_one_brief(tender):  # noqa: F811
    t = await tender(scripted(said("١ - عينة"), said("٢ - عينة")))
    t.approve_plan()
    t.approve_plan()
    await asyncio.gather(*(asyncio.to_thread(t.approve_plan) for _ in range(4)))
    await t.ready(1)
    first = t.claim(1)["brief_id"]
    for watch in t.engine.watchers:  # "Brief ended" again, twice
        watch(t.project, first, "done")
        watch(t.project, first, "done")
    await t.settle()
    assert t.briefs() == (1, [1, 0, 0])
    gate = threading.Barrier(2)

    def sign_off():
        gate.wait()
        t.sign_off(1)

    await asyncio.gather(asyncio.to_thread(sign_off), asyncio.to_thread(sign_off))
    await t.ready(2)
    await t.settle()
    assert t.briefs() == (2, [1, 1, 0])


async def test_a_watchers_fault_never_fails_a_brief(tender):  # noqa: F811
    t = await tender(scripted(said("تمام - عينة")))

    def broken(chat_id, brief_id, state):
        raise RuntimeError("a bug in a watcher (sample)")

    t.engine.watchers.insert(0, broken)
    t.approve_plan()
    await t.ready(1)
    assert t.claim(1)["status"] == "done"


async def test_no_ai_leaves_the_stage_waiting_untouched(make_engine, registry, project, drivers):  # noqa: F811
    found: list = []  # no AI linked yet
    engine = await started(make_engine(found))
    t = Tender(engine, registry, project)
    drivers.append(t.driver)
    t.approve_plan()
    await t.settle()
    assert t.claim(1) is None and t.stage(1).status == "pending"  # nothing used up
    lead = scripted(said("تمام - عينة"))
    found += links(lead=lead)
    t.driver.on_ai_changed()
    await t.ready(1)
    assert lead.calls == 1 and t.briefs() == (1, [1, 0, 0])


async def test_an_archived_tender_is_left(make_engine, registry, project, drivers):  # noqa: F811
    lead = scripted(said("تمام - عينة"))
    engine = await started(make_engine(links(lead=lead)))
    old = Tender(engine, registry, registry.create("قديم - عينة", "engineer")["id"])
    drivers.append(old.driver)
    store.approve(old.rec)
    closing.archive(old.rec, None)
    t = Tender(engine, registry, project, driver=old.driver)
    store.approve(t.rec)
    await old.driver.resume_all()
    await t.ready(1)
    assert old.claim(1) is None and lead.calls == 1


async def test_a_finding_that_waits_keeps_the_stage_now(tender):  # noqa: F811
    t = await tender(scripted(said("تمام - عينة")))
    at = t.rec.clock()
    with t.rec.write("lead_qs") as conn:
        conn.execute(
            "INSERT INTO findings (id, title, text, sources, status, recorded_at, recorded_by)"
            " VALUES ('f1', ?, 'سعر ناقص - عينة', '[]', 'raised', ?, 'lead-qs')",
            (json.dumps({"en": "A rate is missing (sample)", "ar": "سعر ناقص - عينة"}), at),
        )
    t.approve_plan()
    await until(lambda: (t.claim(1) or {}).get("status") == "done")
    await t.settle()
    assert t.stage(1).status == "now"  # the tender waits for the decision, not for a sign-off
    with t.rec.write("engineer") as conn:
        conn.execute("UPDATE findings SET status = 'settled' WHERE id = 'f1'")
    t.driver.kick(t.project)
    await t.ready(1)


async def test_the_engineers_own_brief_delays_the_next_stage(tender):  # noqa: F811
    go = asyncio.Event()

    async def waits(messages, info):
        await asyncio.wait_for(go.wait(), 5)
        return "تمام - عينة"

    lead = scripted(said("١ - عينة"), waits, said("٢ - عينة"))
    t = await tender(lead)
    t.approve_plan()
    await t.ready(1)
    own = await t.engine.start_brief(t.project, "Change the margin (sample)")
    await until(lambda: lead.calls == 2)
    t.sign_off(1)  # stage 2 is due; the chat is busy
    await t.settle()
    assert t.engine.active(t.project) == own and t.briefs() == (2, [1, 0, 0])
    go.set()
    await t.ready(2)  # it started once the chat was free
    assert t.briefs() == (3, [1, 1, 0])


async def test_one_brief_per_stage_attempt_is_a_database_rule(tender):  # noqa: F811
    t = await tender(scripted(said("تمام - عينة")))
    t.approve_plan()
    await t.ready(1)
    claim, stage_id = t.claim(1), t.stage(1).id
    for sql, args in (
        ("INSERT INTO tender_stage_briefs VALUES (?, 1, 'x', 'now')", (stage_id,)),
        ("INSERT INTO tender_stage_briefs VALUES (?, 2, ?, 'now')", (stage_id, claim["brief_id"])),
        ("INSERT INTO tender_stage_briefs VALUES (?, 0, 'y', 'now')", (stage_id,)),
        ("UPDATE tender_stage_briefs SET attempt = 3", ()),
        ("DELETE FROM tender_stage_briefs", ()),
    ):
        with pytest.raises(db.DatabaseError):
            with t.rec.write("engineer") as conn:
                conn.execute(sql, args)
    assert t.briefs() == (1, [1, 0, 0])


# Try again (route 25) ---------------------------------------------------------------------------


def client(t: Tender) -> httpx.AsyncClient:
    setup_state.give_consent(setup_state.CONSENT_VERSION)  # the Lead may work
    app = FastAPI()
    app.include_router(retry_routes.router(t.engine, t.driver))
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://core")


async def test_try_again_goes_on_with_a_stopped_stage_once(tender):  # noqa: F811
    lead = scripted(blocks)
    t = await tender(lead)
    t.approve_plan()
    await until(lambda: lead.calls == 1)  # the Lead is at work
    stopped = t.claim(1)["brief_id"]
    await t.engine.stop(stopped)
    await t.settle()
    assert t.stage(1).status == "now"  # stopped: it waits for Try again, not for a sign-off
    lead.steps.append(said("تمام - عينة"))
    async with client(t) as http:
        again = await http.post(f"/briefs/{stopped}/retry")
        assert again.status_code == 202, again.text
        new = c.BriefStarted.model_validate_json(again.text, strict=True).brief_id
        await t.ready(1)
        assert t.claim(1) == {"attempt": 2, "brief_id": new, "status": "done", "began": True}
        twice = await http.post(f"/briefs/{stopped}/retry")  # no longer the chat's last Brief
        assert (twice.status_code, twice.json()) == (404, {"error": copy.BRIEF_NOT_FOUND})
    assert t.store.brief(new)["started_by"] == "one"
    assert t.store.brief(new)["text"] == t.store.brief(stopped)["text"]


async def test_try_again_on_the_engineers_own_failed_work(tender):  # noqa: F811
    t = await tender(scripted(said("تمام - عينة")))  # no plan approved: an ordinary chat
    async with client(t) as http:
        unknown = await http.post(f"/briefs/{'5a' + '0' * 30}/retry")
        assert (unknown.status_code, unknown.json()) == (404, {"error": copy.BRIEF_NOT_FOUND})
        mine = t.store.new_brief(t.project, "Price the BOQ (sample)")
        with pytest.raises(ValueError):
            c.BriefStarted.model_validate_json((await http.post(f"/briefs/{mine}/retry")).text)
        t.store.set_status(mine, "failed")
        again = await http.post(f"/briefs/{mine}/retry")
        assert again.status_code == 202, again.text
        new = again.json()["brief_id"]
        busy = await http.post(f"/briefs/{new}/retry")  # it runs: nothing to try again
    assert (busy.status_code, busy.json()) == (404, {"error": copy.BRIEF_NOT_FOUND})
    await until(lambda: t.engine.active(t.project) is None)
    question = t.engine.chat_messages(t.project)[2]
    assert question["metadata"]["by"] == "one"
    assert question["parts"][0]["text"] == "Price the BOQ (sample)"


async def test_try_again_refuses_what_it_must(tender, monkeypatch):  # noqa: F811
    """Only the last Brief of its chat; never in an archived tender; never while the Lead cannot
    work. Each refusal starts nothing."""
    t = await tender(scripted(said("تمام - عينة")))
    older = t.store.new_brief(t.project, "Price the BOQ (sample)")
    t.store.set_status(older, "failed")
    last = t.store.new_brief(t.project, "Check the rates (sample)")
    t.store.set_status(last, "stopped")
    async with client(t) as http:
        refused = await http.post(f"/briefs/{older}/retry")  # not the chat's last Brief
        assert (refused.status_code, refused.json()) == (404, {"error": copy.BRIEF_NOT_FOUND})
        with monkeypatch.context() as patch:
            patch.setattr(setup_state, "consent", lambda: None)
            blocked = await http.post(f"/briefs/{last}/retry")
        assert blocked.status_code == 409
        assert blocked.json() == copy.error(copy.AI_CONSENT_NEEDED)
        closing.archive(t.rec, None)
        archived = await http.post(f"/briefs/{last}/retry")
        assert (archived.status_code, archived.json()) == (423, copy.error(copy.PROJECT_ARCHIVED))
    assert t.engine.active(t.project) is None and t.briefs() == (2, [0, 0, 0])
