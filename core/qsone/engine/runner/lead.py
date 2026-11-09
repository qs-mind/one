import asyncio
import json
from typing import Any

from pydantic_ai import Agent, DeferredToolRequests, DeferredToolResults, ModelRetry, ToolFailed
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.messages import (
    PartDeltaEvent,
    PartStartEvent,
    TextPart,
    TextPartDelta,
    ToolCallPart,
)
from pydantic_ai.settings import ModelSettings
from pydantic_ai.usage import UsageLimits

from qsone import copy
from qsone.engine import agents, oneshot, selection, tool_groups, tools, truth
from qsone.engine.data_text import as_data
from qsone.engine.runner.histories import (
    _load,
    cut_back,
    final_text,
    heard,
    lead_text,
    pending_deferred,
    settled,
)
from qsone.engine.runner.shared import TOOL_RETRIES, log
from qsone.engine.tools import DENIED, Denied
from qsone.engine.types import Data, ModelChoice, TextDelta, reply_line

STEP_LIMIT = 50  # model requests in one pass of the Lead; then it reports what it has
REPORT_LIMIT = 3  # model requests of that report, or of a report at a Spending Cap
_DEFERRED = object()  # the Lead's pass ended with deferred calls to run


def _result_value(stored: str):
    found = json.loads(stored)
    if "ok" in found:
        return found["ok"]
    if "retry" in found:
        return ModelRetry(found["retry"])
    return ToolFailed(found["failed"])


