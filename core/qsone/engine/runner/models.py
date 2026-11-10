from qsone import copy
from qsone.engine import connectors as connectors_mod
from qsone.engine import oneshot, tools
from qsone.engine.costs import CostedModel
from qsone.engine.data_text import new_fence
from qsone.engine.runner.errors import _Fail
from qsone.engine.runner.shared import TOOL_RETRIES, WORK
from qsone.engine.tools import ToolContext
from qsone.engine.types import AgentSpec, Effort, ModelCard, ModelChoice, Role


class _BriefModels:
    """The models of the Brief's runs, and the tool context and toolset each run gets."""

    # Models ----------------------------------------------------------------------------------

    def _model(self, choice: ModelChoice) -> bool:
        connector = self.found.get(choice.connector)
        return connector is not None and connector.kind == "model"

    def card(self, choice: ModelChoice) -> ModelCard:
        for c in self.sheet:
            if c.choice == choice:
                return c
        connector = self.found.get(choice.connector)
        return ModelCard(
            choice=choice,
            name=choice.model,
            provider=getattr(connector, "provider", choice.connector),
            images=False,
            tools=True,
            context=None,
            price_in=None,
            price_out=None,
            price_source=None,
            subscription=getattr(connector, "kind", "") == "agent",
        )

    def _provider(self, choice: ModelChoice) -> str:
        connector = self.found.get(choice.connector)
        return getattr(connector, "name", choice.connector)

    def lead_effort(self, choice: ModelChoice) -> Effort | None:
        """The Brief's effort, when the Lead's model `choice` accepts it (a model moved to after
        a failure may not); None sends none, and the provider uses its own."""
        return self.effort if self.effort in self.card(choice).efforts else None

    def _costed(self, run_id: str, role: Role, choice: ModelChoice, effort: Effort | None = None):
        connector = self.found.get(choice.connector)
        if connector is None:
            raise _Fail(copy.NO_AI)
        if self.here_only and not self.card(choice).on_device:  # a run stored before
            raise _Fail(copy.CONFIDENTIAL_NO_LOCAL_AI)
        try:
            model = connector.model(choice.model)
        except connectors_mod.NoKey:
            raise _Fail(copy.NO_AI) from None
        return CostedModel(
            model,
            spending=self.engine.spending,
            host=self,
            brief_id=self.brief_id,
            project_id=self.place.project_id,
            run_id=run_id,
            role=role,
            card=self.card(choice),
            effort=effort,
            member_id=self.member_of(run_id),
        )

    def member_of(self, run_id: str) -> str | None:
        """The run's member: its spec's id (`engine/identity.py`)."""
        try:
            return self.store.run(run_id)["spec"].id
        except LookupError:
            return None

    def models(self, run_id: str) -> oneshot.Models:
        """This Brief's models, for the one-shot calls of a tool in run `run_id`."""
        return oneshot.Models(
            sheet=tuple(self.sheet),
            roles=dict(self.setup.roles) if self.setup is not None else {},
            connectors=dict(self.found),
            spending=self.engine.spending,
            host=self,
            brief_id=self.brief_id,
            project_id=self.place.project_id,
            run_id=run_id,
            work=self.engine.data_dir / WORK,
            member_id=self.member_of(run_id),
        )

    def _ctx(self, run_id: str, spec: AgentSpec) -> ToolContext:
        meaning = self.engine.meaning
        services = self.engine.services
        if services is not None:
            services = oneshot.for_run(services, self.models(run_id))
        return ToolContext(
            brief_id=self.brief_id,
            run_id=run_id,
            agent=spec,
            rec=self.place.rec,
            store=self.store,
            host=self,
            fence=new_fence(),
            embedder=meaning.embedder() if meaning is not None else None,
            services=services,
            projects=self.engine.projects,
        )

    def _toolset(self, spec: AgentSpec, ctx: ToolContext):
        found = tools.toolset(spec.tools, ctx)
        found.max_retries = TOOL_RETRIES
        return found
