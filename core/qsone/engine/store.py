"""The engine's durable state, inside one encrypted Records file (schema migration 3; migration 4
renamed its Deliverable drafts table to `deliverable_drafts`).

`Store` keeps a chat's Briefs, each agent run's Checkpoint (its message history), stored
results of deferred tool calls, approvals, writes already made, the team's messages,
Deliverable drafts and their Reviews. `CostBook` keeps every AI cost, only in the Engineer
Records file, so the day and month caps count every project.

Approvals and Reviews write audit rows; history saves do not (working state, and large).
JSON is written with `ensure_ascii=False`; money is decimal text, never a float."""

import json
from dataclasses import asdict
from datetime import UTC, date, datetime, tzinfo
from decimal import Decimal
from uuid import uuid4

from qsone.engine.types import (
    AgentSpec,
    BriefState,
    Card,
    DeliverableDraft,
    ModelChoice,
    Review,
    Role,
    TeamMessage,
    Text,
    choice_of,
)
from qsone.records import audit
from qsone.records.project import Records

ENGINE = "engine"  # the actor of the engine's own writes
ENGINEER = "engineer"  # the actor of the engineer's answers
UNFINISHED: tuple[BriefState, ...] = (
    "queued",
    "running",
    "waiting_engineer",
    "waiting_connection",
    "paused_cap",
)


def _dump(value) -> str:
    return json.dumps(value, ensure_ascii=False)


def _new_id() -> str:
    return uuid4().hex


def _spec(text: str) -> AgentSpec:
    d = json.loads(text)
    return AgentSpec(**{**d, "tools": tuple(d["tools"])})


def _card(text: str) -> Card:
    d = json.loads(text)
    return Card(**{**d, "options": tuple(d["options"])})


def _draft(text: str) -> DeliverableDraft:
    d = json.loads(text)
    return DeliverableDraft(**{**d, "rows": tuple(d["rows"]), "sources": tuple(d["sources"])})


