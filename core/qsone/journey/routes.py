"""The journey's routes (Plan 8): the first launch's steps, the AI consent, Claude Code, the AI
check, the introduction card and the outside links the core opens for the page (decision 6);
a tender folder's "I understood this" card; and closing a project: the checklist, its lessons
and the archive."""

import asyncio
import webbrowser
from typing import Any, Literal
from uuid import uuid4

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from qsone import chat, copy, usage
from qsone.engine import connectors as engine_connectors
from qsone.engine import roles
from qsone.engine.connectors import claude_code as claude_link
from qsone.journey import claude_code, closing, engineer, setup_state, understand
from qsone.journey.setup_state import Language, State

LINKS = {
    "terms": "https://qsmind.app/{lang}/terms",  # the website's own pages, both languages
    "privacy": "https://qsmind.app/{lang}/privacy",
    "releases": "https://github.com/qs-mind/one/releases",
    "sign_in": "https://auth.qsmind.app/{lang}/account",
}

Step = Literal["language", "account", "ai", "card", "usage"]


class StepIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: State
    lang: Language | None = None  # the language step: the language the engineer chose


class ConsentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text_version: int = Field(ge=1, le=1000)


class CheckIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    via: Literal["api_key", "claude_code", "standard"]
    connector: str | None = Field(None, max_length=200)  # a Standard Link's id (audit R16)


class OpenIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    link: Literal["terms", "privacy", "releases", "sign_in"]
    lang: Language | None = None  # the page's language; else the one chosen at the first launch


FactName = Literal["client", "submission_date", "contract_type", "items_count"]


class FactIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    value: str = Field(min_length=1, max_length=300)


class FactsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    facts: dict[FactName, FactIn] = Field(default_factory=dict)
    approve: bool = False


class CarryIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    carry: bool


def _not_saved() -> JSONResponse:
    return JSONResponse({}, status_code=503)  # the screen says it in its own words


