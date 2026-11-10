"""The tender plan in Project Records: one plan per tender, every state of it kept.

Each change appends a row to `tender_plans` holding the whole plan; the newest row is the plan
now. A row's body is `{"plan": TenderPlan, "requests": {stage id: n}, "measured": [in, out, n] |
None, "refs": {ref: member id}, "change_requests", "change_measured", "answered": {"id",
"accept"} | None}`: the plan as the contract sends it, with what its estimate (and a waiting
change's) is worked out from and what makes an answer safe to repeat.

- `version` rises when what the engineer approves changes: the plan proposed again, a Suggested
  change accepted, or an estimate that came out different at approval. A stage moving, or a
  change suggested, keeps the version.
- Every write publishes the `plan` event after it commits (`events.held`); every refusal changes
  nothing. Approving what is approved already answers the plan and writes nothing."""

import json
from datetime import date
from uuid import uuid4

from qsone import copy
from qsone import phase1_contract as c
from qsone.deliverables import events
from qsone.engine.plan import build, members, signoff
from qsone.engine.plan.model import Estimate, PlanDraft, check_date
from qsone.records import audit
from qsone.records.project import Records, RecordsError

ENGINEER = "engineer"
LEAD_ACTOR = "lead_qs"
TABLE = "tender_plans"
STEPS = ("pending", "now", "waiting_engineer")  # what `set_stage_status` may set


# Reading ----------------------------------------------------------------------------------------


def _body(conn) -> dict | None:
    found = conn.execute(f"SELECT body FROM {TABLE} ORDER BY rev DESC LIMIT 1").fetchone()
    return None if found is None else json.loads(found[0])


def _shown(body: dict) -> c.TenderPlan:
    """The plan as sent: a waiting change's stages carry the plan's own status, result and
    output ids."""
    plan = json.loads(json.dumps(body["plan"]))
    if plan["change"] is not None:
        now = {s["id"]: s for s in plan["stages"]}
        plan["change"]["stages"] = [
            build.kept(now.get(s["id"]), s) for s in plan["change"]["stages"]
        ]
    return c.TenderPlan.model_validate(plan)


def current(project: Records) -> c.TenderPlan | None:
    """The tender's plan now, or None when it has none (a project made before plans, too)."""
    with project.read() as conn:
        body = _body(conn)
    return None if body is None else _shown(body)


def plan_view(project: Records) -> c.PlanView:
    """The one body the plan travels in: `{"plan": TenderPlan | None}`."""
    return c.PlanView(plan=current(project))


def body(project: Records) -> dict | None:
    """The stored body of the plan now (with what its estimate is worked out from), or None."""
    with project.read() as conn:
        return _body(conn)


def _fact(conn) -> str | None:
    found = conn.execute(
        "SELECT json_extract(fields, '$.value') FROM items WHERE kind = 'project_fact'"
        " AND json_extract(fields, '$.name') = 'submission_date'"
        " ORDER BY created_at DESC, rowid DESC LIMIT 1"
    ).fetchone()
    return None if found is None else found[0]


def submission_fact(project: Records) -> str | None:
    """The tender fact `submission_date` (what GET .../facts gives), or None."""
    with project.read() as conn:
        return _fact(conn)


def today(project: Records) -> date:
    return date.fromisoformat(project.clock()[:10])


# Writing ----------------------------------------------------------------------------------------


def _save(conn, project: Records, new: dict, actor: str, action: str) -> c.TenderPlan:
    """Inside `events.held` and a write: the next row and its audit row; the event is sent
    once the write commits."""
    plan = new["plan"]
    at = project.clock()
    cur = conn.execute(
        f'INSERT INTO {TABLE} (plan_id, version, body, at, "by") VALUES (?, ?, ?, ?, ?)',
        (plan["id"], plan["version"], json.dumps(new, ensure_ascii=False), at, actor),
    )
    after = {"version": plan["version"], "status": plan["status"], "rev": cur.lastrowid}
    audit.record(
        conn,
        at=at,
        actor=actor,
        action=action,
        table=TABLE,
        row_id=plan["id"],
        before=None,
        after=after,
    )
    shown = _shown(new)
    events.publish(project.id, {"type": "plan", "plan": shown.model_dump(mode="json")})
    return shown


def _found(conn) -> dict:
    found = _body(conn)
    if found is None:
        raise RecordsError(copy.PLAN_NOT_FOUND, status=404)
    return found


def _version(plan: dict, version: int | None) -> None:
    if version is not None and version != plan["version"]:
        raise RecordsError(copy.PLAN_CHANGED, field="version")


