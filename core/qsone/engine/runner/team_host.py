import asyncio
import json

from qsone import copy
from qsone.engine import agents, roles, team
from qsone.engine.runner.errors import _Fail
from qsone.engine.types import (
    AgentSpec,
    Asked,
    BriefState,
    Card,
    CheckPacket,
    ModelChoice,
    Progress,
    Review,
    Settled,
    TeamMessage,
    Text,
    choice_of,
)


class _BriefTeamHost:
    """The `TeamHost` the Brief's tools use: cards, team messages, specialists, the checker."""

    # TeamHost --------------------------------------------------------------------------------

    async def ask(self, card: Card) -> str:
        if card.id not in {c.id for c in self.store.pending(self.brief_id)}:
            self.store.add_approval(self.brief_id, card)  # stored before it is shown
        future = asyncio.get_running_loop().create_future()
        self.waiting[card.id] = (card, future)
        before = self.step
        state: BriefState = "paused_cap" if card.kind == "cap" else "waiting_engineer"
        # Consumers answering a card must already observe its paused state. Keep
        # the previous step until the card is visible; only then announce waiting.
        self.set_state(state)
        self.emit(Asked(self.brief_id, card))
        if card.kind == "question" and self.lead_run_id is not None:
            self.emit(Progress(self.brief_id, self.lead_run_id, copy.ROLE_LEAD, copy.DOING_ASK))
        self.set_state(state, copy.fill(copy.STEP_WAITING, title=card.title))
        if self.lead_run_id is not None:
            self._agent(self.lead_run_id, state="waiting")
        self._waiting_count()
        try:
            return await future
        finally:
            self.waiting.pop(card.id, None)
            self._waiting_count()
            if not self.waiting and self.state in ("waiting_engineer", "paused_cap"):
                self.set_state("running", before)
                if self.lead_run_id is not None:
                    self._agent(self.lead_run_id, state="working")

    def answer(self, card_id: str, choice: str) -> None:
        """`choice` is the settled value: an option, or a payload card's `answer_value`."""
        card, future = self.waiting[card_id]
        if choice_of(card, choice) not in card.options:
            raise ValueError(choice)
        try:
            self.store.settle(card_id, choice)
        except LookupError:
            pass  # stored by the tool that asked
        self.emit(Settled(self.brief_id, card_id, choice))
        if not future.done():
            future.set_result(choice)

    def post(self, message: TeamMessage) -> None:
        self.emit(message)  # send_message stored it already

    def note_refusal(self, tool: str, text: Text | None) -> None:
        """A tool call refused, with its words when ONE has them in both languages: the flag
        beside a reply that says it was done gives the engineer this reason (`_did`)."""
        if text is not None:
            self.refusals[tool] = text
        else:
            self.refusals.pop(tool, None)

    async def run_specialist(self, spec: AgentSpec, task: str, kit: dict) -> str:
        run_id = team.specialist_run(self.store, self.brief_id, spec.id)
        prompt = task
        if any(kit.get(k) for k in ("file_ids", "item_ids", "notes")):
            prompt = f"{task}\n\nKit: {json.dumps(kit, ensure_ascii=False)}"
        async with self.engine._agent_slots:
            self.store.set_run(run_id, status="running")
            choice = self.store.run(run_id)["choice"]
            self._agent(run_id, spec=spec, model=choice.model, state="thinking")
            try:
                out = await self._attempts(
                    run_id, spec, lambda c: self._specialist_pass(run_id, spec, prompt, c)
                )
            except _Fail as failed:  # the Lead hears it and decides; the Brief goes on
                self.store.set_run(run_id, status="failed")
                self._agent(run_id, state="failed", line=failed.text)
                return f"The specialist could not finish: {failed.text['en']}"
            self.store.set_run(run_id, status="done")
            self._agent(run_id, state="done")
            return out

    async def run_checker(self, packet: CheckPacket, maker: ModelChoice) -> Review:
        assert self.setup is not None
        spec = agents.checker_spec()
        choice = self.setup.roles.get("checker") or maker
        if choice == maker and "checker" not in self.saved_roles:
            # Only a default Checking QS moves off the maker's model, and never to a costlier
            # one: the engineer's own choice always wins (a Same-provider check, still blind).
            others = [
                c for c in roles.same_or_cheaper(self.sheet, maker, {maker}) if self._model(c)
            ]
            choice = others[0] if others else maker
        run_id = self.store.new_run(self.brief_id, spec, choice, self.lead_run_id)
        async with self.engine._agent_slots:
            self._agent(run_id, spec=spec, model=choice.model, state="working")
            self.emit(Progress(self.brief_id, run_id, spec.name, copy.STEP_CHECKING))
            try:
                review = await self._attempts(
                    run_id,
                    spec,
                    lambda c: self._check_pass(run_id, spec, packet, maker, c),
                    avoid=frozenset({maker}),
                )
            finally:
                self.store.set_run(run_id, status="done")
                self._agent(run_id, state="done")
        return review
