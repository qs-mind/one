"""The tender plan as data (Phase 1, C2): the checks a plan passes, its date, its estimate, the
`data-plan` part and the Suggested change. Scripted models only, never a real AI. Synthetic
«عينة» data only."""

from dataclasses import replace
from datetime import timedelta

import pytest
from pydantic import ValidationError

from qsone import copy
from qsone.engine import costs
from qsone.engine.plan import model, store
from qsone.engine.plan import tool as plan_tool
from qsone.engine.plan.model import PlanDraft, PlanIn
from qsone.engine.team.common import TeamSetup
from qsone.engine.tools import ModelRetry, call
from qsone.engine.types import Data, ModelChoice
from qsone.journey import understand
from qsone.records.project import RecordsError
from tests.engine_fakes import OPUS, SAMPLE_SHEET
from tests.fakes_tools import tool_ctx

# A model no price list knows: the sheet keeps the sample price it was given.
CARD = replace(OPUS, choice=ModelChoice("anthropic", "sample-lead"), name="sample-lead (sample)")
SHEET = [CARD]


def day(rec, n: int) -> str:
    return (store.today(rec) + timedelta(days=n)).isoformat()


def due_in(rec, n: int = 10) -> str:
    """Makes the tender's submission date `n` days from today; gives it."""
    understand.correct(rec, {"submission_date": day(rec, n)}, approve=False)
    return day(rec, n)


def pair(en: str) -> dict:
    return {"en": f"{en} (sample)", "ar": f"{en} - عينة"}


def stage(rec, n: int = 0, **over) -> dict:
    found = {
        "title": pair(f"Stage {n}"),
        "owner": "lead-qs",
        "starts": day(rec, n),
        "ends": day(rec, n),
        "outputs": [{"kind": "deliverable", "title": pair("Priced BOQ")}],
        "gate": pair("You approve it"),
        "requests": 10,
    }
    return found | over


def member(**over) -> dict:
    found = {
        "ref": "pricing-qs",
        "name": pair("Pricing QS"),
        "title": pair("Pricing Quantity Surveyor"),
        "speciality": pair("Rates"),
        "style": pair("Cites a source for every rate"),
        "tools": ["prices_lookup"],
    }
    return found | over


def plan_args(rec, stages=None, team=None, due=None) -> dict:
    return {
        "submission_date": due or day(rec, 10),
        "stages": stages or [stage(rec, 0), stage(rec, 1, owner="pricing-qs")],
        "team": [member()] if team is None else team,
    }


def draft(rec, **more) -> PlanDraft:
    given = PlanIn.model_validate(plan_args(rec, **more))
    found = model.estimate(model.work_of(given.stages), SHEET, None)
    return PlanDraft(given.submission_date.isoformat(), given.stages, given.team, found)


def lead_ctx(rec):
    ctx = tool_ctx(rec)
    ctx.host.setup = TeamSetup(tuple(SHEET), model.picked_roles(SHEET), None)
    return ctx


def refused(rec, **more) -> RecordsError:
    with pytest.raises(RecordsError) as e:
        store.propose(rec, draft(rec, **more))
    assert store.current(rec) is None  # nothing was stored
    return e.value


# The checks -------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("change", "field"),
    [
        (lambda rec: {"stages": [stage(rec, 2), stage(rec, 1)]}, "stages[1].starts"),
        (lambda rec: {"stages": [stage(rec, -1)]}, "stages[0].starts"),
        (lambda rec: {"stages": [stage(rec, 11)]}, "stages[0].starts"),
        (lambda rec: {"stages": [stage(rec, 2, ends=day(rec, 1))]}, "stages[0].ends"),
        (lambda rec: {"stages": [stage(rec, owner="estimator")]}, "stages[0].owner"),
        (lambda rec: {"stages": [stage(rec, title={"en": "Sample"})]}, "stages[0].title"),
        (lambda rec: {"stages": [stage(rec, gate={"ar": "عينة"})]}, "stages[0].gate"),
        (
            lambda rec: {"stages": [stage(rec, outputs=[{"kind": "map", "title": {}}])]},
            "stages[0].outputs[0].title",
        ),
        (lambda rec: {"team": [member(title={"en": "QS"})]}, "team[0].title"),
        (lambda rec: {"team": [member(tools=["delegate"])]}, "team[0].tools"),
        (lambda rec: {"team": [member(ref="lead-qs")]}, "team[0].ref"),
    ],
)
async def test_plan_write_validates(rec, change, field):
    due_in(rec)
    e = refused(rec, **change(rec))
    assert (e.status, e.field) == (422, field)
    assert set(e.text) == {"en", "ar"} and all(e.text.values())
    # The tool sends it back to the Lead with the field and a filled example.
    with pytest.raises(ModelRetry) as retry:
        await call(plan_tool.WRITE, plan_args(rec, **change(rec)), lead_ctx(rec))
    assert f"Field: {field}." in retry.value.message and "Example: {" in retry.value.message