def _dated(conn, project: Records, submission_date: str) -> None:
    """PLAN_NEEDS_SUBMISSION_DATE unless the tender's date is there, has not passed and is the
    one the plan was dated back from."""
    if check_date(_fact(conn), today(project)).isoformat() != submission_date:
        raise RecordsError(copy.PLAN_NEEDS_SUBMISSION_DATE, field="submission_date")


def propose(project: Records, draft: PlanDraft, *, actor: str = LEAD_ACTOR) -> c.TenderPlan:
    """Stores the plan as proposed: version 1, or the next version of a proposed plan. Raises
    `RecordsError`: a value that does not fit (`model.check`), PLAN_NEEDS_SUBMISSION_DATE, and
    PLAN_APPROVED for an approved plan (a change to it is `suggest`)."""
    with events.held(), project.write(actor) as conn:
        found = _body(conn)
        if found is not None and found["plan"]["status"] == "approved":
            raise RecordsError(copy.PLAN_APPROVED)
        made = build.built(
            project, found, draft, fact=_fact(conn), today=today(project), change=False
        )
        plan = made["plan"] | {
            "id": uuid4().hex if found is None else found["plan"]["id"],
            "version": 1 if found is None else found["plan"]["version"] + 1,
            "status": "proposed",
            "approved_at": None,
            "change": None,
        }
        answered = None if found is None else found.get("answered")
        new = made | {
            "plan": plan,
            "change_requests": {},
            "change_measured": None,
            "answered": answered,
        }
        return _save(conn, project, new, actor, "propose")


def suggest(
    project: Records, draft: PlanDraft, reason: str, *, actor: str = LEAD_ACTOR
) -> c.TenderPlan:
    """Stores a Suggested change to the approved plan under a new id, in place of one that
    waits. Raises `RecordsError`: PLAN_NOT_FOUND, PLAN_NOT_APPROVED, PLAN_STAGE_LOCKED, and
    what `propose` raises."""
    with events.held(), project.write(actor) as conn:
        found = _found(conn)
        if found["plan"]["status"] != "approved":
            raise RecordsError(copy.PLAN_NOT_APPROVED)
        made = build.built(
            project, found, draft, fact=_fact(conn), today=today(project), change=True
        )
        change = made["plan"] | {"id": uuid4().hex, "reason": reason}
        new = found | {
            "plan": found["plan"] | {"change": change},
            "refs": made["refs"],
            "change_requests": made["requests"],
            "change_measured": made["measured"],
        }
        return _save(conn, project, new, actor, "suggest")


def approve(
    project: Records, *, version: int | None = None, estimate: Estimate | None = None
) -> c.TenderPlan:
    """Approves the plan and its team, by the engineer. `version` is the one on screen;
    `estimate` the figures worked out again now: when they differ, the next version is stored
    with them and PLAN_CHANGED is raised. Raises `RecordsError`: PLAN_NOT_FOUND (404),
    PLAN_CHANGED (`field: "version"`), PLAN_NEEDS_SUBMISSION_DATE. An approved plan of that
    version is answered as it is."""
    with events.held(), project.write(ENGINEER) as conn:
        found = _found(conn)
        plan = found["plan"]
        _version(plan, version)
        if plan["status"] == "approved":
            return _shown(found)
        _dated(conn, project, plan["submission_date"])
        if estimate is not None and not estimate.same_figures(build.figures(plan)):
            again = build.with_estimate(plan, estimate) | {"version": plan["version"] + 1}
            _save(conn, project, found | {"plan": again}, ENGINEER, "estimate")
        else:
            done = plan | {"status": "approved", "approved_at": project.clock()}
            members.answered(project, accepted=True)  # one approval covers the team
            return _save(conn, project, found | {"plan": done}, ENGINEER, "approve")
    raise RecordsError(copy.PLAN_CHANGED, field="version")  # the new figures are stored


