"""The plan driver beside test_plan_driver.py: what a stage made (its output ids and `result`, so it
can be signed off), what its live reply carries (`data-stage`, the `brief` event, its place in the
live line), and a cut-off stage that is never offered to the engineer. Scripted models only;
synthetic «عينة» data only."""

import asyncio

import pytest

from qsone import activity, copy, home
from qsone.deliverables import store as deliverables
from qsone.engine.plan import driver as plan_driver
from qsone.engine.plan import store
from qsone.engine.types import Data, Progress, Status
from qsone.projects import Projects
from qsone.records.project import RecordsError
from tests.engine_fakes import call, scripted
from tests.engine_fakes import text as said
from tests.plan_driver_kit import MAP, Tender, blocks, drivers, english, tender  # noqa: F401
from tests.samples import sample_boq_rows
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

BOQ = {"kind": "deliverable", "title": {"en": "Priced BOQ (sample)", "ar": "جدول - عينة"}}
CHECKED = call("final_result", {"code": "A", "comments": [], "checked": ["sources - sample"]})


async def test_a_stage_that_made_its_deliverable_is_signed_off(tender, registry, project):  # noqa: F811
    rec = registry.get(project)
    sheet = {"kind": "sheet", "variant": "boq", "title": "جدول - عينة", "language": "ar"}
    lead = scripted(
        call("deliverable_create", sheet | {"rows": sample_boq_rows(rec, 2)}),
        said("الجدول جاهز - عينة"),
        said("ما اتعملش جدول - عينة"),
    )
    t = await tender(lead, checker=scripted(CHECKED), n=2, outputs=[BOQ, *MAP])
    t.approve_plan()
    await t.ready(1)
    [made] = [d["id"] for d in deliverables.list_deliverables(rec)]
    first = t.stage(1)
    assert [o.id for o in first.outputs] == [made, None]  # a map has no id
    assert first.result.model_dump() == {
        "en": "Made: Priced BOQ (sample); Project map (sample).",
        "ar": "اتعمل: جدول - عينة؛ Project map - عينة.",
    }
    t.sign_off(1)  # route 11's write: the Deliverable is signed off with the stage
    assert t.stage(1).status == "approved"
    assert deliverables.status(rec, made)["status"] == "signed_off"
    await t.ready(2)  # stage 2 made no Deliverable: it says so and cannot be signed off
    second = t.stage(2)
    assert [o.id for o in second.outputs] == [None, None]
    assert second.result.model_dump()["en"] == (
        "Made: Project map (sample). Not made yet: Priced BOQ (sample)."
    )
    with pytest.raises(RecordsError) as refused:
        store.approve_stage(t.rec, second.id)
    assert refused.value.field == "outputs"
    assert refused.value.text == copy.fill(
        copy.STAGE_OUTPUT_NOT_READY, output=BOQ["title"], reason=copy.STAGE_OUTPUT_MISSING
    )


async def test_a_stages_live_reply(tender):  # noqa: F811
    """Live, not read back: the stage's place in the live line, the `brief` event of each state,
    and `data-stage` before the reply's last status."""
    go = asyncio.Event()

    async def waits(messages, info):
        await asyncio.wait_for(go.wait(), 5)
        return call("search_records", {"query": "خرسانة - عينة"})

    t = await tender(scripted(waits, said("تمام - عينة")))
    told: list = []

    def listen(channel, event):
        if channel == t.project and event.get("type") == "brief":
            told.append(event)

    activity.LISTENERS.append(listen)
    try:
        t.approve_plan()
        await until(lambda: t.claim(1) is not None and t.engine.active(t.project) is not None)
        brief = t.claim(1)["brief_id"]
        followed = asyncio.create_task(_follow(t.engine, brief))
        go.set()
        live = await followed
        await t.ready(1)
    finally:
        activity.LISTENERS.remove(listen)
    lines = [e.text for e in live if isinstance(e, Progress)]
    assert lines and all(line["en"].startswith("Stage 1 of 3: ") for line in lines)
    assert all(line["ar"].startswith("المرحلة 1 من 3: ") for line in lines)
    stage_id = t.stage(1).id
    marks = [i for i, e in enumerate(live) if isinstance(e, Data) and e.name == "stage"]
    [mark] = marks
    assert live[mark].id == stage_id and live[mark].data == {"stage_id": stage_id}
    assert isinstance(live[-1], Status) and live[-1].state == "done" and mark < len(live) - 1
    assert {"type": "brief", "brief_id": brief, "state": "done"} in told
    assert [e["state"] for e in told][:2] == ["queued", "running"]


async def _follow(engine, brief_id: str) -> list:
    return [e async for e in engine.events(brief_id)]


async def test_a_cut_off_stage_is_never_offered_and_goes_on_when_an_ai_is_linked(
    make_engine,  # noqa: F811
    registry,  # noqa: F811
    project,  # noqa: F811
    data_dir,
    drivers,  # noqa: F811
):
    lead1 = scripted(blocks)
    e1 = await started(make_engine(links(lead=lead1)))
    t1 = Tender(e1, registry, project)
    drivers.append(t1.driver)
    t1.approve_plan()
    await until(lambda: lead1.calls == 1)
    brief = t1.claim(1)["brief_id"]
    await t1.driver.stop()
    await e1.crash()  # a power cut in the middle of stage 1
    registry.close_all()

    found: list = []  # ONE starts again with no AI linked
    second = Projects(data_dir)
    try:
        e2 = await started(make_engine(found, projects=second))
        driver = plan_driver.PlanDriver(e2)
        drivers.append(driver)
        driver.start()
        await driver.resume_all()
        second.open(project)
        e2.opened(project)
        await driver.idle()
        t2 = Tender(e2, second, project, propose=False, driver=driver)
        assert t2.claim(1)["status"] == "running" and t2.stage(1).status == "now"
        assert e2.unfinished() == []  # never a waiting item: it goes on by itself
        assert [i for i in home.snapshot(t2.rec)["waiting"] if i["kind"] == "unfinished"] == []
        lead2 = scripted(said("تمام - عينة"))
        found += links(lead=lead2)
        driver.on_ai_changed()
        await t2.ready(1)
        assert t2.claim(1)["brief_id"] == brief and lead2.calls == 1
    finally:
        second.close_all()


async def test_work_cut_off_while_one_runs_waits_for_the_next_start(tender):  # noqa: F811
    lead = scripted(blocks, said("تمام - عينة"))
    t = await tender(lead)
    t.approve_plan()
    await until(lambda: lead.calls == 1)
    brief = t.claim(1)["brief_id"]
    await t.engine.pause_all()  # before an update: it stops at its Checkpoint
    await until(lambda: t.engine.active(t.project) is None)
    t.driver.kick(t.project)  # an event while ONE still runs: it does not start again
    await t.settle()
    assert lead.calls == 1 and t.engine.active(t.project) is None
    t.engine.opened(t.project)  # the tender opened again counts as a start
    await t.ready(1)
    assert lead.calls == 2 and t.claim(1)["brief_id"] == brief and t.briefs() == (1, [1, 0, 0])
