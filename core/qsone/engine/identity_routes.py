"""The team's routes (contract rows 15-16): a tender's team, and the list for Settings → Team.
Both answer from what the core holds; neither calls an AI provider."""

import logging

from fastapi import APIRouter

from qsone import phase1_contract as c
from qsone.engine import identity, identity_live
from qsone.journey import setup_state
from qsone.records.project import RecordsError

log = logging.getLogger(__name__)
_REFUSAL = {"model": c.Refusal}


def router(projects, engine) -> APIRouter:
    r = APIRouter()

    # On the event loop, as the running Briefs' state is read there.
    @r.get(
        "/projects/{project_id}/members",
        response_model=c.TeamMembers,
        responses={404: _REFUSAL, 409: _REFUSAL},
    )
    async def tender_team(project_id: str):
        try:
            rec = projects.get(project_id)
            engineer = engine.engineer_records()
            return c.TeamMembers(members=identity_live.team_members(engine, rec, engineer))
        except RecordsError as e:
            return c.refusal(e.text, e.status, field=e.field)

    @r.get("/team/members", response_model=c.Members, responses={409: _REFUSAL, 503: _REFUSAL})
    async def permanent_team():
        try:
            return c.Members(members=identity.permanent(engine.engineer_records()))
        except RecordsError as e:
            return c.refusal(e.text, e.status, field=e.field)

    return r


async def list_models(engine) -> None:
    """Once after the app starts, with the AI consent given: the Model Data Sheet, so each
    member's model has a name before the first work. A listing that fails changes nothing."""
    if setup_state.consent() is None:
        return
    try:
        await engine.sheet()  # it remembers the sheet
    except Exception as e:  # no AI linked, a provider down: the members' model stays null
        log.info("Listing the models for the team did not work (%s)", type(e).__name__)