def test_a_plan_that_fits_is_stored_as_version_one(rec):
    due = due_in(rec)
    plan = store.propose(rec, draft(rec))
    assert (plan.version, plan.status, plan.submission_date, plan.change) == (
        1,
        "proposed",
        due,
        None,
    )
    assert [s.status for s in plan.stages] == ["pending", "pending"]
    assert [m.id for m in plan.team][:2] == ["lead-qs", "checking-qs"]
    pricing = plan.team[2]
    assert (pricing.kind, pricing.role, len(pricing.id)) == ("temporary", "specialist", 32)
    assert plan.stages[1].owner_member_id == pricing.id
    # Proposed again: the next version, the same plan, stage and member ids.
    again = store.propose(rec, draft(rec, stages=[stage(rec, 0, id=plan.stages[0].id)]))
    assert (again.id, again.version, again.stages[0].id) == (plan.id, 2, plan.stages[0].id)
    assert again.team[2].id == pricing.id
    with pytest.raises(ValidationError):  # the day must be a real one
        PlanIn.model_validate(plan_args(rec, stages=[stage(rec, starts="2026-02-30")]))


async def test_plan_needs_submission_date(rec):
    assert refused(rec).text == copy.PLAN_NEEDS_SUBMISSION_DATE  # no date yet
    understand.correct(rec, {"submission_date": day(rec, -1)}, approve=False)
    e = refused(rec, due=day(rec, -1), stages=[stage(rec, -1)])
    assert (e.text, e.field) == (copy.PLAN_NEEDS_SUBMISSION_DATE, "submission_date")
    due_in(rec, 12)
    e = refused(rec)  # dated back from another day than the tender's
    assert e.field == "submission_date"
    assert e.text == copy.fill(copy.PLAN_DATE_NOT_FACT, date=day(rec, 12))
    with pytest.raises(ModelRetry) as retry:
        await call(plan_tool.WRITE, plan_args(rec), lead_ctx(rec))
    assert day(rec, 12) in retry.value.message


# The estimate -----------------------------------------------------------------------------------


async def test_plan_cost_shown(rec):
    due_in(rec)
    ctx = lead_ctx(rec)
    await call(plan_tool.WRITE, plan_args(rec), ctx)
    plan = store.current(rec)
    # Each stage on its owner's model, one Lead request each to hand it over, and one Checking
    # QS request per Deliverable: 10 + 1 + 1 on the Lead's and checker's models, twice.
    items = [
        {"tier": "lead", "requests": 10},
        {"tier": "lead", "requests": 1},
        {"tier": "checker", "requests": 1},
        {"tier": "specialist", "requests": 10},
        {"tier": "lead", "requests": 1},
        {"tier": "checker", "requests": 1},
    ]
    budget = costs.brief_budget(items, SHEET, model.picked_roles(SHEET), None)
    assert plan.expected_cost_usd == costs.usd_text(budget.usd) and budget.usd > 0
    assert plan.expected_minutes == budget.minutes == 8  # 24 requests of 20 s
    assert (plan.cost_basis.model_dump(), plan.paid) == (copy.BASIS_ASSUMED, True)


def test_a_model_with_no_price_has_no_cost(rec):
    unpriced = replace(CARD, price_in=None, price_out=None)
    found = model.estimate([("lead-qs", 5, 0)], [unpriced], None)
    assert (found.usd, found.paid) == (None, True)
    assert model.estimate([("lead-qs", 5, 0)], SAMPLE_SHEET, (1000, 100, 4)).basis == copy.fill(
        copy.BASIS_MEASURED, n=4
    )


# The part in the chat ---------------------------------------------------------------------------


