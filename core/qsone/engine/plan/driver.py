"""The plan driver (Phase 1, C3): code, never the model, moves an approved tender plan on, stage
after stage (decisions §17.2 and §17.20; spike `research_notes/2026-11-10-phase1-spikes/driver.md`).

A table-backed loop that keeps nothing in memory that matters. Every event only schedules
`advance(project_id)`, which reads the plan's open stage, that stage's latest claim
(`claims`) and the claimed Brief's row, brings the stage's status in line, and does the one
thing due. An event delivered twice changes nothing; one lost in a power cut is made up at the
next start, because the tables say what is due.

- A stage's Brief row and its claim are written in one transaction, then launched with no
  await between (`Engine.launch`): a stage never starts twice.
- `pending` -> `now` (claimed and launched) -> `waiting_engineer` (its latest Brief ended
  `done`, no Finding is raised or queued and no work runs in the tender; its output ids and
  `result` written, `outputs`)
  -> `approved` (route 11). The tender's work that follows a stage's Brief (a Finding's
  decision, "I have notes") counts for the open stage, and its done reply ends the stage again
  (`claims.worked`, `claims.ended`). A card, a cap pause, cut short, stopped, failed or no AI
  all leave the stage `now`: the tender row says why.
- The work stops only where its Brief asks the engineer (a card: missing information, money,
  anything leaving the machine) and at the stage's end; caps, Stop, steer and Continue are the
  runner's, as for any Brief. A stopped or failed stage goes on by route 25 (`retry`).
- At start (`resume_all`) and when a tender is opened again, its own cut-off stage continues
  by itself, after the Model Data Sheet answers; with no AI it waits, untouched."""

import asyncio
import logging

from qsone import copy
from qsone import phase1_contract as c
from qsone.deliverables import events
from qsone.engine.plan import claims, outputs, store
from qsone.engine.runner import GENERAL, BriefBusy, NoAI
from qsone.engine.store import ENGINE, UNFINISHED, Store
from qsone.journey import setup_state, understand
from qsone.records import audit
from qsone.records.project import Records, RecordsError

log = logging.getLogger(__name__)
DUE = "due"  # `_decide` without acting: a stage Brief would be launched now
ENDED = ("done", "stopped", "failed")
_running: "PlanDriver | None" = None  # the app's driver, while it runs


# Told by the plan routes (C2), which find these by name -----------------------------------------


def on_plan_approved(project_id: str) -> None:
    if _running is not None:
        _running.kick(project_id)


def on_stage_approved(project_id: str, stage_id: str) -> None:
    if _running is not None:
        _running.kick(project_id)


def on_plan_changed(project_id: str) -> None:
    """A Suggested change was accepted: a stage it adds, or one it frees, starts."""
    if _running is not None:
        _running.kick(project_id)


# The work a stage is given ----------------------------------------------------------------------


def stage_brief_text(plan: c.TenderPlan, stage: c.Stage, lang: str) -> str:
    """The stage's Brief text, in the engineer's language: its place in the plan, owner,
    outputs and gate, and what the engineer must supply when ONE cannot do it alone. It is the
    Brief's stored text, so a continued Brief is told its stage again."""
    owner = next((m.name.model_dump() for m in plan.team if m.id == stage.owner_member_id), None)
    titles = [o.title.model_dump() for o in stage.outputs] or [copy.STAGE_NO_OUTPUTS]
    listed = {k: copy.STAGE_JOIN[k].join(t[k] for t in titles) for k in ("en", "ar")}
    text = copy.fill(
        copy.STAGE_BRIEF,
        n=plan.stages.index(stage) + 1,
        total=len(plan.stages),
        title=stage.title.model_dump(),
        owner=owner or stage.owner_member_id,
        outputs=listed,
        gate=stage.gate.model_dump(),
    )[lang]
    if stage.engineer_supplies is not None:
        supplies = stage.engineer_supplies.model_dump()
        text += " " + copy.fill(copy.STAGE_BRIEF_SUPPLIES, supplies=supplies)[lang]
    return text


def _open(plan: c.TenderPlan) -> c.Stage | None:
    """The stage open now (`now` or `waiting_engineer`), else the next one due in order."""
    found = [s for s in plan.stages if s.status in ("now", "waiting_engineer")]
    return found[0] if found else next((s for s in plan.stages if s.status == "pending"), None)


def _deciding(conn) -> bool:
    """A Finding waits for the engineer's decision, or for its turn to be raised."""
    found = conn.execute("SELECT 1 FROM findings WHERE status IN ('raised', 'queued') LIMIT 1")
    return found.fetchone() is not None


