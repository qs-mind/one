import asyncio
from dataclasses import replace
from datetime import datetime
from decimal import ROUND_HALF_UP
from typing import Any

from pydantic_ai import ModelRetry

from qsone import copy, usage
from qsone.deliverables import tools as outputs
from qsone.engine import agents, checker, general, numbers_guard, roles, team, truth
from qsone.engine import connectors as connectors_mod
from qsone.engine.runner.histories import _tool_results
from qsone.engine.runner.shared import utc_now
from qsone.engine.runner.truth_checks import _marked
from qsone.engine.team import TeamSetup
from qsone.engine.types import Data, ModelChoice, Role, TextDelta, Unsourced
from qsone.journey import engineer


class _BriefStages:
    """The whole Brief's first and last steps: its team made ready, its reply finished."""

    # The whole Brief ---------------------------------------------------------------------------

    async def _prepare(self) -> None:
        if self._given_sheet is not None:
            sheet, found = self._given_sheet
        else:
            sheet, found = await self.engine.sheet()
        self.sheet, self.found = sheet, {c.id: c for c in found}
        allowed = {c.choice for c in sheet}
        defaults = roles.defaults(sheet)
        saved = {
            r: c for r, c in roles.saved().items() if c in allowed and not connectors_mod.refused(c)
        }
        self.saved_roles = set(saved)
        picked: dict[Role, ModelChoice] = defaults | saved
        if self.lead_choice in allowed:  # picked in the message box for this Brief
            picked["lead"] = self.lead_choice
        if "lead" not in picked:
            picked["lead"] = sheet[0].choice
        for role in roles.ROLES:
            picked.setdefault(role, picked["lead"])
        book, project = self.engine.book, self.place.project_id
        measured = book.tokens_per_request(project)
        # the Lead's requests as measured at this Brief's effort (each effort costs its own)
        effort = self.lead_effort(picked["lead"])
        lead_measured = measured if effort is None else book.tokens_per_request(project, effort)
        self.setup = TeamSetup(tuple(sheet), picked, measured, lead_measured)
        lead = next(
            (
                r
                for r in self.store.runs(self.brief_id)
                if r["parent_id"] is None and r["spec"].role == "lead"
            ),
            None,
        )
        # The General chat's Lead has its three tools only; a project's has the project's.
        spec = general.lead_spec() if self.place.rec is None else agents.lead_spec()
        if self.mapping_files is not None:
            spec = replace(spec, name=copy.MAP_AI_LABEL, instructions="", tools=())
        introduced = engineer.card_line(engineer.card(self.engine.engineer_records()))
        if introduced:  # the introduction card's one line (Plan 8)
            spec = replace(spec, instructions=f"{spec.instructions}\n\n{introduced}")
        if lead is None:
            self.lead_run_id = self.store.new_run(self.brief_id, spec, picked["lead"], None)
        else:
            self.lead_run_id = lead["id"]
        self.lead_ctx = self._ctx(self.lead_run_id, spec)
        choice = self.store.run(self.lead_run_id)["choice"]
        self._agent(self.lead_run_id, spec=spec, model=choice.model, state="thinking")

    def results(self) -> list[str]:
        """What the Brief's tools gave (the team's own words do not count)."""
        return _tool_results(self.store.runs(self.brief_id))

    async def _finish(self, output: Any) -> None:
        if isinstance(output, str):
            clean = truth.clean_reply(output, shown=self._did().shown)
            if clean != output:  # JSON or ids that stayed after the retry: never on the screen
                self.emit(Data(self.brief_id, "redo", self.brief_id, {"from": 0, "to": self.said}))
                self.emit(TextDelta(self.brief_id, clean))
                self.worklog.truth = (self.worklog.truth or {}) | {"reply": clean}
                output = clean
            results = self.results()
            marked = await asyncio.to_thread(_marked, self.place.rec, output, results)
            unread_segments = [
                segment
                for segment, _, _ in truth.citations(output)
                if truth.unread_citations(segment, self._read_returns(), rec=self.place.rec)
            ]
            marked = list(dict.fromkeys([*marked, *unread_segments]))
            if marked:
                self.emit(Unsourced(self.brief_id, tuple(marked)))
            self.worklog.truth = (self.worklog.truth or {}) | {"unsourced": marked}
            named = numbers_guard.sourced(output, results)
            if named:  # decision 16.3: each opens into its ledger number's source card
                self.emit(Data(self.brief_id, "sourced", self.brief_id, {"numbers": named}))
            await self._facts(output)
        drafts = self.store.unchecked(self.brief_id)
        if self.place.rec is not None:  # Plan 6: the Deliverables this Brief made or changed
            returns = [
                found
                for run in self.store.runs(self.brief_id)
                if run["history"]
                for found in agents.tool_returns(run["history"])
            ]
            drafts += await asyncio.to_thread(outputs.unchecked, self.place.rec, returns)
        for draft in drafts:
            if checker.has_numbers(draft):
                try:
                    await team.check_deliverable(self.lead_ctx, draft.id)
                except ModelRetry:
                    pass  # settled meanwhile

    def _withdraw(self) -> None:
        for card in self.store.pending(self.brief_id):
            self.emit(Data(self.brief_id, "card", card.id, {"status": "withdrawn"}))
        self.store.withdraw_pending(self.brief_id)

    def _track_done(self) -> None:
        """Usage Stats' one `brief_done`: counts only, never a Desk's name (Plan 8)."""
        specialists = [
            r["spec"] for r in self.store.runs(self.brief_id) if r["spec"].role == "specialist"
        ]
        cost = self.engine.book.spent(brief_id=self.brief_id, count_equivalent=True)
        started = datetime.fromisoformat(self.store.brief(self.brief_id)["created_at"])
        usage.track(
            "brief_done",
            desks=len({s.desk or self.brief_id for s in specialists}),
            specialists=len(specialists),
            off_desk=bool(specialists),  # every Desk is Temporary or Draft until Plan 9
            cost_usd_cents=int((cost * 100).to_integral_value(ROUND_HALF_UP)),
            minutes=max(0, round((utc_now() - started).total_seconds() / 60)),
        )
