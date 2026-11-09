import asyncio
import json
import re
from typing import Any

from pydantic_ai import ModelRetry
from pydantic_ai.messages import ModelRequest, ModelResponse, ToolReturnPart

from qsone import copy, view
from qsone.engine import agents, numbers_guard, team, truth
from qsone.engine.runner.histories import NOT_DONE, _calls, _load, _refused, outcomes
from qsone.engine.runner.shared import log
from qsone.engine.tools import REGISTRY
from qsone.engine.types import Data, Text
from qsone.journey import understand
from qsone.records.project import Records

# The reply says ONE could not search the web: the screen adds the way to set it up.
_NO_SEARCH_SAID = re.compile(
    r"الإنترنت|الانترنت|\bالنت\b|الويب|أونلاين|اونلاين|\b(?:web|internet|online)\b", re.I
)


def _descriptions(rec: Records) -> list[str]:
    """The project's item descriptions, as its records have them."""
    with rec.read() as c:
        rows = c.execute(
            "SELECT json_extract(fields, '$.description') FROM items"
            " WHERE json_extract(fields, '$.description') IS NOT NULL"
        ).fetchall()
    return [str(d) for (d,) in rows]


def _no_search_notice(brief_id: str) -> Data:
    """The notice the web tools give when no search is set up, with its fix (audit B8)."""
    data = {"text": copy.WEB_NO_SEARCH, "fix": "search"}
    return Data(brief_id, "notice", f"{brief_id}-no-search", data)