class PlanDriver:
    """One for the app (`app.state.driver`): `start` on the event loop, `stop` before the
    engine shuts down."""

    def __init__(self, engine) -> None:
        self.engine = engine
        self._locks: dict[str, asyncio.Lock] = {}
        self._tasks: set[asyncio.Task] = set()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stopped = False

    # Life ----------------------------------------------------------------------------------------

    def start(self) -> None:
        global _running
        self._loop = asyncio.get_running_loop()
        self._stopped = False
        self.engine.watchers.append(self.on_brief)
        self.engine.on_open.append(self.on_project_opened)
        _running = self

    async def stop(self) -> None:
        """No more launches; waits for the advances in flight."""
        global _running
        self._stopped = True
        if _running is self:
            _running = None
        for found, mine in (
            (self.engine.watchers, self.on_brief),
            (self.engine.on_open, self.on_project_opened),
        ):
            if mine in found:
                found.remove(mine)
        await asyncio.gather(*tuple(self._tasks), return_exceptions=True)

    async def idle(self) -> None:
        """Waits until no advance is in flight (tests)."""
        while self._tasks:
            await asyncio.gather(*tuple(self._tasks), return_exceptions=True)
            await asyncio.sleep(0)

    # Events in: each only schedules an `advance`; safe from any thread, safe twice -------------

    def _soon(self, work) -> None:
        loop = self._loop
        if loop is None or self._stopped:
            return

        def go() -> None:
            task = loop.create_task(work())
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

        loop.call_soon_threadsafe(go)

    def kick(self, project_id: str, *, starting: bool = False) -> None:
        if project_id != GENERAL:
            self._soon(lambda: self.advance(project_id, starting=starting))

    def on_project_opened(self, project_id: str) -> None:
        self.kick(project_id, starting=True)

    def on_ai_changed(self) -> None:
        """The AI links changed (the app tells it after each change in the AI settings): what
        waited for an AI goes on, in a closed tender too, as at start-up."""
        self._soon(self.resume_all)

    def on_brief(self, chat_id: str, brief_id: str, state: str) -> None:
        """The runner's watcher, inside the Brief's task: the stage's status in line at once,
        a stage Brief that ended done marks its reply (`data-stage`), then an `advance`."""
        if chat_id == GENERAL:
            return
        try:
            rec = self.engine.projects.get(chat_id)
            if state == "queued":
                self._tell_lead(rec, brief_id)
            if rec.archived_at is None:
                self._decide(rec, chat_id, act=False)
            running = self.engine._briefs.get(brief_id) if state == "done" else None
            if running is not None:
                stage_id = claims.ended(rec, Store(rec, project_id=chat_id).brief(brief_id))
                if stage_id is not None:
                    running.emit(claims.stage_part(brief_id, stage_id))
        except RecordsError:
            pass  # a project closing: its next opening puts it right
        self.kick(chat_id)

    def _tell_lead(self, rec: Records, brief_id: str) -> None:
        """Before a Brief's Lead starts: the engineer's answer to its last Suggested change,
        when no steer told it, joins the Brief's instruction (route 12). Not a mapping or an
        "I understood this" Brief: the reading state and the card check know that one by its
        exact instruction, so the answer waits for the next ordinary work."""
        brief = self.engine._briefs.get(brief_id)
        if brief is None or brief.mapping_files is not None:
            return
        if brief.instruction == understand.INSTRUCTION:
            return
        said = store.untold(rec)
        if said is not None and store.told(rec, said[0]):
            line = said[1][setup_state.language()]
            brief.instruction = "\n\n".join(p for p in (brief.instruction, line) if p)

    # The loop ----------------------------------------------------------------------------------

    async def resume_all(self) -> None:
        """At start-up: every tender on this computer whose plan has work due. A closed one is
        looked at on its own and opened only when work is due; one tender's fault never stops
        the others."""
        for listed in await asyncio.to_thread(self.engine.projects.list):
            project_id = listed["id"]
            if "error" in listed or listed.get("archived_at") or self._stopped:
                continue
            try:
                opened = not listed["open"]
                if opened:
                    if not await asyncio.to_thread(self._due_closed, project_id):
                        continue
                    await asyncio.to_thread(self.engine.projects.open, project_id)
                await self.advance(project_id, starting=True)
                if opened and not self.engine.keep_open(project_id):  # nothing could start
                    await asyncio.to_thread(self.engine.projects.close, project_id, back_up=False)
            except Exception:  # noqa: BLE001 - the next tender still starts
                log.exception("plan driver: tender %s did not resume", project_id)

    async def advance(self, project_id: str, *, starting: bool = False) -> None:
        if self._stopped:
            return
        async with self._locks.setdefault(project_id, asyncio.Lock()):
            try:
                rec = self.engine.projects.get(project_id)
                if rec.archived_at is not None:
                    return  # a read-only tender: nothing is due in it
                if self._decide(rec, project_id, act=False, starting=starting) != DUE:
                    return
                try:
                    await self.engine.sheet()  # the Lead must be able to work before a claim
                except NoAI:
                    return  # it waits as it is; the next event tries again
                if self._stopped:
                    return
                launch = self._decide(rec, project_id, act=True, starting=starting)
                if launch is not None:  # no await between the claim and the launch
                    self.engine.launch(project_id, launch)
            except (RecordsError, BriefBusy, LookupError):
                return  # closed, archived or taken meanwhile: its next event comes back here
            except Exception:  # noqa: BLE001 - one tender's fault never stops the others
                log.exception("plan driver: tender %s", project_id)

    def _decide(
        self, rec: Records, project_id: str, *, act: bool, starting: bool = False
    ) -> str | None:
        """One transaction: the open stage's status in line with its latest Brief. With `act`,
        the stage Brief due now is claimed and its id given, to launch at once; without, DUE
        says one would be."""
        with events.held(), rec.write(ENGINE) as conn:
            plan = store.current(rec)
            if plan is None or plan.status != "approved":
                return None
            stage = _open(plan)
            if stage is None:
                return None  # every stage is signed off
            claim = claims.latest(conn, stage.id)
            busy = self.engine.active(project_id)
            if claim is None:
                if busy is not None:
                    return None  # the chat has other work: its end comes back here
                if not act:
                    return DUE
                brief_id = self._claim(conn, rec, plan, stage, 1)
                self._move(rec, stage, "now")
                return brief_id
            if claim["status"] == "done":
                made = outputs.ids(conn, rec, stage)
                status = "now" if _deciding(conn) else "waiting_engineer"
                if status != "now" and self._working(project_id):
                    status = stage.status  # it waits for the work that follows to end
                self._move(rec, stage, status, made=made)
                return None
            self._move(rec, stage, "now")
            if claim["status"] not in UNFINISHED or claim["brief_id"] in self.engine._briefs:
                return None  # stopped or failed (route 25 goes on), or it runs
            if busy is not None or (claim["began"] and not starting):
                return None  # cut short while ONE ran: Continue, or the next start
            return claim["brief_id"] if act else DUE

    def _working(self, project_id: str) -> bool:
        """Work runs in the tender: a Brief that has not ended (one that just ended is still in
        memory while its watchers are told)."""
        return any(
            b.chat_id == project_id and not b.finished and b.state not in ENDED
            for b in self.engine._briefs.values()
        )

    def _claim(
        self, conn, rec: Records, plan, stage, attempt: int, *, text=None, actor=ENGINE
    ) -> str:
        """Inside the caller's write: the stage's Brief row and its claim, together."""
        text = text or stage_brief_text(plan, stage, setup_state.language())
        brief_id = Store(rec, project_id=rec.id).new_brief(rec.id, text, by="one")
        at = rec.clock()
        claims.add(conn, stage.id, attempt, brief_id, at)
        after = {"attempt": attempt, "brief_id": brief_id}
        audit.record(
            conn,
            at=at,
            actor=actor,
            action="start",
            table=claims.TABLE,
            row_id=stage.id,
            before=None,
            after=after,
        )
        return brief_id

    def _move(
        self, rec: Records, stage: c.Stage, status: str, *, made: list[str | None] | None = None
    ) -> None:
        """The stage's status; with `made` (its work ended), its output ids and `result` too."""
        if made is None:
            if stage.status != status:
                store.set_stage_status(rec, stage.id, status, actor=ENGINE)
            return
        result = outputs.result(stage, made)
        before = (stage.status, [o.id for o in stage.outputs], stage.result)
        if before != (status, made, c.Text.model_validate(result)):
            store.set_stage_status(
                rec, stage.id, status, result=result, output_ids=made, actor=ENGINE
            )

    def _due_closed(self, project_id: str) -> bool:
        """For a closed tender, on its own handle: is a stage due to start or to continue, or
        its status behind its Brief's?"""
        rec = self.engine.projects.open_file(project_id)
        try:
            plan = store.current(rec)
            stage = None if plan is None or plan.status != "approved" else _open(plan)
            if stage is None or rec.archived_at is not None:
                return False
            with rec.read() as conn:
                claim = claims.latest(conn, stage.id)
            if claim is None or claim["status"] in UNFINISHED:
                return True
            return claim["status"] == "done" and stage.status == "now"
        finally:
            rec.close()

    # The engineer's "Try again" on a stage (route 25) --------------------------------------------

    async def retry(self, project_id: str, stage_id: str, brief_id: str) -> str:
        """The stage's work again after its latest Brief stopped or failed: attempt + 1, with
        the same words, started by ONE; its id. Raises `LookupError` when `brief_id` is not the
        stage's latest Brief or did not end stopped or failed, `BriefBusy`, `NoAI`,
        `RecordsError`."""
        async with self._locks.setdefault(project_id, asyncio.Lock()):
            rec = self.engine.projects.get(project_id)
            await self.engine.sheet()
            with events.held(), rec.write("engineer") as conn:
                claim = claims.latest(conn, stage_id)
                plan = store.current(rec)
                stage = next((s for s in plan.stages if s.id == stage_id), None) if plan else None
                if stage is None or claim is None or claim["brief_id"] != brief_id:
                    raise LookupError(brief_id)
                if claim["status"] not in ("stopped", "failed"):
                    raise LookupError(brief_id)
                busy = self.engine.active(project_id)
                if busy is not None:
                    raise BriefBusy(busy)
                old = Store(rec, project_id=project_id).brief(brief_id)["text"]
                new = self._claim(
                    conn, rec, plan, stage, claim["attempt"] + 1, text=old, actor="engineer"
                )
                self._move(rec, stage, "now")
            self.engine.launch(project_id, new)
            return new
