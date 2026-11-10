import asyncio
from dataclasses import replace
from uuid import uuid4

from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

from qsone import copy
from qsone.engine import selection, tool_groups
from qsone.engine.mcp_server import RunScope
from qsone.engine.runner.errors import _Busy, _Fail
from qsone.engine.runner.histories import _load, final_text
from qsone.engine.runner.shared import WORK
from qsone.engine.types import AgentSpec, ModelChoice, Role, reply_line


class _BriefLink:
    """The Subscription Link: a run on the engineer's Claude Code, mirrored as a history."""

    # The Subscription Link -------------------------------------------------------------------

    async def _job(self, run_id: str, spec: AgentSpec, choice: ModelChoice, task: str) -> str:
        """One run on an agent connector (the engineer's Claude Code), with its own MCP token.
        Keeps a mirror of what it did as an ordinary history."""
        connector = self.found[choice.connector]
        run = self.store.run(run_id)
        card = self.card(choice)
        role: Role = spec.role if spec.role != "specialist" else spec.tier
        effort = self.lead_effort(choice) if run_id == self.lead_run_id else None
        await self.engine.spending.before_request(self, brief_id=self.brief_id, card=card)
        mirror = _load(run["history"])
        prompt = task
        if run["session_id"] is not None:
            prompt = copy.CONTINUE_AFTER_RESTART if final_text(mirror) is None else task
        if not mirror or final_text(mirror) is not None:
            mirror.append(ModelRequest(parts=[UserPromptPart(task)]))
        if run_id == self.lead_run_id and self.steering:
            # steers sent before the Lead started go with its first message, as the
            # PydanticAI Lead enqueues them (lead.py); no await from here to `claude_lead`
            steers, self.steering = self.steering, []
            prompt = "\n\n".join((prompt, *steers))
            mirror.append(ModelRequest(parts=[UserPromptPart(s) for s in steers]))

        def on_result(name: str, args: dict, text: str) -> None:
            call_id = f"mcp-{uuid4().hex[:12]}"
            mirror.append(ModelResponse(parts=[ToolCallPart(name, args, tool_call_id=call_id)]))
            mirror.append(ModelRequest(parts=[ToolReturnPart(name, text, tool_call_id=call_id)]))
            self._save(run_id, mirror)
            on = self._focus(name, args)
            if on is not None:
                self._agent(run_id, focus=on)

        ctx = self.lead_ctx if run_id == self.lead_run_id else self._ctx(run_id, spec)
        # Claude Code is given every tool at once: no group to open
        spec = replace(spec, tools=tuple(t for t in spec.tools if t != tool_groups.OPEN))
        token = self.engine.mcp.issue(RunScope(ctx, spec.tools, on_result))
        self.tokens.add(token)
        job_type = _agent_job()
        job = job_type(
            run_id=run_id,
            brief_id=self.brief_id,
            spec=spec,
            task=prompt,
            model=choice.model,
            mcp_url=self.engine.mcp_url(),
            mcp_token=token,
            tools=spec.tools,
            cwd=self.engine.data_dir / WORK / run_id,
            resume=run["session_id"],
            effort=effort,
        )
        if run_id == self.lead_run_id:
            self.claude_lead = (connector, run_id)
        try:
            outcome = await connector.run(job, self.emit)
        finally:
            self.claude_lead = None
            self.engine.mcp.revoke(token)
            self.tokens.discard(token)
        if outcome.session_id and self.cancel_mode != "crash":
            self.store.set_run(run_id, session_id=outcome.session_id)
        self.engine.spending.after_response(
            brief_id=self.brief_id,
            project_id=self.place.project_id,
            run_id=run_id,
            role=role,
            card=card,
            input_tokens=sum(n for _, n, _ in outcome.usage),
            output_tokens=sum(n for _, _, n in outcome.usage),
            reported_usd=outcome.reported_usd,
            effort=effort,
            member_id=self.member_of(run_id),
        )
        if outcome.ended == "limit":
            raise _Busy()
        if outcome.ended == "signed_out":
            raise _Fail(copy.CLAUDE_CODE_SIGNED_OUT)
        if outcome.ended == "stopped":
            raise asyncio.CancelledError()
        if outcome.ended not in ("done", "max_tokens"):
            raise _Fail(copy.fill(copy.AI_FAILED, provider=connector.name))
        mirror.append(ModelResponse(parts=[TextPart(outcome.text)]))
        self._save(run_id, mirror)
        return outcome.text

    async def _lead_job(self, run_id: str, spec: AgentSpec, choice: ModelChoice) -> str:
        self._agent(run_id, state="working", model=choice.model)
        # Claude Code reads only its instructions file: a Brief from code's own instruction
        # (Plan 8) and the canvas selection go there.
        for extra in (reply_line(self.text), self.instruction, selection.line(self.selection)):
            if extra:
                spec = replace(spec, instructions=f"{spec.instructions}\n\n{extra}")
        return await self._job(run_id, spec, choice, self.text)


def _agent_job():
    from qsone.engine.connectors.claude_code import AgentJob

    return AgentJob
