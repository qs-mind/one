"""POST /chat: the engineer's message becomes a Brief of the Brief Runner, streamed as the AI SDK
UI message stream. The Brief runs on without the request: a dropped stream reattaches with
GET /chat/{id}/stream."""

import json
import logging
from collections.abc import AsyncIterator

import pydantic_ai
from pydantic_ai.models import Model
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.providers.anthropic import AnthropicProvider
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse

from qsone import copy, keys, settings
from qsone.engine import roles, selection
from qsone.engine.runner import BriefBusy, Engine, NoAI, reply_id
from qsone.engine.stream import HEADERS, error_chunk, ui_stream
from qsone.engine.types import EFFORTS, Effort, ModelChoice

# The default; the engineer picks another from the header (PUT /settings/model).
LEAD_MODEL = roles.LEAD_MODEL

pydantic_ai.BANNER_ENABLED = False  # keep core.log to our own lines

log = logging.getLogger("qsone.chat")


def lead_model_id() -> str:
    """The Lead QS's model on the Native Link, as the engineer chose it, or LEAD_MODEL."""
    lead = roles.saved().get("lead")
    return lead.model if lead is not None and lead.connector == "anthropic" else LEAD_MODEL


def default_model() -> Model | None:
    """The Lead QS model with the engineer's own key, or None when no key is saved."""
    key = keys.get_key("anthropic")
    if key is None:
        return None
    return AnthropicModel(lead_model_id(), provider=AnthropicProvider(api_key=key))


def stream(events: AsyncIterator, message_id: str) -> StreamingResponse:
    return StreamingResponse(
        ui_stream(events, message_id=message_id), media_type="text/event-stream", headers=HEADERS
    )


async def _refused(text: dict[str, str]) -> AsyncIterator[str]:
    """No Brief: only the stream's `error` chunk, so the chat shows `text` as its error line, with
    the action that fixes it (Open AI settings, for a refused key)."""
    yield error_chunk(text)
    yield "data: [DONE]\n\n"


def _last_text(body: dict) -> str:
    messages = body.get("messages") or []
    for message in reversed(messages if isinstance(messages, list) else []):
        if isinstance(message, dict) and message.get("role") == "user":
            parts = message.get("parts") or []
            return "".join(
                p.get("text", "") for p in parts if isinstance(p, dict) and p.get("type") == "text"
            ).strip()
    return ""


def _picked(body: dict) -> tuple[ModelChoice | None, Effort | None]:
    """The Lead QS's model `{connector, model}` and `effort` picked in the message box; each is
    None when left out. Raises `ValueError` for one that is not of that shape."""
    model, effort = body.get("model"), body.get("effort")
    lead = None
    if model is not None:
        if not (
            isinstance(model, dict)
            and isinstance(model.get("connector"), str)
            and isinstance(model.get("model"), str)
        ):
            raise ValueError("model")
        lead = ModelChoice(model["connector"], model["model"])
    if effort is not None and effort not in EFFORTS:
        raise ValueError("effort")
    return lead, effort


def remember(lead: ModelChoice | None, effort: Effort | None) -> None:
    """The message box's last pick, for the next time: the model as the Lead QS's role (the one
    AI settings show), the effort in settings.json "ai.effort". Not saved: the same next time."""
    try:
        if lead is not None:
            roles.choose("lead", lead)
        if effort is not None:
            settings.save_ai("effort", effort)
    except OSError:
        log.warning("The message box's model and effort were not saved")


async def respond(request: Request, engine: Engine) -> Response:
    """The AI SDK body `{id: chat id, messages, selection?, model?, effort?}`: only the last user
    message is used. The chat id is a project id or "general"; `selection` is what the engineer
    selected in the open document (up to 20 items); `model` `{connector, model}` and `effort`
    ("low", "medium", "high") are the Lead QS's for this Brief, picked in the message box, and
    remembered for the next. 409 with `{"brief_id"}` while the chat has a Brief."""
    try:
        body = json.loads(await request.body())
    except ValueError:
        body = None
    text = _last_text(body) if isinstance(body, dict) else ""
    chat_id = body.get("id") if isinstance(body, dict) else None
    if not text or not isinstance(chat_id, str):
        return JSONResponse({"error": copy.CHAT_EMPTY}, status_code=422)
    try:
        chosen = selection.read(body.get("selection"))
    except ValueError:
        answer = {"error": copy.CHAT_BAD_SELECTION, "field": "selection"}
        return JSONResponse(answer, status_code=422)
    try:
        lead, effort = _picked(body)
    except ValueError as bad:
        return JSONResponse({"error": copy.CHAT_MODEL_GONE, "field": str(bad)}, status_code=422)
    try:
        brief_id = await engine.start_brief(
            chat_id, text, selection=chosen, lead=lead, effort=effort
        )
    except BriefBusy as busy:
        return JSONResponse({"brief_id": busy.brief_id}, status_code=409)
    except NoAI as none:
        # No Brief: the plain words come through the same stream, so the screen shows them.
        return StreamingResponse(
            _refused(none.text), media_type="text/event-stream", headers=HEADERS
        )
    remember(lead, effort)
    return stream(engine.events(brief_id), reply_id(brief_id))