class _BriefTruth:
    """The truth checks: what the Brief did, and the Lead's reply against ONE's records."""

    # The truth checks (engine.truth) ---------------------------------------------------------

    def _did(self) -> truth.Brief:
        """What this Brief did, from its runs' tool results: the facts a reply is checked on."""
        did = truth.Brief(tool_names=frozenset(n for n in REGISTRY if "_" in n))
        for run in self.store.runs(self.brief_id):
            spec = run["spec"]
            if spec.role == "specialist":
                did.specialists += (spec.name["en"], spec.name["ar"])
            if not run["history"]:
                continue
            for name, ok, said in outcomes(run["history"]):
                if ok:
                    did.done.add(name)
                    did.refused.pop(name, None)
                else:
                    did.refused[name] = self._refusal(name, said)
            for name, text in agents.tool_returns(run["history"]):
                tool = REGISTRY.get(name)
                if tool is None or text.startswith(NOT_DONE):
                    continue
                if tool.writes and (name not in team.TEAM_TOOLS or name == "make_deliverable"):
                    did.writes += 1
                if name in ("deliverable_create", "make_deliverable", "boq_price_from_sheet"):
                    did.deliverables += 1
                did.shown = did.shown or name == view.TOOL
                did.understood = did.understood or name == understand.TOOL
                if name == "add_source":
                    try:
                        found = json.loads(text)
                    except ValueError:
                        continue
                    if isinstance(found, dict) and found.get("covers") == "supply":
                        did.supply_only += (str(found.get("title", "")),)
            if not did.understood:
                refused = _refused(run["history"], understand.TOOL)
                did.understood_refused = refused or did.understood_refused
        if self.place.rec is not None and "deliverable_create" in did.done:
            did.item_rows = self._item_rows()
        return did

    def wrote(self, tool: str) -> None:
        """A tool call wrote to the records (engine.tools.call); team chatter is no change."""
        if tool not in team.TEAM_TOOLS or tool == "make_deliverable":
            self.changes += 1

    def _stopped_line(self) -> Text:
        """The engineer's Stop: what this Brief's records show it changed before it stopped (its
        saved runs, and the writes since their last save)."""
        try:
            writes = max(self._did().writes, self.changes)
        except Exception:  # its records cannot be read: the plain line, never a guess
            log.exception("brief %s: what it changed", self.brief_id)
            return copy.STOPPED
        if not writes:
            return copy.STOPPED_NOTHING
        return copy.fill(copy.STOPPED_CHANGED, changes=copy.counted(writes, copy.CHANGES))

    def _refusal(self, tool: str, said: str) -> Text:
        """Why a call of `tool` was refused, in the engineer's words: as the tool said it, or the
        words of ONE's own text in the refusal, or a plain line naming the step."""
        found = self.refusals.get(tool) or copy.words_for(said)
        if found is not None:
            return {lang: words.rstrip() for lang, words in found.items()}
        step = copy.tool_step(tool)
        step = step if "{" not in step["en"] else copy.TOOL_STEP
        return copy.fill(copy.REFUSED_STEP, step=step)

    def _item_rows(self) -> int | None:
        """The item rows in the Sheets this Brief made, and the numbers it set or added on items
        through suggested changes; None when it made no Sheet."""
        made: list[str] = []
        changes: list[str] = []
        for run in self.store.runs(self.brief_id):
            if not run["history"]:
                continue
            for name, text in agents.tool_returns(run["history"]):
                try:
                    out = json.loads(text)
                except ValueError:
                    continue
                if not isinstance(out, dict):
                    continue
                if name in {"deliverable_create", "boq_price_from_sheet"} and isinstance(
                    out.get("id"), str
                ):
                    made.append(out["id"])
                elif name == "deliverable_propose" and isinstance(out.get("change_ids"), list):
                    changes += [c for c in out["change_ids"] if isinstance(c, str)]
        try:
            with self.place.rec.read() as c:
                made = [
                    d
                    for d in made
                    if c.execute(
                        "SELECT 1 FROM deliverables WHERE id = ? AND kind = 'sheet'", (d,)
                    ).fetchone()
                ]
                if not made:
                    return None
                rows = 0
                for d in made:
                    (n,) = c.execute(
                        "SELECT count(*) FROM parts WHERE deliverable_id = ? AND kind = 'item'"
                        " AND valid_until IS NULL AND removed = 0",
                        (d,),
                    ).fetchone()
                    rows += n
                for change in changes:
                    row = c.execute("SELECT op FROM changes WHERE id = ?", (change,)).fetchone()
                    op = json.loads(row[0]).get("op") if row else None
                    rows += op in ("set_number", "add_item_row")
        except Exception:  # noqa: BLE001 - an older file: the check is left out, never the reply
            return 1
        return rows

    def read_repeat(self, name: str, args: dict) -> bool:
        """Deduplicate only successfully answered full reads within this Brief."""
        expected = REGISTRY[name].args.model_validate(args).model_dump(mode="json")
        runs = self.store.runs(self.brief_id)
        previous_repeats = sum(
            result == copy.READ_ALREADY["en"]
            for run in runs
            if run["history"]
            for tool, result in agents.tool_returns(run["history"])
            if tool in {"files_read", "read_chunk"}
        )
        for run in runs:
            messages = _load(run["history"])
            answered = {
                p.tool_call_id
                for m in messages
                if isinstance(m, ModelRequest)
                for p in m.parts
                if isinstance(p, ToolReturnPart)
                and p.outcome == "success"
                and not str(p.content).startswith(NOT_DONE)
            }
            for m in messages:
                if not isinstance(m, ModelResponse):
                    continue
                for call in _calls(m):
                    if call.tool_name != name or call.tool_call_id not in answered:
                        continue
                    try:
                        old = REGISTRY[name].args.model_validate(call.args_as_dict())
                    except ValueError:
                        continue
                    if old.model_dump(mode="json") == expected:
                        self.read_repeats = max(self.read_repeats, previous_repeats) + 1
                        return True
        return False

    def _read_returns(self) -> list[tuple[str, str]]:
        return [
            (name, result)
            for run in self.store.runs(self.brief_id)
            if run["history"]
            for name, result in agents.tool_returns(run["history"])
            if name in {"files_read", "read_chunk", "search_records"}
        ]

    def _reply_problems(self, output: str) -> list[truth.Problem]:
        rec = self.place.rec
        found = truth.reply_problems(
            output,
            cov=truth.coverage(rec) if rec is not None else None,
            did=self._did(),
            engineer_text=self.text,
            understand_brief=self.instruction == understand.INSTRUCTION,
        )
        if rec is not None:
            searched = any(
                name == "search_records" and ok
                for run in self.store.runs(self.brief_id)
                for name, ok, _ in outcomes(run["history"])
            )
            found += truth.tender_search_problem(output, self.text, searched, rec=rec)
        if rec is not None:  # each number at the row or page the reply cites for it
            found += truth.reading_problems(output, self._read_returns())
            found += truth.unread_citations(output, self._read_returns(), rec=rec)
            with rec.read() as c:
                found += truth.miscited(c, output)
                ids = []
                for run in self.store.runs(self.brief_id):
                    for name, result in (
                        agents.tool_returns(run["history"]) if run["history"] else ()
                    ):
                        if name not in {
                            "deliverable_create",
                            "deliverable_read",
                            "deliverable_propose",
                        }:
                            continue
                        try:
                            data = json.loads(result)
                        except ValueError:
                            continue
                        if isinstance(data, dict) and isinstance(data.get("id"), str):
                            ids.append(data["id"])
                found += truth.document_claims(c, output, ids)
                if re.search(
                    r"خطاب|\b(?:bid|covering|tender) letter\b", self.text + " " + output, re.I
                ):
                    wrong = truth.letter_problems(
                        c,
                        output,
                        day=truth.today(self.engine.clock()),
                        has_total=False,
                        said=self.text,
                    )
                    marked = _marked(rec, output, self.results())
                    if marked:
                        wrong.append(
                            "The letter has numbers with no source in this Brief: "
                            + ", ".join(marked)
                            + ". Read the project records and calculate totals before answering; "
                            "write the letter in a Document with sourced number references."
                        )
                    if wrong:
                        found.append(
                            truth.Problem("letter", " ".join(wrong), copy.TRUTH_LETTER_MONEY)
                        )
        return found

    async def _truthful(self, output: Any) -> Any:
        """The Lead's answer against ONE's records, before the engineer relies on it. Once per
        Brief, what it says that the records do not show (a blank for a value, a promise of work
        that is not running, more priced items than there are, a change never made) goes back
        for the Lead to fix, and the screen drops the words it replaces (`data-redo`)."""
        if not isinstance(output, str) or self.truth_retried:
            return output
        problems = await asyncio.to_thread(self._reply_problems, output)
        if not problems:
            return output
        self.truth_retried = True
        cut = {"from": self.answer_from, "to": self.said}
        self.redo_cleared = self.answer_from == 0
        self.emit(Data(self.brief_id, "redo", self.brief_id, cut))
        raise ModelRetry(
            "ONE checked your answer against its records before the engineer reads it. Answer "
            "again, fixing this:\n- " + "\n- ".join(p.fix for p in problems)
        )

    async def _facts(self, output: str) -> None:
        """The facts beside the reply, from ONE's own records (`data-facts`): the BOQ's real
        coverage and its Deliverables, with a flag for each claim the records do not show; and
        the way to set up web search when the reply says ONE could not search."""
        problems = await asyncio.to_thread(self._reply_problems, output)
        rec = self.place.rec
        cov = await asyncio.to_thread(truth.coverage, rec) if rec is not None else None
        flags = [p.flag for p in problems if p.flag]
        did = self._did()
        worked = did.writes or truth.PRICED.search(output)
        found = truth.facts(cov, flags) if flags or worked else None
        no_search = bool(
            rec is not None and _NO_SEARCH_SAID.search(output) and self._search_line() is not None
        )
        if found is not None:
            self.emit(Data(self.brief_id, "facts", self.brief_id, found))
        if no_search:
            self.emit(_no_search_notice(self.brief_id))
        self.worklog.truth = (self.worklog.truth or {}) | {"facts": found, "no_search": no_search}


def _marked(rec: Records | None, reply: str, results: list[str]) -> list[str]:
    """The numbers of a reply with no source: none of the Brief's tools gave them, no item's
    own words have them (a size, «طوب 25 سم»), and no place the reply cites has them (a number
    read from a cited page carries that source: the bid security on page 26, 6 Nov 2026)."""
    marked = numbers_guard.unsourced(reply, numbers_guard.known_values(results))
    if marked and rec is not None:
        marked = numbers_guard.described(reply, marked, _descriptions(rec))
    return marked
