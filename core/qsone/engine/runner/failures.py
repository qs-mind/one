import asyncio
import re
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import uuid4

import anthropic
import openai
from pydantic_ai.exceptions import (
    ModelAPIError,
    ModelAuthenticationError,
    ModelConnectionError,
    ModelHTTPError,
    ModelRateLimitError,
    ModelRequestTimeout,
    ModelServerError,
    ModelUnavailableError,
    UnexpectedModelBehavior,
)

from qsone import copy
from qsone.engine import connectors as connectors_mod
from qsone.engine import roles
from qsone.engine.costs import CallRefused, CapReached
from qsone.engine.runner.errors import _Busy, _Fail
from qsone.engine.runner.histories import _refused
from qsone.engine.runner.shared import log
from qsone.engine.types import AgentSpec, Card, ModelChoice, Progress, Text

# ONE's own refusals, given up on by the model: never a provider's error (6 Nov 2026)
_TOOL_GAVE_UP = re.compile(r"^Tool '([A-Za-z0-9_]+)' exceeded max retries count of (\d+)")
_REPLY_GAVE_UP = re.compile(r"^Exceeded maximum (?:output )?retries")
BUSY_WAIT = 5  # seconds before the one more try at a busy provider
OFFLINE_WAITS = (5, 15, 30, 60)  # then every 60 s while the app runs


def _error_kind(error: BaseException) -> str | None:
    """auth, offline, busy or other for a provider's error; None when it is not one."""
    if isinstance(error, _Busy):
        return "busy"
    status = getattr(error, "status_code", None)
    if isinstance(
        error,
        ModelAuthenticationError | anthropic.AuthenticationError | openai.AuthenticationError,
    ) or (isinstance(error, ModelHTTPError) and status in (401, 403)):
        return "auth"
    if isinstance(
        error,
        ModelConnectionError
        | ModelRequestTimeout
        | ConnectionError
        | anthropic.APIConnectionError
        | openai.APIConnectionError,
    ):
        return "offline"
    if isinstance(
        error,
        ModelRateLimitError
        | ModelUnavailableError
        | ModelServerError
        | anthropic.RateLimitError
        | anthropic.InternalServerError
        | openai.RateLimitError
        | openai.InternalServerError,
    ) or (isinstance(status, int) and (status == 429 or status >= 500)):
        return "busy"
    # an empty or malformed reply, or retries used up, is the model's doing, not ONE's
    if isinstance(
        error, ModelAPIError | UnexpectedModelBehavior | anthropic.APIError | openai.APIError
    ):
        return "other"
    return None


