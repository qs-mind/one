from pydantic_ai import Agent

from qsone import copy
from qsone.engine import agents, checker, truth
from qsone.engine.runner.errors import _Fail
from qsone.engine.runner.histories import _load, cut_back, final_text
from qsone.engine.runner.shared import TOOL_RETRIES
from qsone.engine.types import AgentSpec, CheckPacket, ModelChoice, Review, reply_line

REVIEW_AS_JSON = (  # the model reads it: a check on Claude Code answers in text
    'Answer with one JSON object only: {"code": "A" | "B" | "C", "comments": '
    '[{"about": "...", "text": "..."}], "checked": ["..."]}.'
)
# Every specialist's principles from ONE, beside the Lead's instructions for it: the tender day's
# weak model priced walls at a block's supply price «شامل العمالة» and cited worked-out numbers
# as read from a quote. The record tools refuse both; these say why before they do.
SPECIALIST_RULES = (
    "ONE's principles for every specialist:\n"
    "- A number read from a file is recorded at the place that has it, as written there. A "
    "number you work out (a total, an average, a price with waste or a margin) goes through "
    "calculate with its inputs and formula, never as read from a file.\n"
    "- A rate says what it includes: supply, or supply and installation. A supply-only quote "
    "never covers labour; an installed item's rate adds labour from its own source, with "
    "calculate. A rate is per the item's own unit.\n"
    "- When the files have a build-up (rate analysis) or a materials price sheet, read them "
    "first (search_records with the item's words, then read_chunk): an item's unit rate = "
    "materials + labour + waste, as its build-up row has them, never one material alone. A "
    "material is missing only when no sheet has it.\n"
    "- A value you do not have is missing: say so; never leave a blank for it."
)


class _BriefSpecialists:
    """One pass of a specialist, and one check by the Checking QS, each on its own model."""

    # Specialists and the checker ---------------------------------------------------------------

    async def _specialist_pass(
        self, run_id: str, spec: AgentSpec, task: str, choice: ModelChoice
    ) -> str:
        if not self._model(choice):
            return await self._job(run_id, spec, choice, task)
        own = cut_back(_load(self.store.run(run_id)["history"]))
        prompt = task if not own or final_text(own) is not None else None
        ctx = self._ctx(run_id, spec)
        agent = agents.build_agent(
            spec, self._costed(run_id, spec.tier, choice), self._toolset(spec, ctx), output_type=str
        )
        # what a specialist writes for the engineer is in the engineer's language (audit C6)
        extra = reply_line(self.text) if spec.role == "specialist" else None
        if spec.role == "specialist":  # ONE's own principles, whatever the Lead wrote (5 Nov)
            extra = "\n\n".join((truth.today_line(self.engine.clock()), extra, SPECIALIST_RULES))
        async with agent.iter(
            prompt, message_history=own or None, instructions=extra, retries=TOOL_RETRIES
        ) as run:
            async for node in run:
                if Agent.is_call_tools_node(node):
                    self._say_tools(run_id, spec, node.model_response)
                else:
                    self._tools_done(run_id)
                self._save(run_id, run.all_messages())
            self._tools_done(run_id)
            self._save(run_id, run.all_messages())
            return run.result.output

    async def _check_pass(
        self,
        run_id: str,
        spec: AgentSpec,
        packet: CheckPacket,
        maker: ModelChoice,
        choice: ModelChoice,
    ) -> Review:
        ctx = self._ctx(run_id, spec)
        mine, theirs = self.card(choice), self.card(maker)
        if not self._model(choice):
            text = await self._job(
                run_id,
                spec,
                choice,
                f"{checker.packet_text(packet, ctx.fence)}\n\n{REVIEW_AS_JSON}",
            )
            try:
                out = checker.ReviewOut.model_validate_json(
                    text[text.index("{") : text.rindex("}") + 1]
                )
            except ValueError:
                raise _Fail(copy.fill(copy.AI_FAILED, provider=self._provider(choice))) from None
            return Review(
                code=out.code,
                comments=tuple(c.model_dump() for c in out.comments),
                checker=choice,
                same_provider=mine.provider == theirs.provider,
                round=1,
                checked=tuple(out.checked),
            )
        return await checker.review(
            packet,
            self._costed(run_id, "checker", choice),
            checker=mine,
            maker=theirs,
            toolset=self._toolset(spec, ctx),
            fence=ctx.fence,
        )
