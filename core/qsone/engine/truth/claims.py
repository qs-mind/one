"""Claims in a reply against the records: priced, made, changed, done, promised, ready."""

import json
import re

from qsone import copy
from qsone.engine.truth.problem import Problem
from qsone.engine.truth.records import Brief, Coverage
from qsone.engine.truth.words import (
    _ALL,
    _CHANGED,
    _DELIVERABLE_READY,
    _DONE,
    _LABOUR_CLAIM,
    _OFFER,
    _PROMISE,
    PRICED,
    _integers,
    _sentences,
)


def overclaim(text: str, cov: Coverage | None, did: Brief) -> list[Problem]:
    """Claims of priced items, a Deliverable or a change that the records do not show."""
    found: list[Problem] = []
    if cov is not None and cov.items:
        for s in _sentences(text):
            if not (PRICED.search(s) and _DONE.search(s)):
                continue
            counts = [n for n in _integers(s) if cov.priced < n <= cov.items and n > 1]
            if _ALL.search(s) and cov.priced < cov.items or counts:
                said = counts[0] if counts else cov.items
                flag = copy.fill(
                    copy.TRUTH_OVERCLAIM_PRICED,
                    said=str(said),
                    priced=str(cov.priced),
                    items=str(cov.items),
                )
                fix = (
                    f"Your reply says {said} items are priced; ONE's records show "
                    f"{cov.priced} of {cov.items} items with a rate. Say only what the records "
                    "show: how many are priced and what is left."
                )
                found.append(Problem("priced", fix, flag))
                break
    if cov is not None and not did.deliverables and not cov.deliverables:
        if any(_DELIVERABLE_READY.search(s) for s in _sentences(text)):
            found.append(
                Problem(
                    "deliverable",
                    "Your reply says a Deliverable is ready, but none exists in this project. "
                    "Make it with deliverable_create, or say plainly that there is none yet.",
                    copy.TRUTH_NO_DELIVERABLE,
                )
            )
    if not did.writes and any(_CHANGED.search(s) for s in _sentences(text)):
        found.append(
            Problem(
                "changed",
                "Your reply says something was changed or set, but nothing was recorded or "
                "changed in this Brief. Make the change with the tools, or say plainly that "
                "nothing changed yet and what would change it.",
                copy.TRUTH_NOTHING_CHANGED,
            )
        )
    if did.supply_only and _LABOUR_CLAIM.search(text or ""):
        found.append(
            Problem(
                "labour",
                "Your reply says a rate includes labour or installation, but the quote it cites "
                f"({', '.join(did.supply_only)}) is supply only. Say what the rate includes, "
                "and build labour in with calculate from another source.",
                copy.fill(copy.TRUTH_SUPPLY_ONLY, quote=", ".join(did.supply_only)),
            )
        )
    return found


