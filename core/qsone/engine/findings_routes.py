"""Routes 13 and 14 of the Phase 1 contract: a tender's Findings, and the engineer's decision.

Deciding gives the decision to the Lead: a steer when work runs in the tender; otherwise ONE
starts the Lead's work on it. When that work would have to start and the Lead cannot work, the
route refuses and stores nothing."""

import asyncio
import logging

from fastapi import APIRouter

from qsone import copy
from qsone import phase1_contract as c
from qsone.engine import finding_tools, findings  # noqa: F401 - registers the Finding tools
from qsone.home_block import project_block
from qsone.journey import setup_state
from qsone.records.project import RecordsError

log = logging.getLogger(__name__)


def _refusals(*codes: int) -> dict:
    bad = c.Refusal | c.BodyProblem  # 422: a body the screen built wrongly
    return {code: {"model": bad if code == 422 else c.Refusal} for code in codes}


def _for_lead(finding: dict) -> str:
    """The decision in the Lead's words: what it steers or starts."""
    n = finding["chosen"]
    option = finding["options"][n]["en"]
    return (
        f"The engineer decided the Finding {finding['id']} «{finding['title']['en']}»: option "
        f"{n + 1}, «{option}». Go on with the work that waited for this decision."
    )


async def _tell_lead(engine, project_id: str, finding: dict) -> None:
    from qsone.engine.runner import BriefBusy, NoAI

    steer = _for_lead(finding)
    option = finding["options"][finding["chosen"]]
    said = copy.fill(copy.FINDING_DECIDED, title=finding["title"], option=option)
    for _ in range(2):  # a Brief may start or end between the two calls
        busy = engine.active(project_id, include_mapping=False)
        try:
            if busy is not None:
                await engine.steer(busy, steer)
            else:
                lang = setup_state.language()
                await engine.start_brief(project_id, said[lang], instruction=steer, by="one")
            return
        except (LookupError, BriefBusy):
            continue
        except NoAI:
            break
    log.warning("the decision on a Finding reached no work of the Lead")


def router(engine) -> APIRouter:
    r = APIRouter()

    @r.get(
        "/projects/{project_id}/findings",
        response_model=c.Findings,
        responses=_refusals(404, 409),
    )
    async def tender_findings(project_id: str):
        try:
            rec = engine.projects.get(project_id)
            return {"findings": await asyncio.to_thread(findings.listed, rec)}
        except RecordsError as e:
            return c.refusal(e.text, e.status)

    @r.post(
        "/projects/{project_id}/findings/{finding_id}/decide",
        response_model=c.Finding,
        responses=_refusals(404, 409, 422, 423),
    )
    async def decide_finding(project_id: str, finding_id: str, body: c.DecideIn):
        from qsone.engine.runner import NoAI
        from qsone.engine.runner.shared import kept_here

        try:
            rec = engine.projects.get(project_id)
            if engine.active(project_id, include_mapping=False) is None:
                current = next(
                    (f for f in await asyncio.to_thread(findings.listed, rec)
                     if f["id"] == finding_id), None,
                )  # fmt: skip
                if current is not None and current["status"] == "raised":
                    if (blocked := project_block(engine, rec)) is not None:
                        return c.refusal(blocked["reason"])
                    try:
                        # the Lead's work would start: is there a model it may use here?
                        kept_here(rec, (await engine.sheet())[0])
                    except NoAI as none:
                        return c.refusal(none.text, 409)
            settled, changed = await asyncio.to_thread(
                findings.decide, rec, finding_id, body.choice
            )
        except RecordsError as e:
            return c.refusal(e.text, e.status)
        findings.publish(project_id, changed)
        if changed:
            from qsone.engine import room  # the team room's raised message is answered (C6)

            room.finding_decided(rec, finding_id)
            await _tell_lead(engine, project_id, settled)
        return settled

    return r
