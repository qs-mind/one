import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from qsone import copy, usage
from qsone.engine.costs import CallRefused, CapReached
from qsone.engine.runner.errors import NoAI, _Fail
from qsone.engine.runner.events import _BriefEvents
from qsone.engine.runner.failures import _BriefFailures
from qsone.engine.runner.lead import _BriefLead
from qsone.engine.runner.link import _BriefLink
from qsone.engine.runner.models import _BriefModels
from qsone.engine.runner.shared import GENERAL, log
from qsone.engine.runner.specialists import _BriefSpecialists
from qsone.engine.runner.stages import _BriefStages
from qsone.engine.runner.steps import _BriefSteps
from qsone.engine.runner.team_host import _BriefTeamHost
from qsone.engine.runner.team_view import _AgentState, _BriefTeamView
from qsone.engine.runner.truth_checks import _BriefTruth
from qsone.engine.store import Store
from qsone.engine.team import TeamSetup
from qsone.engine.tools import ToolContext
from qsone.engine.types import (
    BriefState,
    Card,
    Effort,
    Event,
    ModelCard,
    ModelChoice,
    Role,
    Status,
    Text,
    brief_language,
)
from qsone.engine.worklog import WorkLog
from qsone.records.project import Records, RecordsError

if TYPE_CHECKING:
    from qsone.engine.runner.engine import Engine

# The Brief task ------------------------------------------------------------------------------


@dataclass
class _Place:
    store: Store
    rec: Records | None  # the open project; None for the General chat
    project_id: str | None
    project_name: str | None

    @property
    def channel(self) -> str:
        return self.project_id or GENERAL


class _Brief(
    _BriefEvents,
    _BriefTeamView,
    _BriefTeamHost,
    _BriefModels,
    _BriefSteps,
    _BriefFailures,
    _BriefLead,
    _BriefLink,
    _BriefSpecialists,
    _BriefStages,
    _BriefTruth,
):
    """One Brief while this core runs it: its task, its event log, and the `TeamHost` its
    tools use."""

    def __init__(
        self,
        engine: "Engine",
        place: _Place,
        brief: dict,
        *,
        instruction: str | None = None,
        output_type: type | None = None,
        sheet: tuple[list[ModelCard], list] | None = None,
        lead: ModelChoice | None = None,
    ) -> None:
        self.engine = engine
        self.place = place
        self.store = place.store
        self.brief_id: str = brief["id"]
        self.chat_id: str = brief["chat_id"]
        self.text: str = brief["text"]
        self.lang = brief_language(self.text)  # the engineer's, for the Brief's Progress words
        self.selection: list[dict] | None = brief["selection"]  # on the canvas (Plan 7)
        # The Lead QS's model and effort, as picked in the message box; the effort is kept with
        # the Brief, so a continued Brief thinks as hard as it began.
        self.lead_choice = lead
        self.effort: Effort | None = brief["effort"]
        self.state: BriefState = brief["status"]
        self.step: Text | None = brief["step"]
        self.instruction = instruction
        self.mapping_files = next(
            (
                item["anchor"]["project_map_files"]
                for item in brief.get("selection") or []
                if "project_map_files" in (item.get("anchor") or {})
            ),
            None,
        )
        self.output_type = output_type
        self.output: Any = None
        self.log: list[Event] = []
        self.finished = False
        self.task: asyncio.Task | None = None
        self.cancel_mode = "stop"  # "stop", "pause" (keep the Checkpoint as unfinished), "crash"
        self.waiting: dict[str, tuple[Card, asyncio.Future]] = {}
        self.steering: list[str] = []
        self.lead_run = None  # the Lead's PydanticAI `AgentRun` while one runs
        self.claude_lead: tuple[Any, str] | None = None  # (connector, run id) of a Claude Code Lead
        self.agents: dict[str, _AgentState] = {}
        self.tokens: set[str] = set()
        self.setup: TeamSetup | None = None
        self.saved_roles: set[Role] = set()  # the roles the engineer chose in Settings
        self.sheet: list[ModelCard] = []
        self.found: dict[str, Any] = {}
        self._given_sheet = sheet
        self.lead_run_id: str | None = None
        self.mapping_passes = None
        self.lead_ctx: ToolContext | None = None
        self.truth_retried = False  # the reply went back once to be fixed (engine.truth)
        self.changes = 0  # the writes this Brief made to the records since it started (`wrote`)
        self.read_repeats = 0
        self.step_limited = False  # the Lead reached STEP_LIMIT and reported what it had
        self.budget_approved = False  # the engineer said yes to the Brief Budget of its plan
        self.said = 0  # the reply's length so far, in the screen's units (UTF-16)
        self.answer_from = 0  # where the Lead's latest response began in it
        self.redo_cleared = False  # a reply sent back left the screen with no words
        self.refusals: dict[str, Text] = {}  # each tool's last refusal, in the engineer's words
        self._news = asyncio.Event()
        saved = brief.get("worklog")
        self.worklog = (
            WorkLog.load(saved, stopped_at=brief["updated_at"])
            if saved
            else WorkLog(started=self._now())
        )

    async def main(self) -> None:
        try:
            if self.step is None:
                self.step = copy.STEP_QUEUED
            self.set_state("queued")
            async with self.engine._brief_slots:
                self.set_state(
                    "running", copy.STEP_STARTED if self.step == copy.STEP_QUEUED else None
                )
                await self._prepare()
                try:
                    if self.mapping_files is not None:
                        from qsone.records.mapping import ai as map_ai

                        await map_ai.run(
                            self.place.rec,
                            self.models(self.lead_run_id),
                            file_ids=self.mapping_files,
                            passes=self.mapping_passes(self) if self.mapping_passes else None,
                        )
                        output = ""
                    else:
                        output = await self._lead()
                except CapReached as reached:
                    if not reached.report:
                        raise
                    self.set_state("paused_cap")
                    try:
                        if self.mapping_files is None:
                            await self._lead(report=True)
                    except CapReached:
                        pass
                    raise
                if self.mapping_files is None:
                    await self._finish(output)
                self.output = output
                self.set_state("done", copy.STEP_DONE)
                self._track_done()
        except asyncio.CancelledError:
            if self.cancel_mode == "crash":
                raise
            self._withdraw()
            if self.cancel_mode == "stop":
                self.set_state("stopped", self._stopped_line())
            else:
                self.emit(Status(self.brief_id, self.state, self.step))
        except CapReached:
            self.set_state("stopped", copy.STOPPED)
        except (CallRefused, _Fail) as failed:
            self._withdraw()
            self.set_state("failed", failed.text)
        except RecordsError as failed:
            log.warning("brief %s: records error", self.brief_id)
            self.set_state("failed", failed.text)
        except NoAI as none:  # a stored Brief launched with no AI linked: plain words, no crash
            self._withdraw()
            self.set_state("failed", none.text)
        except Exception as error:
            log.exception("brief %s failed", self.brief_id)
            usage.crash(error)  # a bug in One: its class and line, never the message
            self._withdraw()
            # only `_attempts` knows a provider's error; anything that reaches here is ONE's own
            self.set_state("failed", copy.CORE_FAILED)
        finally:
            self.finished = True
            for token in tuple(self.tokens):
                self.engine.mcp.revoke(token)
            self.engine._ended(self)
            self._notify()