class Store:
    """Over one open Records file: a project's, or the Engineer Records for the General chat
    (`project_id=None`). Uses only `rec.read()` and `rec.write(actor)`."""

    def __init__(self, rec: Records, *, project_id: str | None):
        self.rec = rec
        self.project_id = project_id

    # Briefs -----------------------------------------------------------------------------------

    def new_brief(
        self,
        chat_id: str,
        text: str,
        selection: list[dict] | None = None,
        *,
        effort: str | None = None,
    ) -> str:
        """`selection` is what the engineer selected on the canvas (Plan 7), kept with it;
        `effort` the Lead QS's effort picked in the message box (None: the provider's own)."""
        brief_id = _new_id()
        at = self.rec.clock()
        with self.rec.write(ENGINE) as c:
            c.execute(
                "INSERT INTO briefs(id, chat_id, text, status, created_at, updated_at, selection,"
                " effort) VALUES (?, ?, ?, 'queued', ?, ?, ?, ?)",
                (
                    brief_id,
                    chat_id,
                    text,
                    at,
                    at,
                    None if not selection else _dump(selection),
                    effort,
                ),
            )
        return brief_id

    _BRIEF = (
        "id, chat_id, text, status, step, read_untrusted, allowed, created_at, updated_at,"
        " selection, effort, worklog"
    )

    @staticmethod
    def _brief_row(row) -> dict:
        keys = Store._BRIEF.split(", ")
        d = dict(zip(keys, row, strict=True))
        d["step"] = None if d["step"] is None else json.loads(d["step"])
        d["allowed"] = json.loads(d["allowed"])
        d["selection"] = None if d["selection"] is None else json.loads(d["selection"])
        return d

    def brief(self, brief_id: str) -> dict:
        """Raises `LookupError` for an unknown id."""
        with self.rec.read() as c:
            row = c.execute(f"SELECT {self._BRIEF} FROM briefs WHERE id = ?", (brief_id,))
            row = row.fetchone()
        if row is None:
            raise LookupError(brief_id)
        return self._brief_row(row)

    def set_status(self, brief_id: str, status: BriefState, step: Text | None = None) -> None:
        """With no `step`, the last step stays: an unfinished Brief is listed with it."""
        with self.rec.write(ENGINE) as c:
            c.execute(
                "UPDATE briefs SET status = ?, step = coalesce(?, step), updated_at = ?"
                " WHERE id = ?",
                (status, None if step is None else _dump(step), self.rec.clock(), brief_id),
            )

    def set_worklog(self, brief_id: str, worklog: str) -> None:
        """The Brief's work log (`worklog.WorkLog.saved`): screen text, not a project fact, so
        not audited."""
        with self.rec.write(ENGINE) as c:
            c.execute("UPDATE briefs SET worklog = ? WHERE id = ?", (worklog, brief_id))

    def mark_untrusted(self, brief_id: str) -> None:
        with self.rec.write(ENGINE) as c:
            c.execute(
                "UPDATE briefs SET read_untrusted = 1, updated_at = ? WHERE id = ?",
                (self.rec.clock(), brief_id),
            )

    def allow(self, brief_id: str, tool: str) -> None:
        """The engineer's "Allow for this Brief" for one tool."""
        with self.rec.write(ENGINE) as c:
            (allowed,) = c.execute(
                "SELECT allowed FROM briefs WHERE id = ?", (brief_id,)
            ).fetchone()
            tools = json.loads(allowed)
            if tool not in tools:
                c.execute(
                    "UPDATE briefs SET allowed = ?, updated_at = ? WHERE id = ?",
                    (_dump([*tools, tool]), self.rec.clock(), brief_id),
                )

    def allowed(self, brief_id: str) -> set[str]:
        return set(self.brief(brief_id)["allowed"])

    def unfinished(self) -> list[dict]:
        """Briefs that are queued, running, waiting or paused at a cap; oldest first."""
        marks = ", ".join("?" * len(UNFINISHED))
        with self.rec.read() as c:
            rows = c.execute(
                f"SELECT {self._BRIEF} FROM briefs WHERE status IN ({marks})"
                " ORDER BY created_at, rowid",
                UNFINISHED,
            ).fetchall()
        return [self._brief_row(row) for row in rows]

    # Agent runs and their Checkpoints ---------------------------------------------------------

    def new_run(
        self, brief_id: str, spec: AgentSpec, choice: ModelChoice, parent_id: str | None
    ) -> str:
        run_id = _new_id()
        at = self.rec.clock()
        with self.rec.write(ENGINE) as c:
            c.execute(
                "INSERT INTO agent_runs(id, brief_id, parent_id, spec, connector, model, status,"
                " created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, 'running', ?, ?)",
                (
                    run_id,
                    brief_id,
                    parent_id,
                    _dump(asdict(spec)),
                    choice.connector,
                    choice.model,
                    at,
                    at,
                ),
            )
        return run_id

    _RUN = (
        "id, brief_id, parent_id, spec, connector, model, status, history, session_id,"
        " created_at, updated_at"
    )

    @staticmethod
    def _run_row(row) -> dict:
        (
            run_id,
            brief_id,
            parent_id,
            spec,
            connector,
            model,
            status,
            history,
            session_id,
            created_at,
            updated_at,
        ) = row
        return {
            "id": run_id,
            "brief_id": brief_id,
            "parent_id": parent_id,
            "spec": _spec(spec),
            "choice": ModelChoice(connector, model),
            "status": status,
            "history": None if history is None else bytes(history),
            "session_id": session_id,
            "created_at": created_at,
            "updated_at": updated_at,
        }

    def run(self, run_id: str) -> dict:
        """Raises `LookupError` for an unknown id."""
        with self.rec.read() as c:
            row = c.execute(f"SELECT {self._RUN} FROM agent_runs WHERE id = ?", (run_id,))
            row = row.fetchone()
        if row is None:
            raise LookupError(run_id)
        return self._run_row(row)

    def runs(self, brief_id: str) -> list[dict]:
        """Oldest first."""
        with self.rec.read() as c:
            rows = c.execute(
                f"SELECT {self._RUN} FROM agent_runs WHERE brief_id = ? ORDER BY created_at, rowid",
                (brief_id,),
            ).fetchall()
        return [self._run_row(row) for row in rows]

    def save_history(self, run_id: str, history: bytes) -> None:
        """Replaces the saved history: the run's Checkpoint. Not audited."""
        with self.rec.write(ENGINE) as c:
            c.execute(
                "UPDATE agent_runs SET history = ?, updated_at = ? WHERE id = ?",
                (history, self.rec.clock(), run_id),
            )

    def set_run(
        self,
        run_id: str,
        *,
        status: str | None = None,
        session_id: str | None = None,
        choice: ModelChoice | None = None,
    ) -> None:
        """Changes only what is given."""
        with self.rec.write(ENGINE) as c:
            c.execute(
                "UPDATE agent_runs SET status = coalesce(?, status),"
                " session_id = coalesce(?, session_id), connector = coalesce(?, connector),"
                " model = coalesce(?, model), updated_at = ? WHERE id = ?",
                (
                    status,
                    session_id,
                    None if choice is None else choice.connector,
                    None if choice is None else choice.model,
                    self.rec.clock(),
                    run_id,
                ),
            )

    def save_result(self, run_id: str, call_id: str, result: str) -> None:
        """Once per call: a second save of the same call raises `IntegrityError`."""
        with self.rec.write(ENGINE) as c:
            c.execute(
                "INSERT INTO deferred_results(run_id, call_id, result) VALUES (?, ?, ?)",
                (run_id, call_id, result),
            )

    def results(self, run_id: str) -> dict[str, str]:
        with self.rec.read() as c:
            rows = c.execute(
                "SELECT call_id, result FROM deferred_results WHERE run_id = ? ORDER BY rowid",
                (run_id,),
            )
            return dict(rows.fetchall())

    def lead_histories(self, chat_id: str, before: str) -> list[bytes]:
        """The saved Lead histories of the chat's Briefs made before Brief `before`, oldest
        first. Specialists' and the checker's runs are never included."""
        with self.rec.read() as c:
            rows = c.execute(
                "SELECT r.history FROM agent_runs r JOIN briefs b ON b.id = r.brief_id"
                " WHERE b.chat_id = ? AND r.parent_id IS NULL AND r.history IS NOT NULL"
                " AND json_extract(r.spec, '$.role') = 'lead'"
                " AND (b.created_at, b.rowid) < (SELECT created_at, rowid FROM briefs WHERE id = ?)"
                " ORDER BY b.created_at, b.rowid, r.created_at, r.rowid",
                (chat_id, before),
            ).fetchall()
        return [bytes(history) for (history,) in rows]

    # Approvals --------------------------------------------------------------------------------

    def add_approval(
        self, brief_id: str, card: Card, *, run_id: str | None = None, call_id: str | None = None
    ) -> None:
        """Stores the card as pending before it is shown."""
        at = self.rec.clock()
        with self.rec.write(ENGINE) as c:
            c.execute(
                "INSERT INTO approvals(id, brief_id, run_id, call_id, card, status, asked_at)"
                " VALUES (?, ?, ?, ?, ?, 'pending', ?)",
                (card.id, brief_id, run_id, call_id, _dump(asdict(card)), at),
            )
            audit.record(
                c,
                at=at,
                actor=ENGINE,
                action="ask",
                table="approvals",
                row_id=card.id,
                before=None,
                after={
                    "brief_id": brief_id,
                    "kind": card.kind,
                    "run_id": run_id,
                    "call_id": call_id,
                },
            )

    def settle(self, card_id: str, choice: str) -> None:
        """The engineer's answer. Raises `LookupError` when no such card is pending (it was
        settled or withdrawn) and `ValueError` when `choice` is not one of its options. A card
        with a payload settles with `types.answer_value`'s JSON text, kept as it is."""
        at = self.rec.clock()
        with self.rec.write(ENGINEER) as c:
            row = c.execute(
                "SELECT card FROM approvals WHERE id = ? AND status = 'pending'", (card_id,)
            ).fetchone()
            if row is None:
                raise LookupError(card_id)
            card = _card(row[0])
            if choice_of(card, choice) not in card.options:
                raise ValueError(choice)
            c.execute(
                "UPDATE approvals SET status = 'settled', choice = ?, settled_at = ? WHERE id = ?",
                (choice, at, card_id),
            )
            audit.record(
                c,
                at=at,
                actor=ENGINEER,
                action="settle",
                table="approvals",
                row_id=card_id,
                before={"status": "pending"},
                after={"status": "settled", "choice": choice_of(card, choice)},
            )

    def pending(self, brief_id: str) -> list[Card]:
        """Oldest first."""
        with self.rec.read() as c:
            rows = c.execute(
                "SELECT card FROM approvals WHERE brief_id = ? AND status = 'pending'"
                " ORDER BY asked_at, rowid",
                (brief_id,),
            ).fetchall()
        return [_card(card) for (card,) in rows]

    def withdraw_pending(self, brief_id: str) -> None:
        """After a restart: a stale approval is withdrawn, and the redone call asks again."""
        at = self.rec.clock()
        with self.rec.write(ENGINE) as c:
            ids = [
                card_id
                for (card_id,) in c.execute(
                    "SELECT id FROM approvals WHERE brief_id = ? AND status = 'pending'",
                    (brief_id,),
                ).fetchall()
            ]
            for card_id in ids:
                c.execute(
                    "UPDATE approvals SET status = 'withdrawn', settled_at = ? WHERE id = ?",
                    (at, card_id),
                )
                audit.record(
                    c,
                    at=at,
                    actor=ENGINE,
                    action="withdraw",
                    table="approvals",
                    row_id=card_id,
                    before={"status": "pending"},
                    after={"status": "withdrawn"},
                )
        if ids and self.project_id is not None:
            from qsone.engine.team import messages  # the team room's raised messages (C6)

            messages.cards_withdrawn(self.rec, ids)

    # Writes already made ----------------------------------------------------------------------

    def known_write(self, brief_id: str, key: str) -> str | None:
        with self.rec.read() as c:
            row = c.execute(
                "SELECT result_id FROM brief_writes WHERE brief_id = ? AND key = ?",
                (brief_id, key),
            ).fetchone()
        return None if row is None else row[0]

    def remember_write(self, brief_id: str, key: str, result_id: str) -> None:
        """The first write for a key is kept; a replayed one leaves it as it is."""
        with self.rec.write(ENGINE) as c:
            c.execute(
                "INSERT OR IGNORE INTO brief_writes(brief_id, key, result_id) VALUES (?, ?, ?)",
                (brief_id, key, result_id),
            )

    # The team ---------------------------------------------------------------------------------

    def add_team_message(self, message: TeamMessage) -> None:
        with self.rec.write(ENGINE) as c:
            c.execute(
                "INSERT INTO team_messages(id, brief_id, at, sender, recipient, text)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (
                    message.id,
                    message.brief_id,
                    self.rec.clock(),
                    _dump(message.sender),
                    _dump(message.recipient),
                    message.text,
                ),
            )

    def team(self, brief_id: str) -> list[dict]:
        """The Coordination Room of one Brief, oldest first."""
        with self.rec.read() as c:
            rows = c.execute(
                "SELECT id, at, sender, recipient, text FROM team_messages WHERE brief_id = ?"
                " ORDER BY at, rowid",
                (brief_id,),
            ).fetchall()
        return [
            {"id": i, "at": at, "sender": json.loads(s), "recipient": json.loads(r), "text": t}
            for i, at, s, r, t in rows
        ]

    # Deliverable drafts and their Reviews -----------------------------------------------------

    def save_deliverable(self, brief_id: str, run_id: str, draft: DeliverableDraft) -> None:
        with self.rec.write(ENGINE) as c:
            c.execute(
                "INSERT INTO deliverable_drafts(id, brief_id, run_id, draft, replaces, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (
                    draft.id,
                    brief_id,
                    run_id,
                    _dump(asdict(draft)),
                    draft.replaces,
                    self.rec.clock(),
                ),
            )

    def deliverable(self, deliverable_id: str) -> DeliverableDraft:
        """Raises `LookupError` for an unknown id."""
        with self.rec.read() as c:
            row = c.execute(
                "SELECT draft FROM deliverable_drafts WHERE id = ?", (deliverable_id,)
            ).fetchone()
        if row is None:
            raise LookupError(deliverable_id)
        return _draft(row[0])

    def unchecked(self, brief_id: str) -> list[DeliverableDraft]:
        """The Brief's latest drafts (none replaces them) that have no Review yet, oldest first."""
        with self.rec.read() as c:
            rows = c.execute(
                "SELECT d.draft FROM deliverable_drafts d WHERE d.brief_id = ?"
                " AND NOT EXISTS (SELECT 1 FROM reviews v WHERE v.deliverable_id = d.id)"
                " AND NOT EXISTS (SELECT 1 FROM deliverable_drafts n WHERE n.replaces = d.id)"
                " ORDER BY d.created_at, d.rowid",
                (brief_id,),
            ).fetchall()
        return [_draft(draft) for (draft,) in rows]

    def save_review(self, deliverable_id: str, review: Review) -> None:
        review_id = _new_id()
        at = self.rec.clock()
        with self.rec.write(ENGINE) as c:
            c.execute(
                "INSERT INTO reviews(id, deliverable_id, round, code, comments, checker,"
                " same_provider, at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    review_id,
                    deliverable_id,
                    review.round,
                    review.code,
                    _dump(list(review.comments)),
                    _dump(asdict(review.checker)),
                    int(review.same_provider),
                    at,
                ),
            )
            audit.record(
                c,
                at=at,
                actor=ENGINE,
                action="review",
                table="reviews",
                row_id=review_id,
                before=None,
                after={
                    "deliverable_id": deliverable_id,
                    "code": review.code,
                    "round": review.round,
                },
            )

    def reviews(self, deliverable_id: str) -> list[Review]:
        """The Reviews of this draft and of every draft it replaces, oldest first."""
        with self.rec.read() as c:
            rows = c.execute(
                "WITH RECURSIVE chain(id) AS (SELECT ? UNION"
                " SELECT d.replaces FROM deliverable_drafts d JOIN chain ON d.id = chain.id"
                " WHERE d.replaces IS NOT NULL)"
                " SELECT code, comments, checker, same_provider, round FROM reviews"
                " WHERE deliverable_id IN (SELECT id FROM chain) ORDER BY at, rowid",
                (deliverable_id,),
            ).fetchall()
        return [
            Review(
                code=code,
                comments=tuple(json.loads(comments)),
                checker=ModelChoice(**json.loads(checker)),
                same_provider=bool(same_provider),
                round=round_,
            )
            for code, comments, checker, same_provider, round_ in rows
        ]


