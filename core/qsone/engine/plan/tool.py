"""The Lead's two plan tools: `tender_plan_write` proposes the tender plan, `tender_plan_change`
suggests a change to the approved one.

Both check the plan in code (`model.check`), work out its expected cost and time from the
Brief's Model Data Sheet (`model.estimate`) and store it (`store`). Neither asks the engineer
anything: a proposed plan waits for route 10 and a Suggested change for route 12, so the Lead's
run goes on. Each places a `data-plan` part in the reply, a pointer that holds no state; it is
given again from the stored tool results (`stored_parts`)."""

import asyncio
import json

from pydantic import Field

from qsone import copy
from qsone.engine.plan import model, store
from qsone.engine.plan.model import PlanDraft, PlanIn, _Args
from qsone.engine.team.common import _setup
from qsone.engine.tools import ModelRetry, Tool, ToolContext, register
from qsone.engine.types import Data
from qsone.records.project import RecordsError

WRITE = "tender_plan_write"
CHANGE = "tender_plan_change"
PART = "plan"  # the chat's `data-plan` part


class ChangeIn(_Args):
    change: PlanIn  # the whole plan as it would be
    reason: str = Field(min_length=1, max_length=2000)  # why, in the engineer's language


_STAGE = {
    "title": {"en": "Pricing the BOQ", "ar": "تسعير جدول الكميات"},
    "owner": "pricing-qs",
    "starts": "2026-11-12",
    "ends": "2026-11-15",
    "outputs": [{"kind": "deliverable", "title": {"en": "Priced BOQ", "ar": "جدول كميات مسعّر"}}],
    "gate": {"en": "You approve the rates", "ar": "موافقتك على الأسعار"},
    "requests": 40,
}
_MEMBER = {
    "ref": "pricing-qs",
    "name": {"en": "Pricing QS", "ar": "مهندس التسعير"},
    "title": {"en": "Pricing Quantity Surveyor", "ar": "مهندس كميات التسعير"},
    "speciality": {"en": "Rates build-up agent", "ar": "وكيل تحليل الأسعار"},
    "style": {"en": "Cites a source for every rate", "ar": "بيذكر مصدر لكل سعر"},
    "tools": ["prices_lookup"],
}
_EXAMPLE = {"submission_date": "2026-11-21", "stages": [_STAGE], "team": [_MEMBER]}
_CHANGE_EXAMPLE = {
    "change": {"submission_date": "2026-11-23", "stages": [_STAGE | {"id": "<stage id>"}]},
    "reason": "Addendum 2 moved the submission date by two days.",
}

_WRITE_DOC = f"""Propose the tender plan: its stages in order and the team, for the engineer to \
approve once. Write it after the tender is read, when its submission date is known.
- submission_date: the tender's own date, as its facts hold it. Without one, ask the engineer \
for it with ask_engineer first; never invent one.
- stages, in order, dated from today back from the submission date. Each: title and gate \
(what the engineer signs off) in English and Arabic; owner: lead-qs, checking-qs or a team \
ref; starts and ends (YYYY-MM-DD); outputs (deliverable, file, map or summary, each with a \
title); engineer_supplies for a stage ONE cannot do alone (what the engineer brings); \
requests, about how many model requests its work needs. A stage already in the plan keeps \
its id.
- team: the members you propose beside the Lead and the Checking QS, each with a ref the \
stages use, a short name, a QS title, speciality and style in both languages, and its tools.
ONE shows the plan with its cost and time; the engineer approves it or discusses it. Calling \
again proposes the next version. After approval, use {CHANGE}.
Example:
{json.dumps(_EXAMPLE, ensure_ascii=False)}"""

_CHANGE_DOC = f"""Suggest a change to the approved tender plan: the whole plan as it would be, \
with the reason, as for {WRITE}. Keep every stage's id; a signed-off stage stays as it is. The \
engineer accepts or rejects it; until then work goes on under the approved plan. A newer \
suggestion replaces one that waits.
Example:
{json.dumps(_CHANGE_EXAMPLE, ensure_ascii=False)}"""


def _part(ctx: ToolContext, plan) -> None:
    ctx.host.emit(Data(ctx.brief_id, PART, plan.id, {"plan_id": plan.id, "version": plan.version}))


def _draft(ctx: ToolContext, plan: PlanIn) -> PlanDraft:
    setup = _setup(ctx)
    found = model.estimate(model.work_of(plan.stages), list(setup.sheet), setup.measured)
    return PlanDraft(
        plan.submission_date.isoformat(), plan.stages, plan.team, found, setup.measured
    )


def _answer(plan, done: str) -> str:
    return json.dumps(
        {
            done: True,
            "plan_id": plan.id,
            "version": plan.version,
            "expected_cost_usd": plan.expected_cost_usd,
            "expected_minutes": plan.expected_minutes,
            "note": "The engineer sees it with its cost and time and answers on the plan. "
            "End your reply: say in a line what you propose and why.",
        }
    )


async def _write(ctx: ToolContext, args: PlanIn) -> str:
    if ctx.rec is None:
        raise RecordsError(copy.PROJECT_NOT_OPEN)
    now = await asyncio.to_thread(store.current, ctx.rec)
    if now is not None and now.status == "approved":
        raise ModelRetry(f"{WRITE}: the plan is approved. Suggest a change with {CHANGE}.")
    plan = await asyncio.to_thread(store.propose, ctx.rec, _draft(ctx, args))
    _part(ctx, plan)
    return _answer(plan, "proposed")


async def _change(ctx: ToolContext, args: ChangeIn) -> str:
    if ctx.rec is None:
        raise RecordsError(copy.PROJECT_NOT_OPEN)
    now = await asyncio.to_thread(store.current, ctx.rec)
    if now is None or now.status != "approved":
        raise ModelRetry(f"{CHANGE}: the plan is not approved yet. Propose it with {WRITE}.")
    plan = await asyncio.to_thread(store.suggest, ctx.rec, _draft(ctx, args.change), args.reason)
    _part(ctx, plan)
    return _answer(plan, "suggested")


def stored_parts(brief_id: str, results: list[tuple[str, str]]) -> list[Data]:
    """The `data-plan` parts again, from the Lead's stored tool results."""
    found = []
    for name, text in results:
        if name not in (WRITE, CHANGE):
            continue
        try:
            data = json.loads(text)
        except ValueError:
            continue
        if isinstance(data, dict) and isinstance(data.get("plan_id"), str):
            pointer = {"plan_id": data["plan_id"], "version": data["version"]}
            found.append(Data(brief_id, PART, data["plan_id"], pointer))
    return found


for _name, _args, _run, _doc, _example in (
    (WRITE, PlanIn, _write, _WRITE_DOC, _EXAMPLE),
    (CHANGE, ChangeIn, _change, _CHANGE_DOC, _CHANGE_EXAMPLE),
):
    _step = copy.tool_step(_name)
    register(
        Tool(
            name=_name,
            description=_doc,
            args=_args,
            risk="write",
            run=_run,
            activity=lambda _, step=_step: step,
            writes=True,
            lead_only=True,
            example=_example,
            roles=frozenset({"lead"}),
            group="records",
        )
    )