class _BriefFailures:
    """The failures with a plan: a busy or offline provider, a refused key, a model giving up."""

    # Failures --------------------------------------------------------------------------------

    async def _attempts(
        self,
        run_id: str,
        spec: AgentSpec,
        once: Callable[[ModelChoice], Awaitable[Any]],
        *,
        avoid: frozenset[ModelChoice] = frozenset(),
    ):
        """Runs `once` on the run's model, from its Checkpoint each time, through the failures
        that have a plan: busy (once more, then another model), offline (wait), refused key."""
        retried = False
        unavailable_retried = False
        waits = iter(OFFLINE_WAITS)
        while True:
            choice = self.store.run(run_id)["choice"]
            if connectors_mod.refused(choice):
                current = self.setup.roles if self.setup is not None else {}
                refreshed = roles.available(self.sheet, current)
                new = refreshed.get(spec.tier)
                if new is None or new in avoid or not self._model(new):
                    raise _Fail(copy.NO_AI)
                choice = new
                self.store.set_run(run_id, choice=choice)
                self._agent(run_id, model=choice.model)
            try:
                return await once(choice)
            except (CapReached, CallRefused, _Fail, asyncio.CancelledError):
                raise
            except Exception as error:  # noqa: BLE001 - sorted below; anything else is re-raised
                gave_up = self._gave_up(run_id, error)
                if gave_up is not None:
                    raise _Fail(gave_up) from None
                kind = _error_kind(error)
                if kind is None:
                    raise
                provider = self._provider(choice)
                log.warning("run %s on %s: %s %s", run_id, choice.connector, kind, error)
                if connectors_mod.model_unavailable(error):
                    connectors_mod.note_refused(choice)
                    self.emit(
                        Progress(
                            self.brief_id,
                            run_id,
                            spec.name,
                            copy.fill(copy.MODEL_STOPPED, model=choice.model, provider=provider),
                        )
                    )
                    current = self.setup.roles if self.setup is not None else {}
                    refreshed = roles.available(self.sheet, current)
                    if self.setup is not None:
                        self.setup.roles.clear()
                        self.setup.roles.update(refreshed)
                    new = refreshed.get(spec.tier)
                    if (
                        not unavailable_retried
                        and new is not None
                        and new not in avoid
                        and self._model(new)
                    ):
                        unavailable_retried = True
                        self.store.set_run(run_id, choice=new)
                        self._agent(run_id, model=new.model)
                        continue
                    raise _Fail(
                        connectors_mod.provider_reason(error, provider, choice.model) or copy.NO_AI
                    ) from None
                if kind == "auth":
                    raise _Fail(connectors_mod.key_refused(provider)) from None
                if kind == "other":  # the provider's reason when ONE knows it (audit B7)
                    said = connectors_mod.provider_reason(error, provider, choice.model)
                    raise _Fail(said or copy.fill(copy.AI_FAILED, provider=provider)) from None
                if kind == "offline":
                    before = self.step
                    self.set_state("waiting_connection", copy.WAITING_INTERNET)
                    await self.engine.sleep(next(waits, OFFLINE_WAITS[-1]))
                    self.set_state("running", before)
                    continue
                if not retried:
                    retried = True
                    await self.engine.sleep(BUSY_WAIT)
                    continue
                retried = False
                await self._move(run_id, spec, choice, avoid, provider)

    def _gave_up(self, run_id: str, error: BaseException) -> Text | None:
        """The plain words for a run that stopped on ONE's own refusals (a tool call refused
        until the model gave up, or an answer sent back too often); None for any other error.
        The provider is never named for these: they are ONE's."""
        if not isinstance(error, UnexpectedModelBehavior):
            return None
        tool = _TOOL_GAVE_UP.match(error.message)
        if tool is not None:
            name, n = tool[1], tool[2]
            said = _refused(self.store.run(run_id)["history"], name) or ""
            why = self._refusal(name, said)
            return copy.fill(copy.TOOL_GAVE_UP, n=str(int(n) + 1), why=why)
        if _REPLY_GAVE_UP.match(error.message):
            return copy.REPLY_GAVE_UP
        return None

    async def _move(
        self,
        run_id: str,
        spec: AgentSpec,
        failed: ModelChoice,
        avoid: frozenset[ModelChoice],
        provider: str,
    ) -> None:
        """The run moves to the closest model of the same price or cheaper; a costlier one only
        after the engineer's yes. Raises `_Fail` when there is none, or on "no"."""
        skip = set(avoid) | {failed}
        old = self.card(failed).name
        cheaper = [c for c in roles.same_or_cheaper(self.sheet, failed, skip) if self._model(c)]
        if cheaper:
            new = cheaper[0]
            self.store.set_run(run_id, choice=new)
            self._agent(run_id, model=new.model)
            moved = copy.fill(copy.FALLBACK_MOVED, old=old, role=spec.name, new=self.card(new).name)
            self.emit(Progress(self.brief_id, run_id, spec.name, moved))
            return
        pricier = [c for c in roles.costlier(self.sheet, failed, skip) if self._model(c)]
        if pricier:
            new = pricier[0]
            card = self.card(new)
            detail = copy.fill(
                copy.FALLBACK_COSTLIER,
                old=old,
                new=card.name,
                price_in=format(card.price_in, "f") if card.price_in is not None else "?",
                price_out=format(card.price_out, "f") if card.price_out is not None else "?",
            )
            answer = await self.ask(Card(uuid4().hex, "fallback", spec.name, detail, ("yes", "no")))
            if answer == "yes":
                self.store.set_run(run_id, choice=new)
                self._agent(run_id, model=new.model)
                return
        raise _Fail(copy.fill(copy.AI_FAILED, provider=provider))