class CostBook:
    """Every AI cost, append-only, only in the Engineer Records file.

    `local_day` is the engineer's own day: `at` in `local_tz`, which is the computer's own
    zone unless a test gives one."""

    def __init__(self, rec: Records, *, local_tz: tzinfo | None = None):
        self.rec = rec
        self.local_tz = local_tz

    def add(
        self,
        *,
        brief_id: str,
        project_id: str | None,
        run_id: str,
        role: Role,
        choice: ModelChoice,
        input_tokens: int,
        output_tokens: int,
        usd: Decimal | None,
        equivalent: bool,
        basis: str,
        at: datetime,
        effort: str | None = None,
        cache_read: int = 0,
        cache_write: int = 0,
        member_id: str | None = None,
    ) -> None:
        """`usd` is None when the price is unknown: it is kept as unknown, never as 0. `effort`
        is the one the request was sent with (None: the provider's own). `cache_read` and
        `cache_write` are the input tokens the provider read from or wrote to its prompt cache,
        counted within `input_tokens`. `member_id` is the run's member (`engine/identity.py`).
        Raises `TypeError` for money that is not a `Decimal` and `ValueError` for a naive `at`."""
        if usd is not None and not isinstance(usd, Decimal):
            raise TypeError("money is a Decimal, never a float")
        if at.utcoffset() is None:
            raise ValueError("`at` needs its time zone")
        local_day = at.astimezone(self.local_tz).date().isoformat()
        with self.rec.write(ENGINE) as c:
            c.execute(
                "INSERT INTO ai_costs(at, local_day, brief_id, project_id, run_id, role,"
                " connector, model, input_tokens, output_tokens, usd, equivalent, basis, effort,"
                " cache_read_tokens, cache_write_tokens, member_id)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    at.astimezone(UTC).isoformat(timespec="microseconds"),
                    local_day,
                    brief_id,
                    project_id,
                    run_id,
                    role,
                    choice.connector,
                    choice.model,
                    input_tokens,
                    output_tokens,
                    None if usd is None else str(usd),
                    int(equivalent),
                    basis,
                    effort,
                    cache_read,
                    cache_write,
                    member_id,
                ),
            )

    def spent(
        self,
        *,
        brief_id: str | None = None,
        day: date | None = None,
        month: tuple[int, int] | None = None,
        count_equivalent: bool,
    ) -> Decimal:
        """The known cost in USD of what matches every filter given. Unknown costs are left out;
        equivalent cost (the Claude subscription) only when `count_equivalent`."""
        where, args = ["usd IS NOT NULL"], []
        if not count_equivalent:
            where.append("equivalent = 0")
        if brief_id is not None:
            where.append("brief_id = ?")
            args.append(brief_id)
        if day is not None:
            where.append("local_day = ?")
            args.append(day.isoformat())
        if month is not None:
            year, m = month
            start = date(year, m, 1)
            end = date(year + m // 12, m % 12 + 1, 1)
            where.append("local_day >= ? AND local_day < ?")
            args += [start.isoformat(), end.isoformat()]
        with self.rec.read() as c:
            rows = c.execute(f"SELECT usd FROM ai_costs WHERE {' AND '.join(where)}", args)
            return sum((Decimal(usd) for (usd,) in rows.fetchall()), Decimal("0"))

    def tokens(
        self,
        *,
        brief_id: str | None = None,
        day: date | None = None,
        month: tuple[int, int] | None = None,
        unpriced_only: bool = False,
    ) -> dict[str, int]:
        """The tokens of what matches every filter given, priced or not, and how many responses
        had no known price: {"input", "output", "cached", "unpriced"}, "cached" being the part of
        "input" read from a provider's prompt cache. `unpriced_only` counts only those (the caps
        of a model used without a price)."""
        where, args = ["1"], []
        if unpriced_only:
            where.append("usd IS NULL AND equivalent = 0")
        if brief_id is not None:
            where.append("brief_id = ?")
            args.append(brief_id)
        if day is not None:
            where.append("local_day = ?")
            args.append(day.isoformat())
        if month is not None:
            year, m = month
            where.append("local_day >= ? AND local_day < ?")
            args += [date(year, m, 1).isoformat(), date(year + m // 12, m % 12 + 1, 1).isoformat()]
        with self.rec.read() as c:
            found = c.execute(
                "SELECT coalesce(sum(input_tokens), 0), coalesce(sum(output_tokens), 0),"
                " coalesce(sum(usd IS NULL), 0), coalesce(sum(cache_read_tokens), 0)"
                f" FROM ai_costs WHERE {' AND '.join(where)}",
                args,
            ).fetchone()
        return {"input": found[0], "output": found[1], "cached": found[3], "unpriced": found[2]}

    def tokens_per_request(
        self, project_id: str | None, effort: str | None = None
    ) -> tuple[int, int, int] | None:
        """Average input and output tokens per model request in this project's past runs (the
        General chat's when None), rounded half up, and the number of requests; None if none.
        Only the requests sent with `effort` count (None: those sent with none)."""
        with self.rec.read() as c:
            total_in, total_out, n = c.execute(
                "SELECT sum(input_tokens), sum(output_tokens), count(*) FROM ai_costs"
                " WHERE project_id IS ? AND effort IS ?",
                (project_id, effort),
            ).fetchone()
        if n == 0:
            return None
        return (2 * total_in + n) // (2 * n), (2 * total_out + n) // (2 * n), n