# Claims of done work, each with the tools that do it: «استوردت البنود» with 0 items imported (the
# import was refused), «أضفت البنود» after deliverable_propose was refused (6 Nov 2026).
_IMPORTED = re.compile(
    r"استورد(?:ت|نا)\b|اتستورد|تم\s+(?:ال)?استيراد|\b(?:i(?:'ve| have)?\s+)?imported\b", re.I
)
_ADDED = re.compile(
    r"(?:^|[\s«(])(?:أ|ا)?ضف(?:ت|نا)\b|اتضاف(?:ت)?\b|تم[ّ]?\s+(?:إضافة|اضافة|تسجيل|إدراج|ادراج)"
    r"|سج[ّ]?ل(?:ت|نا)\b|اتسج[ّ]?ل(?:ت)?\b|حط[ّ]?(?:يت|ينا)\b"
    r"|\b(?:i(?:'ve| have)?\s+)?(?:added|recorded|inserted)\b|\bhave been (?:added|recorded)\b",
    re.I,
)
_PRICED_DONE = re.compile(
    # first person only: «اتسعّر 8 بنود من 325» reports the project, not this Brief's work
    r"تم\s+(?:وضع|تسعير)|سع[ّ]?ر(?:ت|نا)\b|\bi(?:'ve| have)?\s+priced\b",
    re.I,
)
# A sentence that says it was not done is no claim: «ماقدرتش أضيف», "could not import".
_NOT = re.compile(
    r"(?<![؀-ۿ])ما?[؀-ۿ]{2,}ش(?![؀-ۿ])|(?<![؀-ۿ])(?:مش|لم|لن|لا|ماتم|رفض\w*|مفيش)(?![؀-ۿ])"
    r"|\b(?:not|no|never|couldn'?t|cannot|can'?t|unable|failed|refused|wasn'?t|didn'?t)\b",
    re.I,
)
_CLAIMS = (  # (words, the tools that do it, what it is in the engineer's words)
    (_IMPORTED, frozenset({"boq_import"}), copy.CLAIM_IMPORT),
    (
        _ADDED,
        frozenset(
            {"deliverable_create", "deliverable_propose", "make_deliverable", "record_number",
             "add_item", "add_source", "correct_number", "boq_import", "note_lesson"}
        ),
        copy.CLAIM_ADD,
    ),
    (
        _PRICED_DONE,
        frozenset(
            {"record_number", "correct_number", "deliverable_create", "deliverable_propose",
             "make_deliverable", "calculate", "prices_propose", "boq_price_from_sheet"}
        ),
        copy.CLAIM_PRICED,
    ),
)  # fmt: skip


def undone(text: str, cov: Coverage | None, did: Brief) -> list[Problem]:
    """Claims of work done (imported, added, priced) that this Brief's tool calls do not show:
    none of the tools that do it went through, or one was refused. A refusal's reason is in the
    engineer's flag, in their words. A Deliverable this Brief made that holds no item is no
    pricing."""
    found: list[Problem] = []
    seen: set[str] = set()
    for s in _sentences(text):
        if _NOT.search(s):
            continue
        for words, tools, what in _CLAIMS:
            if what["en"] in seen or not words.search(s) or did.done & tools:
                continue
            refused = [t for t in sorted(tools) if t in did.refused]
            if not refused and (did.writes or (words is _IMPORTED and cov and cov.items)):
                continue  # something else was done, or an earlier Brief imported
            seen.add(what["en"])
            if refused:
                why = did.refused[refused[0]]
                fix = (
                    f"Your reply says it was done («{s[:120]}»), but ONE refused {refused[0]}: "
                    f"{why['en']} Nothing was done by it. Fix the call and make it again, or tell "
                    "the engineer plainly that it was not done, why, and what is needed."
                )
                found.append(Problem("refused", fix, copy.fill(copy.TRUTH_REFUSED, why=why)))
            else:
                fix = (
                    f"Your reply says it was done («{s[:120]}»), but no tool did it in this Brief. "
                    "Do it with the tools now, or say plainly that it is not done yet."
                )
                found.append(Problem("undone", fix, copy.fill(copy.TRUTH_NOT_DONE, what=what)))
    if did.item_rows == 0 and "record_number" not in did.done:
        if any(PRICED.search(s) and not _NOT.search(s) for s in _sentences(text)):
            found.append(
                Problem(
                    "empty",
                    "Your reply speaks of priced items, but the Deliverable you made has no item "
                    "rows (only headings). Add the items with their numbers (rows of item_id, or "
                    "deliverable_propose), or say plainly that nothing is priced yet.",
                    copy.TRUTH_EMPTY_DELIVERABLE,
                )
            )
    return found


