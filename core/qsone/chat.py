"""POST /chat: the Lead QS, served the official PydanticAI way (AI SDK UI message stream)."""

from collections.abc import Callable

import pydantic_ai
from pydantic_ai import Agent
from pydantic_ai.models import Model
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.ui.vercel_ai import VercelAIAdapter
from starlette.requests import Request
from starlette.responses import Response

from qsone import copy, keys

# Anthropic's most capable widely released model (claude-api model list, 2026-10-06).
LEAD_MODEL = "claude-fable-5-1"

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


def default_model() -> Model | None:
    """The Lead QS model with the engineer's own key, or None when no key is saved."""
    key = keys.get_key("anthropic")
    if key is None:
        return None
    return AnthropicModel(LEAD_MODEL, provider=AnthropicProvider(api_key=key))


async def _say_no_key(messages, info: AgentInfo):
    yield f"{copy.NO_KEY['ar']}\n\n{copy.NO_KEY['en']}"


async def respond(request: Request, model_factory: ModelFactory) -> Response:
    # Without a key, answer in plain words through the same stream, so the screen shows a reply.
    model = model_factory() or FunctionModel(stream_function=_say_no_key)
    return await VercelAIAdapter.dispatch_request(
        request, agent=lead_agent, model=model, sdk_version=6
    )