def router(engine: Any) -> APIRouter:
    """`engine` is the app's Brief Runner: its Engineer Records hold the card, and its
    connectors are the ones the check goes through."""
    r = APIRouter()

    @r.get("/setup")
    def get_setup() -> dict:
        return setup_state.setup()

    @r.put("/setup/{step}")
    def put_setup(step: Step, body: StepIn) -> JSONResponse:
        try:
            if step == "language" and body.lang is not None:
                setup_state.set_language(body.lang)
            if step == "usage" and body.state == "skipped" and usage.is_on() is None:
                usage.set_on(False)  # skipping means don't share
            answer = setup_state.mark(step, body.state)
        except OSError:
            return _not_saved()
        usage.track("setup_step", step=step, state=body.state)
        if step == "ai" and body.state == "skipped":
            usage.track("ai_link", via="none")
        return JSONResponse(answer)

    @r.get("/settings/ai-consent")
    def get_consent() -> dict:
        given = setup_state.consent()
        at = given["at"] if given else None
        return {"at": at, "text_version": setup_state.CONSENT_VERSION}  # the version to send

    @r.put("/settings/ai-consent")
    def put_consent(body: ConsentIn) -> JSONResponse:
        try:
            given = setup_state.give_consent(body.text_version)
        except OSError:
            return _not_saved()
        return JSONResponse({"at": given["at"]})

    @r.get("/settings/claude-code")
    async def find_claude_code() -> dict:
        path, version = await asyncio.to_thread(claude_code.find_claude)
        return {"found": path is not None, "version": version}

    @r.post("/settings/ai/check")
    async def check_ai(body: CheckIn) -> JSONResponse:
        """One tiny check through the link the engineer chose, after the consent. A Claude Code
        that answers is turned on, as the link the Lead QS uses."""
        setup_state.require_consent()
        found = list(engine.connectors())
        if body.via == "api_key":
            failed = await engine_connectors.check(f"anthropic/{chat.lead_model_id()}", among=found)
            if failed:
                return JSONResponse(copy.error(failed), 409)
            usage.track("ai_link", via="api_key")
            return JSONResponse({"ok": True})
        if body.via == "standard":  # its own model: the Lead's, if it is on this link
            link = next((c for c in found if c.id == body.connector), None)
            listed = [] if link is None else await link.cards()
            lead = roles.chosen(listed).get("lead")
            model = lead if lead is not None and lead.connector == body.connector else None
            if model is None and listed:
                model = listed[0].choice
            if model is None:
                return JSONResponse(copy.error(copy.NO_AI), 409)
            used: list = []
            failed = await engine_connectors.check(
                f"{model.connector}/{model.model}", among=found, on_usage=used.append
            )
            if failed:
                return JSONResponse(copy.error(failed), 409)
            card = next((c for c in listed if c.choice == model), None)
            if used and card is not None:
                _count_check(card, used[0])
            usage.track("ai_link", via="standard")
            return JSONResponse({"ok": True})
        saved = claude_link.saved()["path"]
        picked = None  # a Claude Code found outside PATH is saved by its path
        if saved is None and claude_code.on_path() is None:
            path, _ = await asyncio.to_thread(claude_code.find_claude)
            picked = None if path is None else str(path)
        if not any(c.id == claude_link.ID for c in found):
            found.append(claude_link.ClaudeCodeConnector(saved or picked))
        failed = await engine_connectors.check(claude_link.ID, among=found)
        if failed:
            return JSONResponse(copy.error(failed), 409)
        try:
            claude_link.save(path=saved or picked, on=True)
        except OSError:
            return _not_saved()
        usage.track("ai_link", via="claude_code")
        return JSONResponse({"ok": True})

    def _count_check(card, used) -> None:
        """The check's tokens in the cost book, as any call's (tender day: it was not counted)."""
        if engine.cost_book() is None:
            return
        engine.spending.after_response(
            brief_id=f"check-{uuid4().hex}",
            project_id=None,
            run_id=uuid4().hex,
            role="lead",
            card=card,
            input_tokens=used.input_tokens or 0,
            output_tokens=used.output_tokens or 0,
        )

    @r.get("/engineer/card")
    def get_card() -> dict:
        return engineer.card(engine.engineer_records())

    @r.put("/engineer/card")
    def put_card(body: engineer.Card) -> dict:
        return engineer.save_card(engine.engineer_records(), body)

    @r.post("/projects/{project_id}/understand", status_code=202)
    async def understand_project(project_id: str) -> JSONResponse:
        """One Brief to the Lead QS that reads the folder and fills the card (202)."""
        from qsone.engine.runner import BriefBusy, NoAI

        rec = engine.projects.get(project_id)
        try:
            brief_id = await understand.start(rec, engine)
        except BriefBusy as busy:
            return JSONResponse({"brief_id": busy.brief_id}, status_code=409)
        except NoAI as none:
            return JSONResponse(copy.error(none.text), status_code=409)
        return JSONResponse({"brief_id": brief_id}, status_code=202)

    @r.get("/projects/{project_id}/closing")
    async def get_closing(project_id: str) -> dict:
        rec = engine.projects.get(project_id)
        got = await asyncio.to_thread(closing.checklist, rec, engine.engineer_records())
        # what waits for the engineer in the chat: the panel never says nothing is open then
        got["waiting"] = await asyncio.to_thread(closing.waiting, rec, engine.waiting(project_id))
        return got

    @r.post("/projects/{project_id}/lessons/propose", status_code=202)
    async def propose_lessons(project_id: str) -> JSONResponse:
        """The lessons Brief (202); a Confidential Project has none to propose (409)."""
        from qsone.engine.runner import BriefBusy, NoAI

        rec = engine.projects.get(project_id)
        try:
            brief_id = await closing.propose_lessons(rec, engine)
        except BriefBusy as busy:
            return JSONResponse({"brief_id": busy.brief_id}, status_code=409)
        except NoAI as none:
            return JSONResponse(copy.error(none.text), status_code=409)
        if brief_id is None:
            return JSONResponse({"error": copy.LESSON_STAYS_CONFIDENTIAL}, status_code=409)
        return JSONResponse({"brief_id": brief_id}, status_code=202)

    @r.post("/projects/{project_id}/lessons/{lesson_id}")
    async def carry_lesson(project_id: str, lesson_id: str, body: CarryIn) -> dict:
        rec, mine = engine.projects.get(project_id), engine.engineer_records()
        carried = await asyncio.to_thread(closing.carry, rec, mine, lesson_id, carry=body.carry)
        return {"carried": carried}

    @r.post("/projects/{project_id}/archive")
    async def archive(project_id: str) -> JSONResponse:
        """{"archived_at", "backed_up", "note"}; refused (409) while a Brief runs in it."""
        rec = engine.projects.get(project_id)
        busy = engine.active(project_id)
        if busy is not None:
            body = {"brief_id": busy, "error": copy.ARCHIVE_WAITS_FOR_BRIEF}
            return JSONResponse(body, status_code=409)
        done = await asyncio.to_thread(closing.archive, rec, engine.projects.backups)
        return JSONResponse(done)

    @r.post("/projects/{project_id}/unarchive")
    async def unarchive(project_id: str) -> dict:
        rec = engine.projects.get(project_id)
        await asyncio.to_thread(closing.unarchive, rec)
        return {"archived_at": rec.archived_at}

    @r.get("/projects/{project_id}/facts")
    async def get_facts(project_id: str) -> dict:
        return await asyncio.to_thread(understand.facts, engine.projects.get(project_id))

    @r.put("/projects/{project_id}/facts")
    async def put_facts(project_id: str, body: FactsIn) -> dict:
        """The engineer's corrections, then the approval as given."""
        rec = engine.projects.get(project_id)
        values = {name: fact.value for name, fact in body.facts.items()}
        return await asyncio.to_thread(understand.correct, rec, values, approve=body.approve)

    @r.post("/app/open")
    async def open_link(body: OpenIn) -> dict:
        url = LINKS[body.link].format(lang=body.lang or setup_state.language())
        opened = await asyncio.to_thread(webbrowser.open, url)
        return {"opened": bool(opened)}

    return r
