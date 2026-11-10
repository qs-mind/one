from dataclasses import dataclass, field

from qsone import copy
from qsone.engine import identity_live
from qsone.engine.runner.shared import utc_now
from qsone.engine.types import AgentSpec, Text


@dataclass
class _AgentState:
    run_id: str
    spec: AgentSpec
    model: str
    state: str = "thinking"
    line: Text | None = None
    focus: dict | None = None  # Plan 7's Focus: the frame it works on, from its tool calls
    at: str = field(default_factory=lambda: utc_now().isoformat())


class _BriefTeamView:
    """Plan 7's view of the Brief's team: each agent's state, the Desk and the waiting cards."""

    # Plan 7's view of the team ---------------------------------------------------------------

    def _agent(
        self,
        run_id: str,
        *,
        spec: AgentSpec | None = None,
        model: str | None = None,
        state: str | None = None,
        line: Text | None = None,
        focus: dict | None = None,
    ) -> None:
        """`focus` None keeps the frame the agent was on."""
        found = self.agents.get(run_id)
        if found is None:
            if spec is None:
                return
            found = self.agents[run_id] = _AgentState(run_id, spec, model or "")
            if spec.role == "specialist" and spec.desk is None:
                self.engine._publish(self.place.channel, {"type": "desk", "desk": self.desk()})
        if model is not None:
            found.model = model
        if state is not None:
            found.state = state
        if line is not None:
            found.line = line
        if focus is not None:
            found.focus = focus
        found.at = utc_now().isoformat()
        self.engine._publish(self.place.channel, {"type": "agent", "agent": self.agent_info(found)})
        identity_live.changed(self.engine, self.place.project_id, found.spec.id)

    def agent_info(self, a: _AgentState) -> dict:
        desk = None
        if a.spec.role == "specialist":
            desk = a.spec.desk or self.brief_id
        return {
            "id": a.run_id,
            "kind": a.spec.role,  # lead, checker, specialist or quick: where the canvas puts it
            "role": a.spec.name,
            "desk_id": desk,
            "model": a.model,
            # the model's provider on this Brief's sheet, for its company's logo (None: not on it)
            "provider": next((c.provider for c in self.sheet if c.choice.model == a.model), None),
            # its name as the sheet gives it («Gemini 3.1 Flash Lite»): never the raw id
            "model_name": next((c.name for c in self.sheet if c.choice.model == a.model), None),
            "state": a.state,
            "line": a.line,
            "lang": self.lang,  # the line's language: the Brief's
            "brief_id": self.brief_id,
            "focus": a.focus,
            "at": a.at,
        }

    def desk(self) -> dict:
        return {"id": self.brief_id, "name": copy.DESK_TEMPORARY, "stage": "temporary"}

    def _waiting_count(self) -> None:
        count = sum(len(b.waiting) for b in self.engine._in(self.place.channel))
        self.engine._publish(self.place.channel, {"type": "waiting", "count": count})
