import asyncio
import shutil
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from qsone import activity, copy
from qsone.engine import cards, desks, general
from qsone.engine import connectors as connectors_mod
from qsone.engine.costs import Spending
from qsone.engine.mcp_server import McpGate
from qsone.engine.runner.brief import _Brief, _Place
from qsone.engine.runner.errors import BriefBusy, NoAI, _Fail
from qsone.engine.runner.shared import GENERAL, WORK, log, utc_now
from qsone.engine.store import UNFINISHED, CostBook, Store
from qsone.engine.types import Card, Effort, Event, ModelCard, ModelChoice
from qsone.projects import Projects
from qsone.records.project import Records, RecordsError

# The engine ----------------------------------------------------------------------------------


class Engine:
    """Every Brief of this core. One for the app (`app.state.engine`)."""

    def __init__(
        self,
        *,
        projects: Projects,
        data_dir: Path,
        connectors: Callable[[], list] | None = None,
        clock: Callable[[], datetime] = utc_now,
        sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep,
        max_briefs: int = 3,
        max_agents: int = 3,
        mcp: McpGate | None = None,
        meaning: Any = None,
        services: Any = None,
    ) -> None:
        self.projects = projects
        self.data_dir = Path(data_dir)
        self.connectors = connectors or (lambda: connectors_mod.connectors())
        self.clock = clock
        self.sleep = sleep
        self.mcp = mcp or McpGate()
        self.meaning = meaning
        self.services = services  # Plan 5's `tools.services.Services`, set by the app (Task 15)
        self.base_url: str | None = None  # the core's own address, for the MCP config
        self._brief_slots = asyncio.Semaphore(max_briefs)
        self._agent_slots = asyncio.Semaphore(max_agents)
        self._briefs: dict[str, _Brief] = {}
        self._outputs: dict[str, Any] = {}
        self._brief_chats: dict[str, str] = {}
        self._ended_unseen: dict[str, dict] = {}  # chat id: its last Brief, done or failed, unseen
        self._close_after: set[str] = set()  # projects to close when their Brief ends
        self._general: Records | None = None
        self.book: CostBook
        self.spending: Spending

    # Life ------------------------------------------------------------------------------------

    def _ready(self) -> None:
        if self._general is None or not self._general.is_open:
            self._general = general.open_engineer_records(self.data_dir, self._escrow)
            self.book = CostBook(self._general)
            self.spending = Spending(self.book, clock=self.clock)

    def _escrow(self):
        """The account's Backup key escrow, asked only when a lost key is looked for."""
        backups = getattr(self.projects, "backups", None)
        return backups.escrow() if backups is not None else None

    def engineer_records(self) -> Records:
        """The open Engineer Records file (Plan 5's tools use it). Raises `RecordsError` when
        it does not open."""
        self._ready()
        assert self._general is not None
        return self._general

    def cost_book(self) -> CostBook | None:
        """The open cost book, or None before `start` or while the file is not open."""
        return self.book if self._general is not None and self._general.is_open else None

    async def start(self) -> None:
        """Opens the Engineer Records file. Never continues a Brief by itself. A file that does
        not open leaves the app up: each Brief then answers why, in plain words."""
        try:
            self._ready()
        except (RecordsError, OSError) as e:  # the core starts anyway
            log.warning("The Engineer Records file did not open (%s)", type(e).__name__)

    async def _cancel(self, mode: str) -> int:
        briefs = [b for b in self._briefs.values() if b.task is not None and not b.finished]
        for b in briefs:
            b.cancel_mode = mode
            b.task.cancel()
        await asyncio.gather(*(b.task for b in briefs), return_exceptions=True)
        return len(briefs)

    async def pause_all(self) -> int:
        """Plan 8: every running Brief stops at its Checkpoint and waits for Continue."""
        return await self._cancel("pause")

    async def shutdown(self) -> None:
        """Stops every Brief, keeping its Checkpoint, and closes the Engineer Records file."""
        await self._cancel("pause")
        if self._general is not None:
            self._general.close()

    async def crash(self) -> None:
        """For tests: what a power cut leaves (no bookkeeping at all)."""
        await self._cancel("crash")
        if self._general is not None:
            self._general.close()

    def mcp_url(self) -> str:
        if self.base_url is None:
            raise _Fail(copy.fill(copy.AI_FAILED, provider="Claude Code"))
        return self.base_url.rstrip("/") + "/mcp"

    # Where a chat lives ------------------------------------------------------------------------

    def _place(self, chat_id: str) -> _Place:
        """Raises `RecordsError` when the project is not open."""
        self._ready()
        if chat_id == GENERAL:
            return _Place(Store(self._general, project_id=None), None, None, None)
        rec = self.projects.get(chat_id)
        return _Place(Store(rec, project_id=chat_id), rec, chat_id, rec.meta()["name"])

    def _places(self) -> list[_Place]:
        """General and every project on this computer, opened if needed."""
        found = [self._place(GENERAL)]
        for project in self.projects.list():
            if "error" in project:
                continue
            try:
                self.projects.open(project["id"])
                found.append(self._place(project["id"]))
            except RecordsError:
                continue
        return found

    def _in(self, channel: str) -> list[_Brief]:
        return [b for b in self._briefs.values() if b.place.channel == channel]

    def _publish(self, channel: str, event: dict) -> None:
        activity.publish(channel, event)

    def _ended(self, brief: _Brief) -> None:
        self._briefs.pop(brief.brief_id, None)
        self._outputs[brief.brief_id] = brief.output
        if brief.cancel_mode == "crash":
            return
        if brief.state in ("done", "failed"):
            self._ended_unseen[brief.chat_id] = _chat_activity(brief, brief.state)
        else:  # stopped by the engineer, or paused with the core: nothing to tell
            self._ended_unseen.pop(brief.chat_id, None)
        if brief.chat_id in self._close_after and self.active(brief.chat_id) is None:
            self._close_after.discard(brief.chat_id)
            asyncio.get_running_loop().run_in_executor(None, self._close, brief.chat_id)
        for agent in brief.agents.values():
            self._publish(brief.place.channel, {"type": "agent-gone", "id": agent.run_id})
        if brief.state in ("done", "stopped", "failed"):
            for run in brief.store.runs(brief.brief_id):
                shutil.rmtree(self.data_dir / WORK / run["id"], ignore_errors=True)

    async def sheet(self) -> tuple[list[ModelCard], list]:
        """The Model Data Sheet and the connectors. Raises `NoAI` when it is empty."""
        found = self.connectors()
        listed, errors = await cards.listed(found)
        if not listed:
            raise NoAI(next(iter(errors.values()), copy.NO_AI))
        return listed, found

    # Briefs ----------------------------------------------------------------------------------

    def active(self, chat_id: str, *, include_mapping=True) -> str | None:
        mapping = None
        for b in self._briefs.values():
            if b.chat_id == chat_id and not b.finished:
                if b.mapping_files is None:
                    return b.brief_id
                mapping = b.brief_id
        return mapping if include_mapping else None

    async def map_project(self, project_id: str, file_ids: list[str], *, passes=None) -> bool:
        """Use a normal chat Brief for automatic mapping, approvals, events and spending."""
        from qsone.records.mapping import store as map_store

        if self.active(project_id) is not None:
            return False
        place = self._place(project_id)
        try:
            sheet = await self.sheet()
        except NoAI:
            with place.rec.write(map_store.ACTOR) as c:
                for fid in file_ids:
                    map_store.write(
                        c,
                        place.rec,
                        "map_files",
                        {
                            "file_id": fid,
                            "ai_state": "no_ai",
                            "note": copy.NO_AI,
                        },
                    )
            return True
        if self.active(project_id) is not None:
            return False
        selection = [
            {
                "kind": "files",
                "id": project_id,
                "title": copy.MAP_AI_LABEL["en"],
                "anchor": {"project_map_files": file_ids},
            }
        ]
        bid = place.store.new_brief(project_id, copy.MAP_AI_LABEL["en"], selection)
        from qsone.records.mapping.facts import mapping_passes

        brief = _Brief(self, place, place.store.brief(bid), sheet=sheet)
        brief.mapping_passes = passes or mapping_passes
        self._launch(brief)
        return True

    async def start_brief(
        self,
        chat_id: str,
        text: str,
        *,
        instruction: str | None = None,
        output_type: type | None = None,
        selection: list[dict] | None = None,
        lead: ModelChoice | None = None,
        effort: Effort | None = None,
    ) -> str:
        """Starts a Brief in the chat (a project id or "general"), under the caps. `selection`
        is what the engineer selected on the canvas (`engine.selection.read`). `lead` and
        `effort` are the Lead QS's model and effort picked in the message box; without them the
        Lead runs on its role's model at its provider's own effort. An effort the model does not
        accept is dropped. Raises `BriefBusy`, `NoAI` (also for a `lead` no longer on the Model
        Data Sheet) and `RecordsError`."""
        place = self._place(chat_id)
        busy = self.active(chat_id, include_mapping=False)
        if busy is not None:
            raise BriefBusy(busy)
        sheet = await self.sheet()
        busy = self.active(chat_id, include_mapping=False)
        if busy is not None:
            raise BriefBusy(busy)
        if lead is not None:
            card = next((c for c in sheet[0] if c.choice == lead), None)
            if card is None:
                raise NoAI(copy.CHAT_MODEL_GONE)
            if effort not in card.efforts:
                effort = None
        brief_id = place.store.new_brief(chat_id, text, selection, effort=effort)
        self._launch(
            _Brief(
                self,
                place,
                place.store.brief(brief_id),
                instruction=instruction,
                output_type=output_type,
                sheet=sheet,
                lead=lead,
            )
        )
        log.info("brief %s started", brief_id)
        return brief_id

    def _launch(self, brief: _Brief) -> None:
        self._briefs[brief.brief_id] = brief
        self._brief_chats[brief.brief_id] = brief.chat_id
        self._ended_unseen.pop(brief.chat_id, None)  # the chat's new Brief is what it does now
        brief.task = asyncio.create_task(brief.main(), name=f"brief-{brief.brief_id}")

    async def result(self, brief_id: str) -> Any:
        """The Brief's output when it ends (Plan 8: a Brief from code with its `output_type`)."""
        brief = self._briefs.get(brief_id)
        if brief is not None and brief.task is not None:
            await asyncio.gather(brief.task, return_exceptions=True)
        return self._outputs.get(brief_id)

    def _brief(self, brief_id: str) -> _Brief:
        brief = self._briefs.get(brief_id)
        if brief is None or brief.finished:
            raise LookupError(brief_id)
        return brief

    def events(self, brief_id: str) -> AsyncIterator[Event]:
        """The Brief's events from its start, then live until it ends."""
        brief = self._briefs.get(brief_id)
        if brief is None:
            raise LookupError(brief_id)
        return brief.events()

    async def stop(self, brief_id: str) -> None:
        """Stop the current Brief in this chat, even if the screen still names its predecessor.

        Resolve and cancel before the first await: a queued successor must not slip through
        the handover. An unknown id cannot select another chat.
        """
        chat = self._brief_chats.get(brief_id)
        current = self.active(chat) if chat is not None else None
        brief = self._brief(current or brief_id)
        brief.cancel_mode = "stop"
        assert brief.task is not None
        brief.task.cancel()
        await asyncio.gather(brief.task, return_exceptions=True)
        if not brief.finished:  # cancelled before main() entered its try/finally
            brief._withdraw()
            brief.set_state("stopped", brief._stopped_line())
            brief.finished = True
            self._ended(brief)
            brief._notify()

    async def steer(self, brief_id: str, text: str) -> None:
        """Raises `LookupError` when the Brief is not running."""
        brief = self._brief(brief_id)
        if brief.lead_run is not None:
            brief.lead_run.enqueue(text)
        elif brief.claude_lead is not None:
            connector, run_id = brief.claude_lead
            try:
                await connector.steer(run_id, text)
            except LookupError:
                brief.steering.append(text)
        else:
            brief.steering.append(text)
        log.info("brief %s steered", brief_id)

    async def answer(self, card_id: str, choice: str) -> None:
        """Raises `LookupError` when no running Brief waits on the card, `ValueError` with a
        choice that is not one of its options."""
        for brief in tuple(self._briefs.values()):
            if card_id in brief.waiting:
                brief.answer(card_id, choice)
                return
        raise LookupError(card_id)

    def options(self, card_id: str) -> list[str]:
        card = self.card(card_id)
        return [] if card is None else list(card.options)

    def card(self, card_id: str) -> Card | None:
        """The card a running Brief waits on, or None."""
        for brief in self._briefs.values():
            if card_id in brief.waiting:
                return brief.waiting[card_id][0]
        return None

    def unfinished(self) -> list[dict]:
        """Every unfinished Brief that is not running now, in every project and General."""
        found = []
        for place in self._places():
            try:
                briefs = place.store.unfinished()
            except RecordsError:
                continue  # a project closed while it was read (a project switch): asked again later
            for b in briefs:
                if b["id"] in self._briefs:
                    continue
                found.append(
                    {
                        "id": b["id"],
                        "chat_id": b["chat_id"],
                        "project_name": place.project_name,
                        "step": b["step"] or copy.STEP_STARTED,
                        "state": b["status"],
                    }
                )
        return found

    async def continue_brief(self, brief_id: str) -> None:
        """Continues an unfinished Brief from its last Checkpoint. Raises `LookupError`."""
        if brief_id in self._briefs:
            return
        for place in self._places():
            try:
                brief = place.store.brief(brief_id)
            except LookupError:
                continue
            if brief["status"] not in UNFINISHED:
                break
            busy = self.active(brief["chat_id"])
            if busy is not None:
                raise BriefBusy(busy)
            place.store.withdraw_pending(brief_id)  # a stale approval: the redone call asks again
            runner = _Brief(self, place, brief)
            runner.log += _stored_events(place.store, brief, self)
            self._launch(runner)
            log.info("brief %s continued", brief_id)
            return
        raise LookupError(brief_id)

    def leave_brief(self, brief_id: str) -> None:
        """The engineer chose not to continue an unfinished Brief: it ends as stopped, its
        waiting cards withdrawn, so it is never offered again. Raises `BriefBusy` while it
        runs, `LookupError` when no unfinished Brief has the id."""
        if brief_id in self._briefs:
            raise BriefBusy(brief_id)
        for place in self._places():
            try:
                brief = place.store.brief(brief_id)
            except LookupError:
                continue
            if brief["status"] not in UNFINISHED:
                break
            place.store.withdraw_pending(brief_id)
            place.store.set_status(brief_id, "stopped", copy.STOPPED)
            log.info("brief %s left", brief_id)
            return
        raise LookupError(brief_id)

    # The chat as stored ----------------------------------------------------------------------

    def chat_messages(self, chat_id: str) -> list[dict]:
        """AI SDK UI messages, rebuilt from the chat's stored Briefs, oldest first."""
        from qsone.engine.stream import message_parts

        place = self._place(chat_id)
        with place.store.rec.read() as c:
            ids = [
                i
                for (i,) in c.execute(
                    "SELECT id FROM briefs WHERE chat_id = ? ORDER BY created_at, rowid",
                    (chat_id,),
                ).fetchall()
            ]
        messages = []
        for brief_id in ids:
            brief = place.store.brief(brief_id)
            question = {
                "id": question_id(brief_id),
                "role": "user",
                "parts": [{"type": "text", "text": brief["text"]}],
            }
            if brief["selection"] and not any(
                "project_map_files" in (i.get("anchor") or {}) for i in brief["selection"]
            ):  # the chip on the engineer's message (Plan 7)
                question["metadata"] = {"selection": brief["selection"]}
            messages.append(question)
            running = self._briefs.get(brief_id)
            if running is not None:
                parts = message_parts(running.log)
            else:
                waiting = brief["status"] in UNFINISHED
                events = _stored_events(place.store, brief, self, unfinished=waiting)
                parts = message_parts(events, with_status=not waiting)
            messages.append({"id": reply_id(brief_id), "role": "assistant", "parts": parts})
        if place.rec is not None:  # what ONE found in each drop of files, in its place in time
            messages = _with_reports(messages, place.rec)
        return messages

    # Plan 7 ------------------------------------------------------------------------------------

    def team(self, project_id: str) -> dict:
        """Plan 7's `{desks: [DeskInfo], agents: [AgentInfo]}` for the project ("general" for
        the General chat)."""
        running = self._in(project_id)
        saved = [
            {"id": d["slug"], "name": d["name"], "stage": "draft"}
            for d in desks.saved(self.data_dir)
        ]
        temporary = [
            b.desk() for b in running if any(a.spec.role == "specialist" for a in b.agents.values())
        ]
        agents_now = [b.agent_info(a) for b in running for a in b.agents.values()]
        return {"desks": temporary + saved, "agents": agents_now}

    def activity(self, project_id: str) -> AsyncIterator[dict]:
        """Plan 7's `ActivityEvent`s for the project, as they come."""
        return activity.subscribe(project_id)

    def waiting(self, project_id: str) -> int:
        """How many cards wait for the engineer in the project's running Briefs."""
        return sum(len(b.waiting) for b in self._in(project_id))

    # Every chat at once, for the screen outside each chat (the top bar, the projects, notices)

    def chats(self) -> list[dict]:
        """Each chat with a running Brief ("working", or "waiting" while a card waits for the
        engineer) or a last Brief that ended unseen ("done", "failed"), as
        `{chat_id, brief_id, state, name}` (`name`: the project's, None for the General chat).
        From memory only: no project file is opened, so the screen may ask every few seconds."""
        found = {
            b.chat_id: _chat_activity(b, "waiting" if b.waiting else "working")
            for b in self._briefs.values()
            if not b.finished
        }
        ended = [e for chat_id, e in self._ended_unseen.items() if chat_id not in found]
        return list(found.values()) + ended

    def seen(self, chat_id: str) -> None:
        """The engineer has the chat open: its ended Brief's mark clears."""
        self._ended_unseen.pop(chat_id, None)

    def keep_open(self, project_id: str) -> bool:
        """Asked before the screen closes a project: True while a Brief runs in it, whose file
        then stays open and closes when the Brief ends, so moving on never cuts it short."""
        if self.active(project_id) is None:
            return False
        self._close_after.add(project_id)
        return True

    def opened(self, project_id: str) -> None:
        """The project was opened again: it stays open after its Brief ends."""
        self._close_after.discard(project_id)

    def _close(self, project_id: str) -> None:
        try:
            self.projects.close(project_id)
        except (RecordsError, OSError) as e:  # it closes with the core anyway
            log.warning(
                "project %s did not close after its Brief (%s)", project_id, type(e).__name__
            )


def _chat_activity(brief: _Brief, state: str) -> dict:
    return {
        "chat_id": brief.chat_id,
        "brief_id": brief.brief_id,
        "state": state,
        "name": brief.place.project_name,
    }


from qsone.engine.runner.stored import (  # noqa: E402
    _stored_events,
    _with_reports,
    question_id,
    reply_id,
)