class _BriefLead:
    """The Lead's run: its instructions, its passes, its deferred calls and the step limit."""

    # The Lead --------------------------------------------------------------------------------

    def _earlier(self) -> list:
        found = []
        for history in self.store.lead_histories(self.chat_id, self.brief_id):
            found += heard(settled(_load(history)))
        return found

    def _instructions(self, choice: ModelChoice) -> str:
        # a small model repeated "you run on …" in every reply (audit R15): only when asked
        said = (
            f"The AI model you run on is {choice.model}. Say it only if the engineer asks which "
            "model answers; never mention it otherwise."
        )
        found = (
            said,
            truth.today_line(self.engine.clock()),  # dates come from the core, in Cairo time
            reply_line(self.text),
            self._search_line(),
            self.instruction,
            selection.line(self.selection),
        )
        return "\n\n".join(part for part in found if part)

    def _search_line(self) -> str | None:
        """With no web search at all (a Standard Link, no search key), the Lead is told so
        (audit B8): it said nothing and gave remembered prices as today's."""
        from qsone.tools import web as web_tools

        services = self.engine.services
        if services is not None and self.lead_run_id is not None:
            services = oneshot.for_run(services, self.models(self.lead_run_id))
        if web_tools.searchable(services):
            return None
        if self.place.rec is not None:  # a project's Lead has no web_search: ONE adds the way
            return (
                "No web search is set up in ONE. When the engineer asks for something from the "
                "web or today's price, say in one line that ONE could not search the web (ONE "
                "shows them how to set it up), and give no remembered price as today's."
            )
        return (
            "No web search is set up in ONE. When the engineer asks for something from the web "
            "or today's price, call web_search once (ONE shows them how to set search up), say "
            "in one line that you could not search, and give no remembered price as today's."
        )

    async def _lead(self, *, report: bool = False) -> Any:
        assert self.lead_run_id is not None
        spec = self.lead_ctx.agent
        while True:
            if not report:
                own = cut_back(_load(self.store.run(self.lead_run_id)["history"]))
                pending = pending_deferred(own)
                if pending:
                    await self._run_deferred(self.lead_run_id, pending)
            try:
                out = await self._attempts(
                    self.lead_run_id, spec, lambda c: self._lead_pass(c, report=report)
                )
            except UsageLimitExceeded:
                if report:  # a report that keeps calling tools ends with what was said
                    return None
                return await self._step_limit()
            if out is not _DEFERRED:
                return out
            if report:
                return None

    async def _step_limit(self) -> Any:
        """The Lead reached ONE's step limit for one request: the engineer hears why, and the
        Lead says, without another tool, what it got so far (the top 5 of SGH took 50 steps of
        one item each and ended "problem inside ONE", 6 Nov 2026)."""
        log.info("brief %s at the step limit", self.brief_id)
        notice = (
            copy.READ_REPEAT_LIMIT
            if self.read_repeats >= 3
            else copy.fill(copy.STEP_LIMIT_REACHED, n=str(STEP_LIMIT))
        )
        self.emit(Data(self.brief_id, "notice", f"{self.brief_id}-step-limit", {"text": notice}))
        self.worklog.truth = (self.worklog.truth or {}) | {"step_limit": notice}
        self.step_limited = True
        try:
            out = await self._attempts(
                self.lead_run_id,
                self.lead_ctx.agent,
                lambda c: self._lead_pass(
                    c,
                    report=True,
                    prompt=copy.READ_REPEAT_NOW if self.read_repeats >= 3 else copy.STEP_LIMIT_NOW,
                ),
            )
        except UsageLimitExceeded:
            out = None
        return out if isinstance(out, str) and out.strip() else ""

    async def _run_deferred(self, run_id: str, calls: list[ToolCallPart]) -> None:
        """Runs the deferred calls that have no stored result, at the same time, storing each
        result as it finishes. The first failure that ends the Brief stops the others."""
        done = self.store.results(run_id)
        todo = [c for c in calls if c.tool_call_id not in done]
        if not todo:
            return
        self._agent(run_id, state="waiting")

        async def one(c: ToolCallPart) -> None:
            try:
                found = {"ok": await tools.call(c.tool_name, c.args_as_dict(), self.lead_ctx)}
            except ModelRetry as e:
                found = {"retry": e.message}
            except Denied:
                found = {"failed": DENIED.format(tool=c.tool_name)}
            if self.cancel_mode != "crash":
                self.store.save_result(
                    run_id, c.tool_call_id, json.dumps(found, ensure_ascii=False)
                )

        tasks = [asyncio.create_task(one(c)) for c in todo]
        try:
            for finished in asyncio.as_completed(tasks):
                await finished
        finally:
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        self._agent(run_id, state="working")

    async def _lead_pass(
        self, choice: ModelChoice, *, report: bool = False, prompt: str | None = None
    ) -> Any:
        run_id = self.lead_run_id
        assert run_id is not None and self.lead_ctx is not None
        spec = self.lead_ctx.agent
        if not self._model(choice):
            return await self._lead_job(run_id, spec, choice)
        own = cut_back(_load(self.store.run(run_id)["history"]))
        done = final_text(own)
        if done is not None and not report and self.output_type is None:
            return done
        results = None
        pending = pending_deferred(own)
        if pending:
            stored = self.store.results(run_id)
            calls = {}
            for c in pending:
                if c.tool_call_id in stored:
                    calls[c.tool_call_id] = _result_value(stored[c.tool_call_id])
                else:  # only when reporting at a cap: the work was not done
                    calls[c.tool_call_id] = ToolFailed("Stopped by the Spending Cap.")
            results = DeferredToolResults(calls=calls)
        prompt = (prompt or copy.REPORT_NOW) if report else (None if own else self.text)
        if not own and not report and prompt is not None and self.lead_ctx.rec is not None:
            from qsone.engine.map_digest import digest

            navigation = digest(self.lead_ctx.rec)
            if navigation:
                prompt += "\n\n" + as_data(
                    navigation, source="project_map", fence=self.lead_ctx.fence
                )
                self.store.mark_untrusted(self.brief_id)
        earlier = self._earlier()
        effort = self.lead_effort(choice)
        # the Lead is sent the tool groups its Brief opened (tool_groups)
        model = tool_groups.ToolGroups(self._costed(run_id, "lead", choice, effort))
        agent = agents.build_agent(
            spec,
            model,
            tools.toolset((), self.lead_ctx) if report else self._toolset(spec, self.lead_ctx),
            output_type=[self.output_type or str, DeferredToolRequests],
        )
        if not report and self.output_type is None:
            agent.output_validator(self._truthful)
        said = bool(lead_text(own))
        self._agent(run_id, state="thinking", model=choice.model)
        async with agent.iter(
            prompt,
            message_history=(earlier + own) or None,
            deferred_tool_results=results,
            instructions=self._instructions(choice),
            retries=TOOL_RETRIES,
            model_settings=None if effort is None else ModelSettings(thinking=effort),
            usage_limits=UsageLimits(request_limit=REPORT_LIMIT if report else STEP_LIMIT),
        ) as run:
            self.lead_run = run
            try:
                while self.steering:
                    run.enqueue(self.steering.pop(0))
                async for node in run:
                    if not Agent.is_call_tools_node(node):
                        self._tools_done(run_id)
                    if Agent.is_model_request_node(node):
                        if self.read_repeats >= 3 and not report:
                            self._save(run_id, run.all_messages()[len(earlier) :])
                            raise UsageLimitExceeded("Repeated full reads")
                        self._agent(run_id, state="thinking")
                        self.answer_from = self.said  # where this response's words begin
                        if self.redo_cleared:  # the screen dropped every word said so far
                            said, self.redo_cleared = False, False
                        async with node.stream(run.ctx) as events:
                            first = True
                            async for ev in events:
                                text = None
                                if isinstance(ev, PartStartEvent) and isinstance(ev.part, TextPart):
                                    text = ev.part.content
                                    if said and first:
                                        self.emit(TextDelta(self.brief_id, "\n\n"))
                                    first = False
                                elif isinstance(ev, PartDeltaEvent) and isinstance(
                                    ev.delta, TextPartDelta
                                ):
                                    text = ev.delta.content_delta
                                if text:
                                    said = True
                                    self.emit(TextDelta(self.brief_id, text))
                    elif Agent.is_call_tools_node(node):
                        self._say_tools(run_id, spec, node.model_response)
                    self._save(run_id, run.all_messages()[len(earlier) :])
            finally:
                self.lead_run = None
                self._tools_done(run_id)
            self._save(run_id, run.all_messages()[len(earlier) :])
            output = run.result.output
        if isinstance(output, DeferredToolRequests):
            return _DEFERRED
        return output