async def test_plan_stream_part(rec):
    due_in(rec)
    ctx = lead_ctx(rec)
    said = await call(plan_tool.WRITE, plan_args(rec), ctx)
    plan = store.current(rec)
    parts = [e for e in ctx.host.events if isinstance(e, Data) and e.name == "plan"]
    pointer = {"plan_id": plan.id, "version": 1}
    assert [(p.id, p.data) for p in parts] == [(plan.id, pointer)]  # one, and a pointer only
    assert ctx.host.cards == []  # nothing is asked: the plan waits for its route
    again = plan_tool.stored_parts(ctx.brief_id, [(plan_tool.WRITE, said), ("files_list", "{}")])
    assert [(p.name, p.id, p.data) for p in again] == [("plan", plan.id, pointer)]


# The Suggested change ---------------------------------------------------------------------------


async def test_plan_change_after_approval_is_suggested(rec):
    due_in(rec)
    ctx = lead_ctx(rec)
    with pytest.raises(ModelRetry):  # nothing approved to change yet
        await call(plan_tool.CHANGE, {"change": plan_args(rec), "reason": "عينة"}, ctx)
    plan = store.propose(rec, draft(rec))
    store.approve(rec, version=1)
    first, second = (s.id for s in plan.stages)
    later = [stage(rec, 0, id=first), stage(rec, 2, id=second, owner="pricing-qs")]
    reason = "ملحق رقم 2 - عينة"
    args = {"change": plan_args(rec, stages=later), "reason": reason}
    said = await call(plan_tool.CHANGE, args, ctx)
    now = store.current(rec)
    assert (now.version, now.status, now.stages[1].ends) == (1, "approved", day(rec, 1))
    change = now.change
    assert (change.reason, change.stages[1].ends, change.stages[1].id) == (
        reason,
        day(rec, 2),
        second,
    )
    assert ctx.host.cards == []  # a Suggested change is not a card: the Lead's run goes on
    assert plan_tool.stored_parts(ctx.brief_id, [(plan_tool.CHANGE, said)])[0].data == {
        "plan_id": plan.id,
        "version": 1,
    }
    with pytest.raises(ModelRetry):  # the approved plan is not proposed again
        await call(plan_tool.WRITE, plan_args(rec), ctx)
    # Accepted: the version rises, the change is taken, the stage ids stay.
    accepted = store.answer_change(rec, change.id, True)
    assert (accepted.version, accepted.change, accepted.stages[1].ends) == (2, None, day(rec, 2))
    assert [s.id for s in accepted.stages] == [first, second]
    assert store.answer_change(rec, change.id, True) == accepted  # the same answer again
    with pytest.raises(RecordsError) as e:
        store.answer_change(rec, change.id, False)
    assert (e.value.text, e.value.field) == (copy.PLAN_CHANGED, "change_id")


def test_a_change_keeps_progress_and_cannot_alter_a_signed_off_stage(rec):
    due_in(rec)
    mapped = stage(rec, 0, outputs=[{"kind": "map", "title": pair("Register")}])
    plan = store.propose(rec, draft(rec, stages=[mapped, stage(rec, 1, owner="pricing-qs")]))
    store.approve(rec, version=1)
    first, second = (s.id for s in plan.stages)
    store.set_stage_status(rec, first, "waiting_engineer", result=pair("Done"))
    store.approve_stage(rec, first, version=1)
    store.set_stage_status(rec, second, "now", output_ids=["5a" + "0" * 30])
    kept = [mapped | {"id": first}, stage(rec, 1, id=second, owner="pricing-qs")]
    change = store.suggest(rec, draft(rec, stages=kept), "عينة").change
    assert [s.status for s in change.stages] == ["approved", "now"]  # the plan's own progress
    assert change.stages[0].result.model_dump() == pair("Done")
    assert change.stages[1].outputs[0].id == "5a" + "0" * 30
    altered = [mapped | {"id": first, "title": pair("Other")}, kept[1]]
    for bad, field in (
        (altered, "stages"),
        (kept[1:], "stages"),
        ([*kept, stage(rec, -1)], "stages[2].starts"),
    ):
        with pytest.raises(RecordsError) as e:
            store.suggest(rec, draft(rec, stages=bad), "عينة")
        assert e.value.field == field
    assert store.current(rec).change == change  # a refused suggestion changes nothing
    for moved in ((first, "now"), (second, "approved")):
        with pytest.raises(ValueError):  # signed off stays; signing off is approve_stage
            store.set_stage_status(rec, *moved)
