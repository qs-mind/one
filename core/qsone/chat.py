"""POST /chat: the Lead QS, served the official PydanticAI way (AI SDK UI message stream)."""

import json
import logging
from collections.abc import AsyncIterator, Callable

import pydantic_ai
from pydantic_ai import Agent
from pydantic_ai.exceptions import (
    ModelAuthenticationError,
    ModelConnectionError,
    ModelRateLimitError,
    ModelRequestTimeout,
    ModelUnavailableError,
)
from pydantic_ai.models import Model
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.ui.vercel_ai import VercelAIAdapter, VercelAIEventStream
from pydantic_ai.ui.vercel_ai.response_types import BaseChunk
from starlette.requests import Request
from starlette.responses import Response

from qsone import copy, keys, settings

# The default; the engineer picks another from the header (PUT /settings/model).
LEAD_MODEL = "claude-opus-5-5"

LEAD_INSTRUCTIONS = (
    "You are the Lead QS in QS Mind One: a senior quantity surveyor for construction cost work "
    "in Egypt and the Gulf (BOQs, estimates, tenders, procurement). Reply in the engineer's "
    "language; in Arabic, use plain Egyptian-friendly Arabic. Be short and plain. You cannot yet "
    "open files, look up prices, calculate or use tools: when asked, say so plainly. Never "
    "invent a number; every number needs a source."
)

ModelFactory = Callable[[], Model | None]

pydantic_ai.BANNER_ENABLED = False  # keep core.log to our own lines

lead_agent = Agent(name="lead-qs", instructions=LEAD_INSTRUCTIONS)

log = logging.getLogger("qsone.chat")


def lead_model_id() -> str:
    """The model the engineer chose, or LEAD_MODEL."""
    chosen = settings.load().get("lead_model")
    return chosen if isinstance(chosen, str) and chosen else LEAD_MODEL


def default_model() -> Model | None:
    """The Lead QS model with the engineer's own key, or None when no key is saved."""
    key = keys.get_key("anthropic")
    if key is None:
        return None
    return AnthropicModel(lead_model_id(), provider=AnthropicProvider(api_key=key))


async def _say_no_key(messages, info: AgentInfo):
    yield f"{copy.NO_KEY['ar']}\n\n{copy.NO_KEY['en']}"


def plain_error(error: Exception) -> dict[str, str]:
    """The {en, ar} text the engineer sees for a model error."""
    if isinstance(error, ModelAuthenticationError):
        return copy.KEY_REFUSED
    if isinstance(error, ModelConnectionError | ModelRequestTimeout):
        return copy.NO_CONNECTION
    if isinstance(error, ModelRateLimitError | ModelUnavailableError):
        return copy.CLAUDE_BUSY
    return copy.MODEL_FAILED


class _PlainErrorStream(VercelAIEventStream):
    async def on_error(self, error: Exception) -> AsyncIterator[BaseChunk]:
        # The provider's own words go to core.log; the stream carries a plain {en, ar} pair as JSON.
        log.warning("The model failed: %s", error, exc_info=error)
        plain = Exception(json.dumps(plain_error(error), ensure_ascii=False))
        async for chunk in super().on_error(plain):
            yield chunk


class _Adapter(VercelAIAdapter):
    def build_event_stream(self) -> _PlainErrorStream:
        return _PlainErrorStream(
            self.run_input,
            accept=self.accept,
            sdk_version=self.sdk_version,
            server_message_id=self.server_message_id,
            manage_system_prompt=self.manage_system_prompt,
        )


async def respond(request: Request, model_factory: ModelFactory) -> Response:
    # Without a key, answer in plain words through the same stream, so the screen shows a reply.
    model = model_factory() or FunctionModel(stream_function=_say_no_key)
    return await _Adapter.dispatch_request(request, agent=lead_agent, model=model, sdk_version=6)
