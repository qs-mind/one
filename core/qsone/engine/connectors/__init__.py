"""AI Connectors: where a model comes from, behind one interface.

- A *model* connector gives a PydanticAI `Model`, and One runs the agent loop: the Native Link
  (Anthropic, `native_anthropic.py`) and the Standard Link (OpenAI-compatible, `standard.py`).
- An *agent* connector runs its own loop over One's tools through MCP: the Subscription Link
  (the engineer's own Claude Code, `claude_code.py`), listed while settings.json
  "ai.claude_code.on" is true.

Keys live only in the key store, under the connector's id ("anthropic", "standard:<id>").
"""

import asyncio
import logging
import re
from collections.abc import Callable, Mapping, Sequence
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

from qsone import copy, settings
from qsone.engine.types import EFFORTS, Effort, Event, ModelCard, ModelChoice, Text

log = logging.getLogger("qsone.engine.connectors")

# What a provider raises when it does not answer as asked; anything else is a bug in One.
PROVIDER_ERRORS = (ModelAPIError, anthropic.APIError, openai.APIError)
CHECK_SECONDS = (
    10  # one quick call: a provider that has not answered by then is said, not waited on
)


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


def efforts_of(profile: Mapping | None) -> tuple[tuple[Effort, ...], Effort | None]:
    """The effort levels a model accepts, from PydanticAI's profile of it, and the level its
    provider uses when none is sent, when that is known.

    - Anthropic's `effort` (Opus 4.5 and later, Sonnet 4.6 and later, Haiku 5.5): its default is
      "high" (Anthropic's documentation).
    - An OpenAI-style `reasoning_effort` model: its default differs by model, so it is not said.
    - Anything else takes no effort: the message box shows no effort to pick."""
    profile = profile or {}
    if profile.get("anthropic_supports_effort"):
        return EFFORTS, "high"
    if profile.get("openai_supports_reasoning"):
        return EFFORTS, None
    return (), None


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


async def check(
    via: str,
    *,
    among: Sequence[Connector] | None = None,
    on_usage: Callable[[Any], None] | None = None,
) -> Text | None:
    """One tiny call through `via` ("<connector>/<model>"; an agent connector's id alone).

    A model connector gets one request for at most 1 output token; `on_usage` is given its
    usage, so the call is counted in costs like any other. None means it answered; otherwise
    the plain {en, ar} reason. A model the provider does not serve (404) is noted
    (`note_refused`). `among` defaults to `connectors()`."""
    connector_id, _, model_id = via.partition("/")
    found = {c.id: c for c in (connectors() if among is None else among)}
    connector = found.get(connector_id)
    if connector is None:
        return copy.NO_AI
    if connector.kind == "agent":
        return await connector.check()
    try:
        answer = await asyncio.wait_for(
            model_request(
                connector.model(model_id),
                [ModelRequest.user_text_prompt("Reply OK")],
                model_settings=ModelSettings(max_tokens=1, timeout=CHECK_SECONDS),
            ),
            CHECK_SECONDS,
        )
    except NoKey:
        return copy.NO_AI
    except TimeoutError:
        log.warning("The check through %s took over %s s", connector.id, CHECK_SECONDS)
        return copy.fill(copy.AI_CHECK_SLOW, provider=connector.name)
    except PROVIDER_ERRORS as error:
        log.warning("The check through %s failed: %s", connector.id, error)
        if getattr(error, "status_code", None) == 404:
            note_refused(ModelChoice(connector_id, model_id))
        said = plain_error(error, connector.name)
        # a check has no work to save: its own words, not AI_FAILED's
        failed = copy.fill(copy.AI_FAILED, provider=connector.name)
        return copy.fill(copy.AI_CHECK_FAILED, provider=connector.name) if said == failed else said
    if on_usage is not None:
        on_usage(answer.usage)
    return None


def key_refused(provider: str) -> Text:
    """A refused key, in plain words: Anthropic's own for the Claude key (the Native Link)."""
    from qsone.engine.connectors.native_anthropic import NativeLink

    if provider == NativeLink.name:
        return copy.KEY_REFUSED
    return copy.fill(copy.AI_KEY_REFUSED, provider=provider)


def _model_key(choice) -> str:
    return f"{choice.connector}/{choice.model}"


def note_refused(choice) -> None:
    """A model the provider said it does not serve: no longer listed (audit C4)."""
    found = settings.ai().get("refused_models")
    kept = [k for k in found if isinstance(k, str)] if isinstance(found, list) else []
    try:
        settings.save_ai("refused_models", sorted({*kept, _model_key(choice)}))
    except OSError:
        log.warning("the refused model was not saved")


def refused(choice) -> bool:
    found = settings.ai().get("refused_models")
    return isinstance(found, list) and _model_key(choice) in found


_SUGGESTED = re.compile(r"\buse (?:models/)?([A-Za-z0-9][\w.-]*[\w])", re.IGNORECASE)


def _said(error: BaseException) -> str:
    """The provider's own message in an HTTP error's body (Google sends a list of one)."""
    body = getattr(error, "body", None)
    if isinstance(body, list) and body:
        body = body[0]
    if isinstance(body, dict):
        inner = body.get("error")
        found = inner.get("message") if isinstance(inner, dict) else body.get("message")
        if isinstance(found, str):
            return found
    found = getattr(error, "message", None)
    return found if isinstance(found, str) else ""


def provider_reason(error: BaseException, provider: str, model: str) -> Text | None:
    """The provider's reason in plain words, when ONE knows it (audit B7): a model it retired or
    does not serve (with the one it suggests), or Google's 400 for a wrong key. None otherwise:
    the provider's own words go to core.log only."""
    status = getattr(error, "status_code", None)
    said = _said(error)
    if status == 400 and "api key not valid" in said.lower():
        return key_refused(provider)
    if status != 404:
        return None
    name = model.removeprefix("models/")
    suggested = _SUGGESTED.search(said)
    if suggested and suggested.group(1) != name:
        return copy.fill(copy.MODEL_GONE_TRY, provider=provider, model=name, other=suggested[1])
    return copy.fill(copy.MODEL_GONE, provider=provider, model=name)


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
        return key_refused(provider)
    if isinstance(
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
        said = provider_reason(error, provider, str(getattr(error, "model_name", "") or ""))
        if said is not None:
            return said
        status = getattr(error, "status_code", None)
        if status in (401, 403):
            return key_refused(provider)
        if isinstance(status, int) and (status == 429 or status >= 500):  # also overloaded
            text = copy.AI_BUSY
        else:
            text = copy.AI_FAILED
    return copy.fill(text, provider=provider)
