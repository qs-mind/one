"""The plan driver and the work that follows a stage's own Brief: a Finding's decision, "I have
notes", the engineer's own messages. That work counts for the stage still open, and a stage
stopped or failed goes on by Try again (route 25) whatever ran in the chat since. Scripted
models only; synthetic «عينة» data only."""

import asyncio
import json

import pytest

from qsone import copy
from qsone.deliverables import store as deliverables
from qsone.engine.plan import claims
from tests.engine_fakes import call, scripted
from tests.engine_fakes import text as said
from tests.plan_driver_kit import MAP, blocks, drivers, english, tender  # noqa: F401
from tests.samples import sample_boq_rows
from tests.test_engine_runner import (  # noqa: F401 - fixtures
    links,
    make_engine,
    project,
    registry,
    started,
    until,
)
from tests.test_plan_driver_cases import client
from tests.test_plan_driver_more import BOQ, CHECKED

pytestmark = pytest.mark.anyio


def raise_finding(rec) -> None:
    with rec.write("lead_qs") as conn:
        conn.execute(
            "INSERT INTO findings (id, title, text, sources, status, recorded_at, recorded_by)"
            " VALUES ('f1', ?, 'سعر ناقص - عينة', '[]', 'raised', ?, 'lead-qs')",
            (json.dumps({"en": "A missing rate (sample)", "ar": "سعر ناقص - عينة"}), rec.clock()),
        )


async def test_work_after_a_decision_counts_for_the_stage(tender, registry, project):  # noqa: F811
    """The stage's Brief ends with a Finding raised and no BOQ; the Lead makes the BOQ in the
    work the decision starts. That BOQ is the stage's output, the stage waits for its sign-off
    only once that work ended, and its reply carries `data-stage`."""
    rec = registry.get(project)
    go = asyncio.Event()
    sheet = {"kind": "sheet", "variant": "boq", "title": "جدول - عينة", "language": "ar"}

    async def makes(messages, info):
        await asyncio.wait_for(go.wait(), 5)
        return call("deliverable_create", sheet | {"rows": sample_boq_rows(rec, 2)})

    lead = scripted(said("سعر ناقص - عينة"), makes, said("الجدول جاهز - عينة"), said("٢ - عينة"))
    t = await tender(lead, checker=scripted(CHECKED), n=2, outputs=[BOQ, *MAP])
    raise_finding(rec)
    t.approve_plan()
    await until(lambda: (t.claim(1) or {}).get("status") == "done")
    await t.settle()
    assert t.stage(1).status == "now"  # the decision waits
    with rec.write("engineer") as conn:
        conn.execute("UPDATE findings SET status = 'settled' WHERE id = 'f1'")
    after = await t.engine.start_brief(t.project, "قراري - عينة", by="one")  # as _tell_lead does
    await until(lambda: lead.calls == 2)
    await t.settle()
    assert t.stage(1).status == "now"  # that work runs: nothing to sign off yet
    go.set()
    await until(lambda: t.engine.active(t.project) is None)
    await t.ready(1)
    [made] = [d["id"] for d in deliverables.list_deliverables(rec)]
    assert [o.id for o in t.stage(1).outputs] == [made, None]
    assert claims.stored_parts(t.rec, t.store.brief(after)) == [
        claims.stage_part(after, t.stage(1).id)
    ]
    t.sign_off(1)  # route 11's write: the BOQ is signed off with the stage
    assert deliverables.status(rec, made)["status"] == "signed_off"
    await t.ready(2)
    assert t.briefs() == (3, [1, 1])


async def test_notes_while_a_stage_waits_keep_it_waiting(tender):  # noqa: F811
    """The engineer's notes: the stage keeps waiting while that work runs, and its reply ends the
    stage again (`data-stage`)."""
    go = asyncio.Event()

    async def waits(messages, info):
        await asyncio.wait_for(go.wait(), 5)
        return "Edited (sample)"

    t = await tender(scripted(said("تمام - عينة"), waits))
    t.approve_plan()
    await t.ready(1)
    notes = await t.engine.start_brief(t.project, "I have notes (sample)")
    await t.settle()
    assert t.stage(1).status == "waiting_engineer"
    go.set()
    await until(lambda: t.engine.active(t.project) is None)
    await t.settle()
    assert t.stage(1).status == "waiting_engineer"
    assert claims.stored_parts(t.rec, t.store.brief(notes)) == [
        claims.stage_part(notes, t.stage(1).id)
    ]


async def test_a_stopped_stage_goes_on_after_other_work_in_the_chat(tender):  # noqa: F811
    lead = scripted(blocks, said("It was stopped (sample)"), said("تمام - عينة"))
    t = await tender(lead)
    t.approve_plan()
    await until(lambda: lead.calls == 1)
    stopped = t.claim(1)["brief_id"]
    await t.engine.stop(stopped)
    await t.settle()
    await t.engine.start_brief(t.project, "Why did it stop? (sample)")  # the engineer's own
    await until(lambda: t.engine.active(t.project) is None)
    async with client(t) as http:
        again = await http.post(f"/briefs/{stopped}/retry")
        assert again.status_code == 202, again.text
        new = again.json()["brief_id"]
        await t.ready(1)
        assert t.claim(1)["attempt"] == 2 and t.claim(1)["brief_id"] == new
        twice = await http.post(f"/briefs/{stopped}/retry")  # no longer the stage's latest
    assert (twice.status_code, twice.json()) == (404, {"error": copy.BRIEF_NOT_FOUND})
