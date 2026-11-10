"""Try again (row 25 of the Phase 1 contract): `POST /briefs/{brief_id}/retry` starts the work of
a Brief that ended `failed` or `stopped` again, as a new Brief in the same conversation with the
same words, started by ONE. A stage's work stays that stage's work: its retry is the stage's
next attempt (`PlanDriver.retry`), so the driver never has two. Only the last Brief of a
conversation is retried, and never while work runs there. `continue` is unchanged: it goes on
from the Checkpoint of work that was cut off."""

import asyncio
import re

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from qsone import copy
from qsone import phase1_contract as c
from qsone.engine.plan import claims
from qsone.engine.runner import GENERAL, BriefBusy, NoAI
from qsone.engine.store import Store
from qsone.home_block import lead_block
from qsone.records.project import Records, RecordsError

_ID = re.compile(r"[0-9a-f]{32}")


def _refusals(*codes: int) -> dict:
    return {code: {"model": c.Refusal} for code in codes}


def _find(engine, brief_id: str) -> tuple[Records, str, dict, bool] | None:
    """The Brief in the Home conversation or an open tender: its file, chat, row, and whether
    it is the last Brief of its chat. Opens no closed tender."""
    if not _ID.fullmatch(brief_id):
        return None
    places = [(GENERAL, engine.engineer_records())] + list(engine.projects.opened())
    for chat_id, rec in places:
        if not rec.is_open:
            continue
        try:
            brief = Store(rec, project_id=None if chat_id == GENERAL else chat_id).brief(brief_id)
        except LookupError:
            continue
        with rec.read() as conn:
            (last,) = conn.execute(
                "SELECT id FROM briefs WHERE chat_id = ? ORDER BY created_at DESC, rowid DESC"
                " LIMIT 1",
                (brief["chat_id"],),
            ).fetchone()
        return rec, brief["chat_id"], brief, last == brief_id
    return None


def router(engine, driver) -> APIRouter:
    r = APIRouter()

    @r.post(
        "/briefs/{brief_id}/retry",
        status_code=202,
        response_model=c.BriefStarted,
        responses=_refusals(404, 409, 423),
    )
    async def retry_brief(brief_id: str):
        try:
            found = await asyncio.to_thread(_find, engine, brief_id)
            if found is None or not found[3] or found[2]["status"] not in ("failed", "stopped"):
                return c.refusal(copy.BRIEF_NOT_FOUND, 404)
            rec, chat_id, brief, _ = found
            if rec.archived_at is not None:
                return c.refusal(copy.PROJECT_ARCHIVED, 423)
            if (busy := engine.active(chat_id)) is not None:
                return c.refusal(copy.WORK_RUNNING, brief_id=busy)
            if (blocked := lead_block(engine)) is not None:
                return c.refusal(blocked["reason"])
            with rec.read() as conn:
                stage_id = claims.stage_of(conn, brief_id)
            if stage_id is not None:
                new = await driver.retry(chat_id, stage_id, brief_id)
            else:
                new = await engine.start_brief(
                    chat_id,
                    brief["text"],
                    selection=brief["selection"],
                    effort=brief["effort"],
                    by="one",
                )
        except BriefBusy as busy:
            return c.refusal(copy.WORK_RUNNING, brief_id=busy.brief_id)
        except NoAI as none:
            return c.refusal(none.text)
        except LookupError:
            return c.refusal(copy.BRIEF_NOT_FOUND, 404)
        except RecordsError as e:
            return c.refusal(e.text, e.status, field=e.field)
        return JSONResponse({"brief_id": new}, status_code=202)

    return r
