"""A plan as it is stored, built from what the Lead wrote: stages that keep their ids and their
progress, the team, the figures, and the checks that need the plan as it stands now."""

from datetime import date
from uuid import uuid4

from qsone import copy
from qsone.engine.plan import members, model
from qsone.engine.plan.model import Estimate, PlanDraft, PlanIn, StageIn
from qsone.records.project import Records, RecordsError


def with_estimate(target: dict, found: Estimate) -> dict:
    return target | {
        "expected_cost_usd": found.usd,
        "expected_minutes": found.minutes,
        "cost_basis": found.basis,
        "paid": found.paid,
    }


def figures(target: dict) -> Estimate:
    return Estimate(
        target["expected_cost_usd"],
        target["expected_minutes"],
        target["cost_basis"],
        target["paid"],
    )


def kept(old: dict | None, new: dict) -> dict:
    """`new` with the status, result and output ids of the stage it already is. An output keeps
    its id when it is at the same place with the same kind."""
    if old is None:
        return new
    outputs = []
    for i, output in enumerate(new["outputs"]):
        was = old["outputs"][i] if i < len(old["outputs"]) else None
        same = was is not None and was["kind"] == output["kind"]
        outputs.append(output | {"id": was["id"]} if same else output)
    return new | {"status": old["status"], "result": old["result"], "outputs": outputs}


def _plain(stage: dict) -> dict:
    """A stage as the engineer approved it: everything but its progress."""
    outputs = [{"kind": o["kind"], "title": o["title"]} for o in stage["outputs"]]
    rest = {k: v for k, v in stage.items() if k not in ("status", "result", "outputs")}
    return rest | {"outputs": outputs}


def _pair(value) -> dict | None:
    return None if value is None else {"en": value.en, "ar": value.ar}


def _stage(stage: StageIn, ids: dict[str, str]) -> dict:
    return {
        "id": stage.id or uuid4().hex,
        "title": _pair(stage.title),
        "owner_member_id": ids[stage.owner],
        "engineer_supplies": _pair(stage.engineer_supplies),
        "starts": stage.starts.isoformat(),
        "ends": stage.ends.isoformat(),
        "status": "pending",
        "result": None,
        "outputs": [{"kind": o.kind, "title": _pair(o.title), "id": None} for o in stage.outputs],
        "gate": _pair(stage.gate),
    }


def built(
    project: Records,
    body: dict | None,
    draft: PlanDraft,
    *,
    fact: str | None,
    today: date,
    change: bool,
) -> dict:
    """`{"plan": {submission_date, stages, team, figures}, "requests", "measured", "refs"}` from
    `draft`,
    checked against the plan now (`body`). A change may not remove or alter a stage that is
    signed off (PLAN_STAGE_LOCKED); the dates of a stage that has begun are not held to today."""
    now = {} if body is None else {s["id"]: s for s in body["plan"]["stages"]}
    begun = frozenset(i for i, s in now.items() if s["status"] != "pending")
    given = PlanIn(
        submission_date=date.fromisoformat(draft.submission_date),
        stages=draft.stages,
        team=draft.team,
    )
    model.check(
        given,
        fact=fact,
        today=today,
        known=now,
        allowed_tools=members.member_tools(),
        locked=begun if change else frozenset(),
    )
    refs = dict({} if body is None else body["refs"])
    ids = members.identity_check(project, draft.team, refs)
    refs |= {member.ref: i for member, i in zip(draft.team, ids, strict=True)}
    ids = {**{fixed: fixed for fixed in model.FIXED}, **refs}
    stages = [kept(now.get(s.id) if s.id else None, _stage(s, ids)) for s in draft.stages]
    if change:
        by_id = {s["id"]: s for s in stages}
        for stage_id, stage in now.items():
            new = by_id.get(stage_id)
            if stage["status"] == "approved" and (new is None or _plain(new) != _plain(stage)):
                text = copy.fill(copy.PLAN_STAGE_LOCKED, stage=stage["title"])
                raise RecordsError(text, status=422, field="stages")
    plan = {
        "submission_date": draft.submission_date,
        "stages": stages,
        "team": members.members(draft.team, refs),
    }
    requests = {stage["id"]: s.requests for stage, s in zip(stages, draft.stages, strict=True)}
    measured = None if draft.measured is None else list(draft.measured)
    plan = with_estimate(plan, draft.estimate)
    return {"plan": plan, "requests": requests, "measured": measured, "refs": refs}


def work(stages: list[dict], requests: dict[str, int]) -> list[model.Work]:
    """What the estimate of stored stages is worked out from."""
    return [
        (
            s["owner_member_id"],
            requests.get(s["id"], 1),
            sum(1 for o in s["outputs"] if o["kind"] == "deliverable"),
        )
        for s in stages
    ]
