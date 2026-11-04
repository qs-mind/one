"""AI Connectors: where a model comes from, behind one interface.

- A *model* connector gives a PydanticAI `Model`, and One runs the agent loop: the Native Link
  (Anthropic, `native_anthropic.py`) and the Standard Link (OpenAI-compatible, `standard.py`).
- An *agent* connector runs its own loop over One's tools through MCP: the Subscription Link
  (the engineer's own Claude Code, `claude_code.py`), listed while settings.json
  "ai.claude_code.on" is true.

Keys live only in the key store, under the connector's id ("anthropic", "standard:<id>").
"""

import logging
from collections.abc import Callable, Sequence
from typing import Any, Literal, Protocol

import anthropic
import httpx2
import openai
from pydantic_ai.direct import model_request
from pydantic_ai.exceptions import (
    ModelAPIError,
    ModelAuthenticationError,
    ModelConnectionError,
    ModelRateLimitError,
    ModelRequestTimeout,
    ModelServerError,
    ModelUnavailableError,
)
from pydantic_ai.messages import ModelRequest
from pydantic_ai.models import Model
from pydantic_ai.settings import ModelSettings

from qsone import copy
from qsone.engine.types import Event, ModelCard, Text

log = logging.getLogger("qsone.engine.connectors")

# What a provider raises when it does not answer as asked; anything else is a bug in One.
PROVIDER_ERRORS = (ModelAPIError, anthropic.APIError, openai.APIError)


class NoKey(LookupError):
    """The connector needs a key, and none is in the key store."""


class ModelConnector(Protocol):
    id: str
    kind: Literal["model"]
    name: str  # shown to the engineer, and in the plain error texts
    provider: str  # decides a Same-provider check
    on_device: bool

    async def cards(self) -> list[ModelCard]:
        """The provider's own list, live; unpriced (`cards.sheet` prices them)."""
        ...

    def model(self, model_id: str) -> Model:
        """Raises `NoKey` when the connector needs a key and has none."""
        ...


class AgentConnector(Protocol):
    """The Subscription Link (Task 5)."""

    id: str
    kind: Literal["agent"]
    name: str
    provider: str

    async def cards(self) -> list[ModelCard]: ...

    async def run(self, job: Any, sink: Callable[[Event], None]) -> Any:
        """`job` is Task 5's `AgentJob`; the answer its `AgentOutcome`."""
        ...

    async def stop(self, run_id: str) -> None: ...

    async def check(self) -> Text | None:
        """Its own tiny check (Claude Code's `auth status`); None means it is ready."""
        ...


Connector = ModelConnector | AgentConnector


def connectors(
    *, http_client: httpx2.AsyncClient | None = None, claude_command: Sequence[str] = ()
) -> list[Connector]:
    """Every connector the engineer has set up, from settings.json "ai" and the key store.

    The Native Link is always listed, so the screen can offer its key; without one it lists no
    models. `http_client` reaches the providers (tests inject a fake; it is never closed here).
    `claude_command` replaces the Claude Code executable (tests: the fake `claude`).
    """
    from qsone.engine.connectors import claude_code, standard
    from qsone.engine.connectors.native_anthropic import NativeLink

    found: list[Connector] = [NativeLink(http_client=http_client)]
    found += standard.links(http_client=http_client)
    saved = claude_code.saved()
    if saved["on"]:
        found.append(
            claude_code.ClaudeCodeConnector(
                saved["path"], command_prefix=claude_command, keep_copy=saved["keep_copy"]
            )
        )
    return found


async def check(via: str, *, among: Sequence[Connector] | None = None) -> Text | None:
    """One tiny call through `via` ("<connector>/<model>"; an agent connector's id alone).

    A model connector gets one request for at most 1 output token. None means it answered;
    otherwise the plain {en, ar} reason. `among` defaults to `connectors()`."""
    connector_id, _, model_id = via.partition("/")
    found = {c.id: c for c in (connectors() if among is None else among)}
    connector = found.get(connector_id)
    if connector is None:
        return copy.NO_AI
    if connector.kind == "agent":
        return await connector.check()
    try:
        await model_request(
            connector.model(model_id),
            [ModelRequest.user_text_prompt("Reply OK")],
            model_settings=ModelSettings(max_tokens=1),
        )
    except NoKey:
        return copy.NO_AI
    except PROVIDER_ERRORS as error:
        log.warning("The check through %s failed: %s", connector.id, error)
        return plain_error(error, connector.name)
    return None


def plain_error(error: Exception, provider: str) -> Text:
    """The {en, ar} words for a provider's error; its own words go to core.log only."""
    if isinstance(
        error,
        ModelAuthenticationError
        | anthropic.AuthenticationError
        | anthropic.PermissionDeniedError
        | openai.AuthenticationError
        | openai.PermissionDeniedError,
    ):
        text = copy.AI_KEY_REFUSED
    elif isinstance(
        error,
        ModelConnectionError
        | ModelRequestTimeout
        | anthropic.APIConnectionError  # also a timeout
        | openai.APIConnectionError,
    ):
        text = copy.AI_NO_CONNECTION
    elif isinstance(
        error,
        ModelRateLimitError
        | ModelUnavailableError
        | ModelServerError
        | anthropic.RateLimitError
        | openai.RateLimitError,
    ):
        text = copy.AI_BUSY
    else:  # a plain HTTP error: ModelHTTPError, or the SDKs' APIStatusError
        status = getattr(error, "status_code", None)
        if status in (401, 403):
            text = copy.AI_KEY_REFUSED
        elif isinstance(status, int) and (status == 429 or status >= 500):  # also overloaded
            text = copy.AI_BUSY
        else:
            text = copy.AI_FAILED
    return copy.fill(text, provider=provider)