# Work said to be under way or about to start when nothing ran: «بدأت في العمل على نسخة جديدة
# … دلوقتي، أنا بجهز المسودة … هل حابب أبعتلك الجدول؟» after 3 s and no tool (6 Nov 2026).
_UNDER_WAY = re.compile(
    r"(?<![؀-ۿ])(?:بدأت|بدات|ابتديت)\s+(?:في|ب|أ|ا)|(?<![؀-ۿ])(?:بجه[ّ]?ز|بحض[ّ]?ر|بشتغل|بنشتغل"
    r"|بنجه[ّ]?ز|بسعّر|بطابق)(?![؀-ۿ])|جار[يٍ]\s|(?<![؀-ۿ])ه(?:قوم|بدأ|سع[ّ]?ر|طابق|حسب"
    r"|خلص|عرضهولك|جه[ّ]?ز|بعت|بلغ|كم[ّ]?ل|ضيف|راجع|حض[ّ]?ر|سج[ّ]?ل|عمل|ربط|نف[ّ]?ذ)\w*"
    r"|\b(?:i(?:'ve| have) started|i am (?:now )?(?:preparing|working|building|pricing)"
    r"|i am going to|سأقوم|i'm (?:now )?(?:preparing|working|building|pricing)"
    r"|i will|i'll|starting now)\b",
    re.I,
)
# Work that waits on the engineer is no promise: «لو بعتلي العرض هسعّره», "once you send it".
_CONDITION = re.compile(
    r"(?<![؀-ۿ])(?:لو|إذا|اذا|أول\s+ما|اول\s+ما|لما|بعد\s+ما)(?![؀-ۿ])"
    r"|\b(?:if|once|when|after you)\b",
    re.I,
)


def promise(text: str, did: Brief | None = None) -> str | None:
    """The promise a reply ends on (work said to be under way, or about to start), or None. An
    offer ("if you want, I'll …", a question) is not a promise, unless `did` shows that the
    Brief wrote nothing and the reply says work has begun or will be done: then the first such
    words are the promise, whatever the reply ends on."""
    if did is not None and not did.writes:
        for s in _sentences(text):
            if _UNDER_WAY.search(s) and not _CONDITION.search(s):
                return s
    if did is not None:
        for s in _sentences(text):
            if re.search(r"هخلص|هعرضهولك|سأقوم|i am going to", s, re.I) and not _CONDITION.search(
                s
            ):
                return s
    tail = _sentences(text)[-2:]
    for s in reversed(tail):
        if _OFFER.search(s):
            return None
        if _PROMISE.search(s):
            return s
    return None


def document_claims(conn, text: str, ids: list[str]) -> list[Problem]:
    """Ready means written content, not an empty Document shell or blank paragraph."""
    if not any(_DELIVERABLE_READY.search(s) and not _NOT.search(s) for s in _sentences(text)):
        return []
    docs = conn.execute(
        "SELECT id, title, variant FROM deliverables WHERE kind = 'document'"
        " ORDER BY updated_at DESC, rowid DESC"
    ).fetchall()
    selected = [d for d in docs if d[0] in ids or d[1] in text]
    if not selected and re.search(r"خطاب|\bletter\b", text, re.I):
        selected = [d for d in docs if d[2] == "letter"][:1]
    elif not selected and re.search(r"مستند|\bdocument\b", text, re.I):
        selected = docs[:1]
    for doc, title, _variant in selected:
        nodes = conn.execute(
            "SELECT node FROM parts WHERE deliverable_id = ? AND kind = 'block' "
            "AND valid_until IS NULL AND removed = 0",
            (doc,),
        ).fetchall()
        if not any(_has_content(json.loads(node)) for (node,) in nodes):
            return [
                Problem(
                    "empty_document",
                    f"The document «{title}» is empty, despite your claim that it is ready. "
                    "Write its blocks with deliverable_propose, or say plainly it is still empty.",
                    copy.TRUTH_EMPTY_DOCUMENT,
                )
            ]
    return []


def _has_content(node) -> bool:
    if isinstance(node, dict):
        if node.get("type") in ("num", "cell"):
            return True
        if isinstance(node.get("text"), str) and node["text"].strip():
            return True
        return any(_has_content(v) for k, v in node.items() if k != "text")
    return isinstance(node, list) and any(_has_content(v) for v in node)