def answer_change(
    project: Records, change_id: str, accept: bool, *, estimate: Estimate | None = None
) -> c.TenderPlan:
    """Accepts or rejects the Suggested change `change_id`, by the engineer. Accepting takes
    the change's dates, stages, team and figures, keeps each stage's progress and raises the
    version; when `estimate` (worked out again now) differs, the change is stored again under a
    new id and PLAN_CHANGED is raised. Raises `RecordsError`: PLAN_NOT_FOUND (404), PLAN_CHANGED
    (`field: "change_id"`) for a change that is not the one waiting, PLAN_NEEDS_SUBMISSION_DATE
    on accept. The same answer to a change settled that way is answered with the plan."""
    with events.held(), project.write(ENGINEER) as conn:
        found = _found(conn)
        plan, change = found["plan"], found["plan"]["change"]
        if change is None or change["id"] != change_id:
            if found.get("answered") == {"id": change_id, "accept": accept}:
                return _shown(found)
            raise RecordsError(copy.PLAN_CHANGED, field="change_id")
        answered = {"id": change_id, "accept": accept}
        if not accept:
            new = found | {"plan": plan | {"change": None}, "answered": answered}
            members.answered(project, accepted=False)
            return _save(conn, project, new, ENGINEER, "reject")
        _dated(conn, project, change["submission_date"])
        if estimate is not None and not estimate.same_figures(build.figures(change)):
            again = build.with_estimate(change, estimate) | {"id": uuid4().hex}
            _save(conn, project, found | {"plan": plan | {"change": again}}, ENGINEER, "estimate")
        else:
            now = {s["id"]: s for s in plan["stages"]}
            stages = [build.kept(now.get(s["id"]), s) for s in change["stages"]]
            taken = {k: v for k, v in change.items() if k not in ("id", "reason")}
            accepted = plan | taken | {"stages": stages, "version": plan["version"] + 1}
            new = found | {
                "plan": accepted | {"change": None},
                "requests": found["change_requests"],
                "measured": found.get("change_measured"),
                "change_requests": {},
                "change_measured": None,
                "answered": answered,
            }
            members.answered(project, accepted=True)
            return _save(conn, project, new, ENGINEER, "accept")
    raise RecordsError(copy.PLAN_CHANGED, field="change_id")  # stored again with new figures


def _stage_of(plan: dict, stage_id: str) -> dict:
    for stage in plan["stages"]:
        if stage["id"] == stage_id:
            return stage
    raise RecordsError(copy.STAGE_NOT_FOUND, status=404)


def _with_stage(found: dict, stage: dict) -> dict:
    stages = [stage if s["id"] == stage["id"] else s for s in found["plan"]["stages"]]
    return found | {"plan": found["plan"] | {"stages": stages}}


def approve_stage(project: Records, stage_id: str, *, version: int | None = None) -> c.TenderPlan:
    """Signs off a stage whose work ended, by the engineer, in one write: every Deliverable
    among its outputs not signed off yet (by the close-out rule), the tender summary when it is
    an output, then the stage. The Deliverable and plan events go after the write commits.
    Raises `RecordsError`: PLAN_NOT_FOUND or STAGE_NOT_FOUND (404), PLAN_CHANGED, STAGE_NOT_WAITING,
    STAGE_OUTPUT_NOT_READY (`field: "outputs"`). A stage signed off already is answered as it is."""
    with events.held(), project.write(ENGINEER) as conn:
        found = _found(conn)
        _version(found["plan"], version)
        stage = _stage_of(found["plan"], stage_id)
        if stage["status"] == "approved":
            return _shown(found)
        if stage["status"] != "waiting_engineer":
            raise RecordsError(copy.STAGE_NOT_WAITING)
        signoff.sign(project, conn, stage["outputs"], actor=ENGINEER)
        new = _with_stage(found, stage | {"status": "approved"})
        return _save(conn, project, new, ENGINEER, "stage")


def set_stage_status(
    project: Records,
    stage_id: str,
    status: str,
    *,
    result: dict | None = None,
    output_ids: list[str | None] | None = None,
    actor: str = LEAD_ACTOR,
) -> c.TenderPlan:
    """Moves a stage of the approved plan (the plan driver): `pending`, `now` or
    `waiting_engineer`, with its one-line `result` ({en, ar}) and the ids of its outputs once
    they exist (one per output, None for one not made). Signing off is `approve_stage` only.
    Raises `RecordsError` PLAN_NOT_FOUND or STAGE_NOT_FOUND (404); `ValueError` for anything
    else this does not take."""
    if status not in STEPS:
        raise ValueError(f"a stage is set to one of {STEPS}; signing off is approve_stage")
    with events.held(), project.write(actor) as conn:
        found = _found(conn)
        if found["plan"]["status"] != "approved":
            raise ValueError("only a stage of an approved plan moves")
        stage = _stage_of(found["plan"], stage_id)
        if stage["status"] == "approved":
            raise ValueError("a stage that is signed off does not move")
        moved = stage | {"status": status}
        if result is not None:
            moved["result"] = c.Text.model_validate(result).model_dump()
        if output_ids is not None:
            if len(output_ids) != len(stage["outputs"]):
                raise ValueError("one id per output, None for one not made yet")
            moved["outputs"] = [
                o | {"id": i} for o, i in zip(stage["outputs"], output_ids, strict=True)
            ]
        return _save(conn, project, _with_stage(found, moved), actor, "move")
