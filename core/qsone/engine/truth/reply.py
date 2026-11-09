"""The final reply: everything the core sends back once, and the facts line beside it."""

import re

from qsone import copy
from qsone.engine import numbers_guard
from qsone.engine.truth.blanks import placeholders
from qsone.engine.truth.claims import overclaim, promise, undone
from qsone.engine.truth.cleaning import has_json
from qsone.engine.truth.problem import Problem
from qsone.engine.truth.records import Brief, Coverage
from qsone.engine.truth.words import (
    _ASK_ENGINEER,
    _BRACKETED_ENGLISH,
    _CARD,
    _TABLE_ROW,
    _TO_TEAM,
    arabic,
)

_CONTRACT = re.compile(
    r"محتجز|استقطاع|غرامة|تأخير|سريان|صلاحية|دفعة|دفعه|تأمين|شروط العقد"
    r"|\b(?:retention|advance|repayment|delay|validity|bid security|payment|contract)\b",
    re.I,
)


def reply_problems(
    text: str,
    *,
    cov: Coverage | None,
    did: Brief,
    engineer_text: str,
    understand_brief: bool = False,
) -> list[Problem]:
    """Everything in a final reply the core sends back once for the model to fix."""
    found: list[Problem] = []
    if (
        cov is not None
        and _CONTRACT.search(text)
        and (numbers_guard.numbers_in(text) or re.search(r"[0-9٠-٩]+\s*[%٪]", text))
    ):
        if not did.done.intersection({"files_read", "search_records", "read_chunk"}):
            found.append(
                Problem(
                    "contract_unread",
                    "Contract values were stated without a successful files_read/search step "
                    "in this Brief. "
                    "Search the tender by words and meaning, read the top pages, "
                    "and cite only values "
                    "read on the cited page. If not found, say so without remembered figures.",
                    copy.TRUTH_CONTRACT_UNREAD,
                )
            )
    if has_json(text):
        found.append(
            Problem(
                "json",
                "Your reply has JSON or ONE's record ids in it. The engineer reads words: a view "
                "you showed is on the screen already. Answer in plain words, with no JSON, no "
                "ids and no copy of a view.",
            )
        )
    blanks = placeholders(text)
    if blanks:
        found.append(
            Problem(
                "placeholder",
                f"Your reply has blanks left for values: {', '.join(blanks)}. Fill each from "
                "ONE's records (ledger_numbers, deliverable_read) or say plainly that the value "
                "is missing. Never send a bracketed placeholder.",
                copy.fill(copy.TRUTH_PLACEHOLDER, blanks=copy.listed(blanks)),
            )
        )
    if (
        re.search(r"\bimport\b|استورد", engineer_text, re.I)
        and not (cov and cov.items)
        and "boq_import" not in did.done
        and re.search(r"confirm|proceed|shall I|تأكيد|أبدأ|ابدأ|اوافق|توافق", text, re.I)
    ):
        found.append(
            Problem(
                "import_card",
                "The engineer already requested import. Call boq_preview then boq_import "
                "now: boq_import shows ONE's rows card for column approval. "
                "Never ask for plain-text "
                "confirmation instead of the rows card. If the file is missing, say that plainly.",
            )
        )
    said = promise(text, did)
    if said is not None:
        found.append(
            Problem(
                "promise",
                f"Your reply ends on a promise («{said}»), but nothing runs once you answer: "
                "the Brief ends with your reply. Do the work now with your tools, or say plainly "
                "what is done and what is left for the engineer to ask next.",
                copy.TRUTH_PROMISE,
            )
        )
    found += overclaim(text, cov, did)
    kinds = {p.kind for p in found}
    found += [p for p in undone(text, cov, did) if not (p.kind == "undone" and "changed" in kinds)]
    if understand_brief and not did.understood and _CARD.search(text or ""):
        why = f" It refused: {did.understood_refused}" if did.understood_refused else ""
        found.append(
            Problem(
                "card",
                "Your reply speaks of the «I understood this» card, but it was not saved, so "
                f"the engineer sees no card.{why} Fix it and call understood again, or tell the "
                "engineer plainly that the card could not be saved and why.",
                copy.TRUTH_NO_CARD,
            )
        )
    if (did.specialists and _TO_TEAM.search(text or "")) or _ASK_ENGINEER.search(text or ""):
        found.append(
            Problem(
                "audience",
                "Your reply goes to the engineer, not to a specialist. Words for the team go "
                "through delegate or send_message; tell the engineer what was done and what "
                "is left.",
            )
        )
    named = sorted(n for n in did.tool_names if re.search(rf"\b{re.escape(n)}\b", text or ""))
    if named:
        found.append(
            Problem(
                "tool",
                f"Do not name ONE's tools to the engineer ({', '.join(named)}); say in plain "
                "words what ONE did or could not do.",
            )
        )
    if arabic(engineer_text) and arabic(text) and _BRACKETED_ENGLISH.search(text or ""):
        found.append(
            Problem(
                "english",
                "Replace the answer silently; no apology or mention of language/retry. "
                "Write the Arabic reply without English words in brackets (not «مستند "
                "(Deliverable)», just «مستند»), in the engineer's own dialect.",
            )
        )
    rows = _TABLE_ROW.findall(text or "")
    if did.shown and len(rows) >= 3 and numbers_guard.numbers_in("\n".join(rows)):
        found.append(
            Problem(
                "table_twice",
                "Your reply types a table of numbers beside the view you showed, so the engineer "
                "sees it twice. Leave the table to the view; say in words what it shows.",
            )
        )
    if not did.shown and len(rows) >= 3 and numbers_guard.numbers_in("\n".join(rows)):
        found.append(
            Problem(
                "table",
                "Show a table of numbers with show, each figure a reference to a ledger number "
                "(top items by cost: read the Deliverable or ledger_numbers, then show), never "
                "as typed numbers in the reply.",
            )
        )
    return found


def facts(cov: Coverage | None, flags: list[dict]) -> dict | None:
    """The line beside a Brief's reply, from the records (`data-facts`): {"text", "flags"}."""
    if cov is None or not cov.items:
        return {"text": None, "flags": flags} if flags else None
    made = (
        copy.TRUTH_NO_DELIVERABLE_YET
        if not cov.deliverables
        else copy.fill(copy.TRUTH_DELIVERABLES, n=copy.counted(cov.deliverables, DELIVERABLES))
    )
    # the client's own rates are not ONE's pricing: said apart, never read as ONE's work
    items = copy.counted(cov.items, copy.ITEMS)
    if cov.client:
        items = copy.fill(copy.TRUTH_CLIENT_RATES, items=items, n=str(cov.client))
    text = copy.fill(
        copy.TRUTH_COVERAGE, items=items, priced=str(cov.priced - cov.client), made=made,
    )  # fmt: skip
    return {"text": text, "flags": flags}


DELIVERABLES = copy.Noun(
    en={"one": "1 Deliverable", "other": "{n} Deliverables"},
    ar={"one": "مخرج واحد", "two": "مخرجين", "few": "{n} مخرجات", "other": "{n} مخرج"},
)
