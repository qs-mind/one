"""Truth checks: what a reply, a Deliverable or a letter says, against ONE's own records.

A check in code beats a sentence in a prompt. A weak model wrote «تم الانتهاء من تسعير كافة
بنود المقايسة» over 8 priced items, letters with «[مبلغ إجمالي المقايسة]», a 60-day validity
the client's email puts at ٩٠ يوم, tomorrow's date, and rates cited to a quote that does not
have them. These functions find each of those from the records; the Brief Runner, the record
tools and the Deliverable tools refuse or flag with them. Pure reading: nothing here writes.

- `coverage`: the project's BOQ items, how many have a rate, its Deliverables.
- `reply_problems`: what a reply says that the records do not show, for one retry.
- `facts`: the line the core puts beside a Brief's reply, with its flags.
- `placeholders`, `letter_problems`: for Deliverables and letters.
- `value_at`: whether a number is where its source says it is.
- `today`: the date in Cairo, which the core gives every agent."""

import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from zoneinfo import ZoneInfo

from qsone import copy
from qsone.engine import numbers_guard
from qsone.records import boq

CAIRO = ZoneInfo("Africa/Cairo")


def today(now: datetime) -> date:
    """The day in Cairo at the moment `now` (an aware datetime)."""
    return now.astimezone(CAIRO).date()


def today_line(now: datetime) -> str:
    """The instruction line that gives every agent today's date, from the core's clock."""
    day = today(now)
    return (
        f"Today is {day.isoformat()} ({day.strftime('%A')}), Cairo time. A date you write "
        "(a letter's date, «today») is this one, never another."
    )


# Placeholders --------------------------------------------------------------------------------

# A bracketed blank a model left for a value: «[القيمة]», "[Client name]", {{total}}, <<date>>.
# Not a markdown link ("[the quote](…)"), a footnote ("[1]") or a checkbox ("[x]").
_PLACEHOLDER = re.compile(
    r"\[(?P<square>[^\[\]\n]{2,80})\](?!\()|\{\{(?P<curly>[^{}\n]{1,80})\}\}|<<(?P<angle>[^<>\n]{1,80})>>"
)
_LETTERS = re.compile(r"[^\W\d_]{2,}")


# A letter's field the engineer fills (bidder, tender number, signature): never invented.
FOR_ENGINEER = re.compile(r"يملأه\s+المهندس|يملاه\s+المهندس|to be filled by the engineer", re.I)
# ONE's insides are no blank: a record id, or a bit of JSON (the Brissa reply, 6 Nov 2026).
_ID = re.compile(r"\b[0-9a-f]{32}\b")
_JSONISH = re.compile(r"[{}\"]|^\s*\w+\s*:")


def placeholders(text: str) -> list[str]:
    """Each blank left for a value in `text`, as written, once."""
    found: list[str] = []
    for m in _PLACEHOLDER.finditer(text or ""):
        inside = m.group("square") or m.group("curly") or m.group("angle") or ""
        if _ID.search(inside) or (m.group("square") and _JSONISH.search(inside)):
            continue
        if FOR_ENGINEER.search(inside):  # a field marked for the engineer to fill is no blank
            continue
        if _LETTERS.search(inside) and m.group(0) not in found:
            found.append(m.group(0))
    return found


# JSON a model wrote into its reply: a fenced block, or an object or array on its own lines.
_JSON_FENCE = re.compile(r"```(?:json)?\s*\n?[\[{].*?```", re.S)
_JSON_START = re.compile(r'^\s*(?:\{\s*"|\[\s*[{"])')


def _json_lines(text: str) -> list[tuple[int, int]]:
    """The (start, end) line ranges of the JSON objects and arrays standing on their own lines."""
    lines = text.split("\n")
    out, i = [], 0
    while i < len(lines):
        if not _JSON_START.match(lines[i]):
            i += 1
            continue
        for j in range(i, min(len(lines), i + 200)):
            try:
                json.loads("\n".join(lines[i : j + 1]))
            except ValueError:
                continue
            out.append((i, j + 1))
            i = j
            break
        i += 1
    return out


def has_json(text: str) -> bool:
    return bool(_JSON_FENCE.search(text or "") or _json_lines(text or "") or _ID.search(text or ""))


def clean_reply(text: str, *, shown: bool) -> str:
    """The reply as the engineer reads it: no JSON, no record ids; and, when the Brief showed a
    view, no typed table of numbers beside it (the breakdown showed twice, 6 Nov 2026)."""
    out = _JSON_FENCE.sub("", text or "")
    lines = out.split("\n")
    for start, end in reversed(_json_lines(out)):
        del lines[start:end]
    if shown:
        table = [k for k, line in enumerate(lines) if _TABLE_ROW.fullmatch(line)]
        if len(table) >= 3 and numbers_guard.numbers_in("\n".join(lines[k] for k in table)):
            lines = [line for k, line in enumerate(lines) if k not in set(table)]
    out = _ID.sub("", "\n".join(lines))
    lang = "ar" if arabic(text) else "en"
    from qsone.engine.tools import REGISTRY

    for name in REGISTRY:
        if "_" in name:
            out = re.sub(rf"`?\b{re.escape(name)}\b`?", copy.REPLY_RECORDS[lang], out)
    out = re.sub(r"\bfile\s*(?:id|number)\s*[:：]?\s*(?:`\s*`|[)）])", "", out, flags=re.I)
    out = re.sub(r"ملف\s+رقم\s*[:：]?\s*(?:`\s*`|[)）])", "", out)
    out = re.sub(
        r"(?:The reply left blanks for values:\s*)?\[show\]",
        copy.REPLY_MISSING_VALUE[lang],
        out,
        flags=re.I,
    )
    out = re.sub(r"\b(?:source\s+)?ledger\b|سجل النظام", copy.REPLY_RECORDS[lang], out, flags=re.I)
    out = re.sub(r"أداة العرض\s*\(show\)|\(show\)", copy.REPLY_TABLE[lang], out, flags=re.I)
    out = _ASK_ENGINEER.sub(copy.REPLY_YOUR_QUOTES[lang], out)
    out = re.sub(r"[ \t]+\n", "\n", out)
    return re.sub(r"\n{3,}", "\n\n", out).strip()


def placeholders_in(value) -> list[str]:
    """The blanks in every text of a JSON-like value (a Deliverable's blocks, rows or title)."""
    found: list[str] = []

    def walk(v) -> None:
        if isinstance(v, str):
            found.extend(p for p in placeholders(v) if p not in found)
        elif isinstance(v, dict):
            for child in v.values():
                walk(child)
        elif isinstance(v, list | tuple):
            for child in v:
                walk(child)

    walk(value)
    return found


# The records ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class Coverage:
    items: int  # BOQ items in the project
    priced: int  # of them, with a current rate
    deliverables: int  # Deliverables in the project (beside the chat or drafts)
    client: int = 0  # of the priced, the rate the client's BOQ holds (a "boq" source): not ONE's


def coverage(rec) -> Coverage:
    """The project's BOQ items, how many have a current rate, and its Deliverables."""
    with rec.read() as c:
        (items,) = c.execute("SELECT count(*) FROM items WHERE kind = 'boq_item'").fetchone()
        (priced,) = c.execute(
            "SELECT count(DISTINCT i.id) FROM items i JOIN numbers n ON n.item_id = i.id"
            " WHERE i.kind = 'boq_item' AND n.name = 'rate' AND n.valid_until IS NULL"
        ).fetchone()
        (client,) = c.execute(
            "SELECT count(DISTINCT i.id) FROM items i JOIN numbers n ON n.item_id = i.id"
            " JOIN sources s ON s.id = n.source_id WHERE i.kind = 'boq_item' AND n.name = 'rate'"
            " AND n.valid_until IS NULL AND s.kind = 'boq'"
        ).fetchone()
        made = 0
        for table in ("deliverables", "deliverable_drafts"):
            try:
                (n,) = c.execute(f"SELECT count(*) FROM {table}").fetchone()
            except Exception:  # noqa: BLE001 - an older file has no such table
                n = 0
            made += n
    return Coverage(items, priced, made, client)


@dataclass
class Brief:
    """What one Brief did, from its own tool results: the facts its reply is checked against."""

    writes: int = 0  # write tool calls that went through
    deliverables: int = 0  # Deliverables it made
    shown: bool = False  # it showed a view (show)
    understood: bool = False  # the "I understood this" card was saved
    understood_refused: str | None = None  # the last refusal of understood, when not saved
    specialists: tuple[str, ...] = ()  # the names of the specialists it built (en and ar)
    supply_only: tuple[str, ...] = ()  # the titles of supply-only quotes it cited
    tool_names: frozenset[str] = field(default_factory=frozenset)
    done: set[str] = field(default_factory=set)  # the tools with a call that went through
    refused: dict[str, dict] = field(default_factory=dict)  # tool: why ({en, ar}), when its last
    # call was refused (a retry or a "not done") and none went through after
    item_rows: int | None = None  # item rows in the Deliverables it made, and numbers it set or
    # recorded on items; None when it made no Deliverable


# The reply -----------------------------------------------------------------------------------

_SENTENCE = re.compile(r"[^.!?؟\n]+[.!?؟]?")
# Pricing done: «تم الانتهاء من تسعير», «سعّرت», «اتسعّرت», "priced all", "finished pricing".
PRICED = re.compile(r"تسعير|سع[ّ]?ر(?:ت|نا)\b|اتسع[ّ]?ر|مسع[ّ]?ر|\bpric(?:ed|ing)\b", re.IGNORECASE)
_DONE = re.compile(
    r"تم\s+(?:ال)?انتهاء|انتهي(?:ت|نا)|خل[ّ]?ص(?:ت|نا)|اكتمل|تم\s+تسعير|سع[ّ]?ر(?:ت|نا)\b"
    r"|اتسع[ّ]?ر|\b(?:completed?|finished|done|have priced|priced)\b",
    re.IGNORECASE,
)
# Every item of the BOQ, not a section's: «كافة بنود المقايسة», «كل البنود», "all the items".
_ALL = re.compile(
    r"(?:كل|كاف[ةه]|جميع)\s+(?:ال)?بنود(?:\s+(?:ال)?(?:مقايس[ةه]|جدول(?:\s+الكميات)?))?"
    r"(?=\s*(?:$|[(\[«.،,؛:!؟]|[0-9٠-٩]|و|بال|ب\s))"
    r"|(?:ال)?مقايس[ةه]\s+(?:كل[هة]ا|بالكامل|كامل[ةه])"
    r"|\b(?:all|every one of)\s+(?:the\s+)?(?:[0-9,]+\s+)?(?:boq\s+)?items\b"
    r"(?!\s+(?:in|of|under)\s+(?:section|division|the\s+\w+\s+works))"
    r"|\bthe\s+(?:whole|entire|full)\s+boq\b",
    re.IGNORECASE,
)
_INTEGER = re.compile(r"(?<![\d.,٫])[0-9٠-٩]{1,6}(?![\d.,٫])")
_DELIVERABLE_READY = re.compile(
    r"(?:خطاب(?: العطاء)?|الخطاب|المخرج|المستند|مستند|مخرج|المقايس[ةه]\s+المسع[ّ]?ر[ةه]|deliverable)"
    r"[^.!?؟\n]{0,40}(?:جاهز|اتعمل|أنشأت|انشأت|عملت|خلص)"
    r"|(?:أنشأت|انشأت|قمت\s+بإنشاء|عملت|جهزت|جه[ّ]?زت)[^.!?؟\n]{0,30}(?:مستند|مخرج|deliverable)"
    r"|\b(?:deliverable|priced boq)\b[^.!?\n]{0,30}\b(?:is ready|ready|created|made)\b"
    r"|\b(?:created|made|prepared|wrote|written)\s+(?:the|a)\s+"
    r"(?:deliverable|priced boq|letter|document)\b"
    r"|\b(?:letter|document)\b[^.!?\n]{0,30}\b(?:ready|written|prepared)\b"
    r"|(?:تم\s+(?:تجهيز|كتابة|إعداد)|كتبت|جهزت)[^.!?؟\n]{0,30}(?:خطاب|مستند)",
    re.IGNORECASE,
)
# A change made: «تم تثبيت الأسعار», «عدّلت», «اتغيرت», "updated", "changed".
_CHANGED = re.compile(
    r"تم\s+(?:تثبيت|تعديل|تغيير|تحديث|استبدال|ضبط)|(?:عد[ّ]?لت|غي[ّ]?رت|ثب[ّ]?ت|حد[ّ]?ثت|ظبطت)\b"
    r"|\bات(?:عد[ّ]?ل|غي[ّ]?ر|ثب[ّ]?ت|حد[ّ]?ث)(?:ت)?\b"
    r"|\b(?:i(?:'ve| have)?\s+(?:updated|changed|set|fixed|replaced)|(?:has|have) been "
    r"(?:updated|changed|set|fixed|replaced))\b",
    re.IGNORECASE,
)
_CARD = re.compile(r"البطاق[ةه]|الكارت|بطاق[ةه]|كارت|\bcard\b", re.IGNORECASE)
# The end of a reply that says work goes on when nothing runs: «جاري التنفيذ…», «ثواني وهتكون».
_PROMISE = re.compile(
    r"\bجار[يٍ]?\s|\bه(?:ن)?(?:بدأ|كم[ّ]?ل|شتغل|بعت|رجع|ظبط|نض[ّ]?ف)\w*|\bسأ(?:قوم|بدأ|كمل|رسل|عمل)"
    r"|هخلص|هعرضهولك|سأقوم|\bi am going to\b|\bسوف\s|\bثواني\b|ثانية\s+واحدة"
    r"|\bلحظ(?:ة|ات)\b|دقايق\s+و|\bحال[اًا]+\s*$|بشتغل\s+على|\bبنشتغل"
    r"|\b(?:i will|i'll|we will|we'll|working on it|in progress|one moment|just a moment|"
    r"shortly|in a few (?:seconds|minutes)|let me now|starting now|will now)\b",
    re.IGNORECASE,
)
_OFFER = re.compile(
    r"لو\s+(?:عايز|عاوز|تحب|حابب|تحبي|حابة)|تحب\s+(?:إن|ان)|عايزني|\bif you (?:want|like|wish)|"
    r"\bshall i\b|\bdo you want\b|\bwould you like\b|[?؟]\s*$",
    re.IGNORECASE,
)
# Words for a specialist that ended up in the reply: «استمر يا بشمهندس، كمل تسعير… أنا متابع».
_ASK_ENGINEER = re.compile(
    r"(?:you may want to )?ask the engineer if they have received alternative offers", re.I
)
_TO_TEAM = re.compile(
    r"(?:^|[.!؟\n،,]\s*)(?:استمر|كم[ّ]?ل|ابدأ|خليك)\s+(?:يا|في|تسعير|الشغل|شغلك)"
    r"|أنا\s+متابع\s+معاك|انا\s+متابع\s+معاك|\b(?:keep going|carry on with|continue pricing|"
    r"i'?m following your work)\b",
    re.IGNORECASE,
)
_BRACKETED_ENGLISH = re.compile(r"[(（]\s*[A-Za-z][A-Za-z \-/]{1,40}\s*[)）]")
_TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$", re.M)
_ARABIC = re.compile(r"[؀-ۿ]")
_LATIN = re.compile(r"[A-Za-z]")
_LABOUR_CLAIM = re.compile(
    r"شامل(?:ة|اً|ا)?\s+(?:ال)?(?:مواد\s+و\s*ال)?(?:عمال[ةه]|مصنعي[ةه]|تركيب)"
    r"|\bincl(?:uding|\.)?\s+(?:materials and\s+)?(?:labou?r|installation)\b",
    re.IGNORECASE,
)


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE.findall(text or "") if s.strip()]


def _integers(sentence: str) -> list[int]:
    return [int(m.group().translate(_DIGITS)) for m in _INTEGER.finditer(sentence)]


_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


def arabic(text: str) -> bool:
    return len(_ARABIC.findall(text or "")) >= len(_LATIN.findall(text or ""))


@dataclass(frozen=True)
class Problem:
    """One thing a reply says that the records do not show. `fix` is English, for the model;
    `flag` is the engineer's line, {en, ar}, or None when only the model needs to hear it."""

    kind: str
    fix: str
    flag: dict | None = None


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


_CONTRACT = re.compile(
    r"محتجز|استقطاع|غرامة|تأخير|سريان|صلاحية|دفعة|دفعه|تأمين|شروط العقد"
    r"|\b(?:retention|advance|repayment|delay|validity|bid security|payment|contract)\b",
    re.I,
)


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


# Sources: is the number where its source says? ------------------------------------------------

_PLACE_KEYS = ("page", "sheet", "row", "line", "paragraph", "table", "layer")


def texts_at(conn, file_id: str, locator: dict) -> list[str] | None:
    """The file's text at `locator` (its passages there), or None when the locator names no
    place this check reads (a column only, a log id)."""
    place = {k: v for k, v in locator.items() if k in _PLACE_KEYS}
    if not place:
        return None
    if "sheet" in place:
        matched = boq.source_sheet(conn, file_id, place["sheet"])
        if matched is None:
            return []
        place["sheet"] = matched
    where = " AND ".join(f"json_extract(locator, '$.{k}') = ?" for k in place)
    rows = conn.execute(
        f"SELECT text FROM chunks WHERE file_id = ? AND {where} ORDER BY id",
        (file_id, *place.values()),
    ).fetchall()
    return [t for (t,) in rows]


def file_text(conn, file_id: str) -> str:
    return "\n".join(
        t for (t,) in conn.execute("SELECT text FROM chunks WHERE file_id = ?", (file_id,))
    )


def value_at(conn, source_id: str, value: str) -> tuple[bool, str, list[str]] | None:
    """Whether `value` is in the text its file source points at: (found, where in words, the
    numbers that place has). None when the source is not a place in a file, or the place has no
    text to read (a scanned page): nothing to check against."""
    row = conn.execute("SELECT file_id, locator, kind FROM sources WHERE id = ?", (source_id,))
    row = row.fetchone()
    if row is None or row[0] is None:
        return None
    file_id, locator, kind = row
    if kind in ("calculation", "sandbox", "web", "prices", "engineer", "connector"):
        return None
    return value_in(conn, file_id, json.loads(locator), value)


def value_in(conn, file_id: str, place: dict, value: str) -> tuple[bool, str, list[str]] | None:
    """`value_at` for a file and a place in it."""
    texts = texts_at(conn, file_id, place)
    if not texts:
        return None
    (name,) = conn.execute("SELECT name FROM files WHERE id = ?", (file_id,)).fetchone() or ("",)
    wanted = numbers_guard.known_values([value])
    have = numbers_guard.known_values(texts)
    where = ", ".join(f"{k} {place[k]}" for k in _PLACE_KEYS if k in place)
    shown = sorted(have, key=lambda v: (len(v), v))[:12]
    return bool(wanted) and wanted <= have, f"{name}, {where}", shown


# A number's unit: «0.2 %» lost "per day" (the delay damages, Brissa, 6 Nov 2026).
_PER_DAY = re.compile(
    r"\bper\s+(?:calendar\s+)?day\b|\bdaily\b|\ba\s+day\b|يومي[اًا]?|يوميا|عن\s+كل\s+يوم"
    r"|في\s+اليوم|لكل\s+يوم|كل\s+يوم|/\s*(?:day|يوم)",
    re.I,
)
_NEAR = 60  # characters after a number where its "per day" is written


def per_day(texts: list[str], value: str) -> bool:
    """Whether the texts write `value` as so much per day («0.2% of the price per day»)."""
    wanted = numbers_guard.known_values([value])
    for text in texts:
        for m in numbers_guard._ANY_NUMBER.finditer(text):
            if numbers_guard.known_values([m.group()]) != wanted:
                continue
            after = text[m.end() : m.end() + _NEAR]
            stop = re.search(r"[0-9٠-٩]", after)  # up to the next number
            if _PER_DAY.search(after[: stop.start()] if stop else after):
                return True
    return False


def says_per_day(text: str) -> bool:
    return bool(_PER_DAY.search(text or ""))


def per_day_at(conn, source_id: str, value: str) -> bool:
    """Whether the place a file source cites writes `value` as so much per day."""
    row = conn.execute("SELECT file_id, locator FROM sources WHERE id = ?", (source_id,))
    row = row.fetchone()
    if row is None or row[0] is None:
        return False
    return per_day(texts_at(conn, row[0], json.loads(row[1])) or [], value)


# Citations in a reply's words: is each number where the reply says it is? --------------------
#
# The real walk (6 Nov 2026): «السعر 12 جنيه/م3 (من شيت "تسعير"، صف 16)» for an item the BOQ does
# not have, ceramic 72 cited to row 18 (a different, empty item), the retention limit to page 59
# (it is on page 58); and the bid security «350,000 دولار … الصفحة: 26» marked "no source yet"
# although page 26 has it.

_Q = "\"'«»“”‘’"
_SHEET_ROW = re.compile(
    rf"(?:شيت|الشيت|ورق[ةه]|الورق[ةه]|sheet)\s*[:：]?\s*[{_Q}]?(?P<sheet>[^{_Q}\n،,()\[\]:]{{1,40}}?)"
    rf"[{_Q}]?\s*[،,]?\s*(?:في\s+)?(?:صف|الصف|سطر|row)\s*[:：]?\s*"
    r"(?P<rows>[0-9٠-٩]+(?:\s*(?:[/،,-]|و)\s*[0-9٠-٩]+)*)",
    re.I,
)
_ROW_SHEET = re.compile(  # "row 8 of sheet Electrical"
    rf"\brow\s*(?P<rows>[0-9]+(?:\s*[/,-]\s*[0-9]+)*)\s+(?:of|in|on)\s+(?:the\s+)?sheet\s*"
    rf"[{_Q}]?(?P<sheet>[^{_Q}\n,()\[\]:]{{1,40}}?)[{_Q}]?(?=[\s,.;)]|$)",
    re.I,
)
_PAGE = re.compile(
    r"(?<![؀-ۿ\w])(?:صفح[ةه]|الصفح[ةه]|ص\.|page|pages|pp?\.)\s*[:：]?\s*(?P<pages>[0-9٠-٩]+"
    r"(?:\s*(?:[/،,-]|و)\s*[0-9٠-٩]+)*)"
    r"|\((?:p|pp)\.?\s*(?P<pp>[0-9]+)",
    re.I,
)
_BARE_ROW = re.compile(
    r"(?<!\w)(?:row|الصف|صف|السطر|سطر)\s*[:：]?\s*(?P<rows>[0-9٠-٩]+)",
    re.I,
)
# A segment: a line, or a sentence of one; a decimal point («0.2», «17.1») never ends one.
_SEGMENT = re.compile(r"(?<=[!?؟])\s+|(?<=\.)(?![0-9])\s+|\n+")
_NUMS = re.compile(r"[0-9٠-٩]+")


@dataclass(frozen=True)
class Place:
    """A place a reply cites: a sheet's rows, or pages."""

    sheet: str | None
    rows: tuple[int, ...] = ()
    pages: tuple[int, ...] = ()
    file_name: str | None = None

    def words(self) -> dict:
        if self.sheet == "":
            rows = "/".join(map(str, self.rows))
            return {"en": f"row {rows}", "ar": f"صف {rows}"}
        if self.sheet is not None:
            rows = "/".join(map(str, self.rows))
            return {
                "en": f"sheet «{self.sheet}», row {rows}",
                "ar": f"شيت «{self.sheet}»، صف {rows}",
            }
        pages = "/".join(map(str, self.pages))
        return {"en": f"page {pages}", "ar": f"صفحة {pages}"}


def _numbers_of(text: str) -> tuple[int, ...]:
    return tuple(int(n.translate(_DIGITS)) for n in _NUMS.findall(text))


def citations(text: str) -> list[tuple[str, list[Place], list[tuple[str, str]]]]:
    """Citations beside values, above a list, or in an explicit trailing Source line.

    A new citation ends the previous scope. A trailing Source line applies only to the
    preceding uncited lines, never across another citation. Markdown emphasis is presentation.
    """
    segments = _SEGMENT.split(re.sub(r"[*`]+", "", text or ""))
    parsed = []
    for segment in segments:
        places: list[Place] = []
        blank = segment
        for pattern in (_SHEET_ROW, _ROW_SHEET):
            for m in pattern.finditer(segment):
                places.append(Place(m["sheet"].strip(), rows=_numbers_of(m["rows"])))
                blank = blank.replace(m[0], " " * len(m[0]))
        for m in _PAGE.finditer(blank):
            places.append(Place(None, pages=_numbers_of(m["pages"] or m["pp"])))
            blank = blank.replace(m[0], " " * len(m[0]))
        for m in _BARE_ROW.finditer(blank):
            places.append(Place("", rows=_numbers_of(m["rows"])))
            blank = blank.replace(m[0], " " * len(m[0]))
        filename = re.search(r"[\w-]+\.(?:pdf|xlsx?|docx?|csv)\b", segment, re.I)
        if filename:
            places = [Place(p.sheet, p.rows, p.pages, filename[0]) for p in places]
        parsed.append([segment, places, list(numbers_guard._counted(blank))])
    active = []
    pending = []
    for entry in parsed:
        segment, places, numbers = entry
        if places:
            if re.match(r"\s*(?:source|المصدر)\s*[:：]", segment, re.I):
                for prior in pending:
                    prior[1] = places
            active = places
            pending = []
        elif active:
            entry[1] = active
        else:
            pending.append(entry)
    return [(segment, places, numbers) for segment, places, numbers in parsed if places]


def _sheet_names(conn) -> dict[str, list[str]]:
    """{normalised name: [names as written]} of the current files' sheets."""
    from qsone.records.arabic import normalise

    rows = conn.execute(
        "SELECT DISTINCT json_extract(c.locator, '$.sheet') FROM chunks c JOIN files f"
        " ON f.id = c.file_id WHERE f.valid_until IS NULL"
        " AND json_extract(c.locator, '$.sheet') IS NOT NULL"
    ).fetchall()
    out: dict[str, list[str]] = {}
    for (name,) in rows:
        out.setdefault(normalise(str(name)), []).append(str(name))
    return out


def _sheet_of(conn, cited: str) -> list[str]:
    """The sheets a cited name names: the same name, trimmed and folded; else the one sheet whose
    name holds it, or that it holds."""
    from qsone.records.arabic import normalise

    names = _sheet_names(conn)
    key = normalise(cited)
    if key in names:
        return names[key]
    near = [n for k, ns in names.items() if key and (key in k or k in key) for n in ns]
    return near if len(near) == 1 else []


def place_text(conn, place: Place) -> list[str] | None:
    """The current files' text at `place`; None when no file has that place."""
    if place.sheet == "":
        rows = conn.execute(
            "SELECT c.text FROM chunks c JOIN files f ON f.id = c.file_id"
            " WHERE f.valid_until IS NULL AND json_extract(c.locator, '$.line') IN"
            " (SELECT value FROM json_each(?))",
            (json.dumps(list(place.rows)),),
        ).fetchall()
        return [t for (t,) in rows] or None
    if place.sheet is not None:
        sheets = _sheet_of(conn, place.sheet)
        if not sheets:
            return None
        rows = conn.execute(
            "SELECT c.text FROM chunks c JOIN files f ON f.id = c.file_id"
            " WHERE f.valid_until IS NULL AND json_extract(c.locator, '$.sheet') IN"
            " (SELECT value FROM json_each(?)) AND json_extract(c.locator, '$.row') IN"
            " (SELECT value FROM json_each(?))",
            (json.dumps(sheets), json.dumps(list(place.rows))),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT c.text FROM chunks c JOIN files f ON f.id = c.file_id"
            " WHERE f.valid_until IS NULL AND json_extract(c.locator, '$.page') IN"
            " (SELECT value FROM json_each(?))",
            (json.dumps(list(place.pages)),),
        ).fetchall()
    return [t for (t,) in rows] or None


_ITEM_CODE = re.compile(
    r"(?:(?<![؀-ۿ])(?:بند|البند)\s*(?:رقم\s*)?|\bitem\s+(?:no\.?\s*)?)"
    r"(?P<code>[0-9٠-٩A-Za-z][0-9٠-٩A-Za-z./-]*[0-9٠-٩A-Za-z]|[0-9٠-٩])",
    re.I,
)


def _tokens(text: str) -> set[str]:
    return set(re.split(r"[\s|،,:;()«»\"']+", text.translate(_DIGITS)))


def _item_codes(conn, segment: str) -> list[str]:
    """The client BOQ codes a segment names as items («بند 17», "item 03/02")."""
    named = [m["code"].translate(_DIGITS) for m in _ITEM_CODE.finditer(segment)]
    if not named:
        return []
    found = conn.execute(
        "SELECT code FROM items WHERE kind = 'boq_item' AND code IN"
        " (SELECT value FROM json_each(?))",
        (json.dumps(named),),
    ).fetchall()
    return sorted({c for (c,) in found})


def miscited(conn, text: str) -> list[Problem]:
    """Each number a reply gives at a cited place (a sheet's row, a page) that the place does not
    have, and each cited place no project file has. One Problem for the model, with a flag for
    the engineer for each of the first three."""
    wrong: list[tuple[str, dict]] = []  # (the model's line, the engineer's flag)
    for segment, places, numbers in citations(text):
        if not numbers:
            continue
        texts: list[str] = []
        missing = []
        for place in places:
            found = place_text(conn, place)
            if found is None:
                missing.append(place)
            else:
                texts += found
        if missing and not texts:
            for place in missing:
                where = place.words()
                line = f"«{segment[:100]}» cites {where['en']}, which no project file has."
                wrong.append((line, copy.fill(copy.TRUTH_NO_PLACE, place=where)))
            continue
        rows = [p for p in places if p.sheet is not None]
        for code in _item_codes(conn, segment) if rows else ():
            if not any(code in _tokens(t) for t in texts):  # the row of another item
                where = rows[0].words()
                line = (
                    f"«{segment[:100]}» prices item {code} from {where['en']}, which is not "
                    f"item {code}'s row."
                )
                wrong.append((line, copy.fill(copy.TRUTH_OTHER_ROW, code=code, place=where)))
        have = numbers_guard.known_values(texts)
        for written, value in numbers:
            if value in have and per_day(texts, value) and not says_per_day(segment):
                where = places[0].words()
                line = (
                    f"«{segment[:100]}» gives {written} without its unit: {where['en']} has it "
                    "per day. Keep the unit with the number."
                )
                wrong.append((line, copy.fill(copy.TRUTH_PER_DAY, value=written, place=where)))
                continue
            if value in have:
                continue
            where = (
                places[0].words()
                if len(places) == 1
                else copy.listed([p.words()["en"] for p in places])
            )
            shown = sorted(have, key=lambda v: (len(v), v))[:8]
            has = copy.listed(shown) if shown else copy.NO_NUMBERS
            line = f"«{segment[:100]}» gives {written} at {where['en']}, which has {has['en']}."
            flag = copy.fill(copy.TRUTH_MISCITED, value=written, place=where, have=has)
            wrong.append((line, flag))
    guide = (
        " Cite the row or page that has the number (search_records, read_chunk), or say plainly "
        "that ONE has no source for it. An item that is not in the BOQ is not priced as one."
    )
    return [
        Problem("cited", line + (guide if i == 0 else ""), flag)
        for i, (line, flag) in enumerate(wrong[:5])
    ]


def cited_values(conn, text: str) -> set[str]:
    """Every number at the places a reply cites (normalised): a number read from a cited page
    carries that source."""
    found: set[str] = set()
    for _, places, _ in citations(text):
        for place in places:
            found |= numbers_guard.known_values(place_text(conn, place) or [])
    return found


# Quotes: what they cover ----------------------------------------------------------------------

# Words that say a price covers labour or installation, in Arabic and English.
_INSTALL = re.compile(
    r"تركيب|مصنعي[ةه]|عمال[ةه]|توريد\s+و\s*تركيب|شامل(?:ة|اً)?\s+(?:ال)?(?:تركيب|مصنعي|عمال)"
    r"|\b(?:install(?:ation|ed)?|labou?r|fix(?:ing|ed)|erect(?:ion)?"
    r"|supply and (?:install|fix|lay))\b",
    re.IGNORECASE,
)
_SUPPLY_ITEM = re.compile(r"توريد(?!\s+و\s*تركيب)|\bsupply(?!\s+and)\b", re.IGNORECASE)


def covers_labour(text: str) -> bool:
    return bool(_INSTALL.search(text or ""))


def supply_only_item(description: str) -> bool:
    """A BOQ item that is supply only («توريد … فقط», "Supply of …"): a supply quote fits it."""
    return bool(_SUPPLY_ITEM.search(description or "")) and not covers_labour(description)


# Letters ---------------------------------------------------------------------------------------

_MONTHS = {
    **{m: i for i, m in enumerate(("يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو",
                                     "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"), 1)},
    **{"ابريل": 4, "اغسطس": 8, "اكتوبر": 10, "يونية": 6, "يولية": 7},
    **{m: i for i, m in enumerate(("january", "february", "march", "april", "may", "june", "july",
                                     "august", "september", "october", "november", "december"), 1)},
}  # fmt: skip
_MONTH_WORDS = "|".join(sorted(_MONTHS, key=len, reverse=True))
_D = "[0-9٠-٩]"
_DATE_WORDS = re.compile(rf"(?<!{_D})({_D}{{1,2}})\s+({_MONTH_WORDS})\s*،?\s*({_D}{{4}})", re.I)
_DATE_ISO = re.compile(rf"(?<!{_D})({_D}{{4}})-({_D}{{2}})-({_D}{{2}})(?!{_D})")
_DATE_SLASH = re.compile(rf"(?<!{_D})({_D}{{1,2}})/({_D}{{1,2}})/({_D}{{4}})(?!{_D})")


def _n(text: str) -> int:
    return int(text.translate(_DIGITS))


def dates_in(text: str) -> list[tuple[str, date]]:
    """Each date written in `text` (6 نوفمبر 2026, 2026-11-06, 06/11/2026), as written."""
    found: list[tuple[str, date]] = []
    for m in _DATE_WORDS.finditer(text or ""):
        try:
            found.append((m.group(0), date(_n(m[3]), _MONTHS[m[2].lower()], _n(m[1]))))
        except ValueError:
            continue
    for m in _DATE_ISO.finditer(text or ""):
        try:
            found.append((m.group(0), date(_n(m[1]), _n(m[2]), _n(m[3]))))
        except ValueError:
            continue
    for m in _DATE_SLASH.finditer(text or ""):
        try:
            found.append((m.group(0), date(_n(m[3]), _n(m[2]), _n(m[1]))))
        except ValueError:
            continue
    return found


# Terms a tender's files state, each found by its words and the number after them.
TERMS = {
    "validity": re.compile(
        r"(?:مد[ةه]\s+)?(?:سريان|صلاحي[ةه])(?:\s+(?:ال)?عرض)?|\bvalid(?:ity)?(?:\s+for)?\b", re.I
    ),
    "vat": re.compile(r"ضريب[ةه]\s+(?:ال)?قيم[ةه]\s+(?:ال)?مضاف[ةه]|\bvat\b", re.I),
    "retention": re.compile(r"(?:ال)?محتجزات|(?:ال)?استقطاع|\bretention\b", re.I),
}
# The unit each term's number takes: days for a validity, a percentage for VAT and retention.
_DAYS = r"(?:يوم|أيام|ايام|يوما|يوماً|days?)"
_PERCENT = r"(?:%|٪|في\s+المي[ةه]|percent)"
_TERM_UNIT = {"validity": _DAYS, "vat": _PERCENT, "retention": _PERCENT}


def _term_values(text: str, term: str) -> list[str]:
    """The numbers stated right after each mention of the term in `text`, on the same line and
    within 40 letters, with the term's unit."""
    number = re.compile(rf"({_D}+(?:[.٫]{_D}+)?)\s*{_TERM_UNIT[term]}", re.I)
    out: list[str] = []
    for m in TERMS[term].finditer(text or ""):
        window = text[m.end() : m.end() + 40].split("\n", 1)[0]
        found = number.search(window)
        if found:
            out += [v for v in numbers_guard.known_values([found.group(1)]) if v not in out]
    return out


def file_terms(conn) -> dict[str, list[tuple[str, str]]]:
    """{term: [(value, where in words)]} that the project's current files state."""
    found: dict[str, list[tuple[str, str]]] = {}
    rows = conn.execute(
        "SELECT f.name, c.locator, c.text FROM chunks c JOIN files f ON f.id = c.file_id"
        " WHERE f.valid_until IS NULL ORDER BY c.id"
    ).fetchall()
    for name, locator, text in rows:
        place = json.loads(locator)
        where = ", ".join(f"{k} {place[k]}" for k in _PLACE_KEYS if k in place)
        for term in TERMS:
            for value in _term_values(text, term):
                found.setdefault(term, []).append((value, f"{name}, {where}".rstrip(", ")))
    return found


def file_dates(conn) -> set[date]:
    """Every date the project's current files write."""
    rows = conn.execute(
        "SELECT c.text FROM chunks c JOIN files f ON f.id = c.file_id WHERE f.valid_until IS NULL"
    ).fetchall()
    return {d for (t,) in rows for _, d in dates_in(t)}


_TOTAL = re.compile(r"إجمالي|اجمالي|قيم[ةه]\s+العطاء|\btotal\b|\bsum\b", re.I)


def letter_problems(conn, text: str, *, day: date, has_total: bool, said: str = "") -> list[str]:
    """What a letter says against the project's files and today's date (English, for the model).
    A date the engineer wrote (`said`, the Brief's text) is theirs to use."""
    wrong: list[str] = []
    amounts = conn.execute(
        "SELECT value FROM numbers WHERE valid_until IS NULL AND currency IS NOT NULL"
    ).fetchall()
    known_amounts = numbers_guard.known_values([v for (v,) in amounts])
    for segment in re.split(r"[\n؛;]", text):
        for match in numbers_guard._ANY_NUMBER.finditer(segment):
            tail = segment[match.end() :].lstrip()
            before = segment[: match.start()]
            # Only monetary figures: a total label immediately before the number or a
            # currency immediately beside it. Days, percentages and dates are separate facts.
            currency = r"(?:جنيه|ريال|درهم|دولار|EGP|SAR|USD|AED|[$€£])"
            money = re.match(currency, tail, re.I) or re.search(currency + r"\s*$", before, re.I)
            total = re.search(
                r"(?:إجمالي|اجمالي|قيم[ةه] العطاء|total|sum)[^0-9٠-٩،,;\n]{0,25}$", before, re.I
            )
            if not (money or total) or re.match(r"%|٪|days?\b|يوم", tail, re.I):
                continue
            written = match.group()
            if written not in numbers_guard.numbers_in(segment):
                continue
            if numbers_guard.known_values([written]) - known_amounts:
                wrong.append(
                    f"The letter amount {written} is not in the project records. "
                    "Read the BOQ total from calculate and use its number reference; "
                    "if missing, use [يملأه المهندس: إجمالي العطاء]."
                )
    known_dates = file_dates(conn) | {d for _, d in dates_in(said)}
    for written, d in dates_in(text):
        if d != day and d not in known_dates:
            wrong.append(
                f"The date «{written}» is not today ({day.isoformat()}, Cairo) and no project "
                "file states it: date the letter today."
            )
    terms = file_terms(conn)
    for term in TERMS:
        stated = terms.get(term, [])
        said = _term_values(text, term)
        if stated and said:
            values = {v for v, _ in stated}
            for v in said:
                if v not in values:
                    places = "; ".join(f"{s} ({w})" for s, w in stated[:3])
                    wrong.append(
                        f"The letter's {term} {v} is not what the project's files state: "
                        f"{places}. Cite the file's term."
                    )
        elif stated and term == "vat" and (has_total or _TOTAL.search(text or "")):
            places = "; ".join(f"{s}% ({w})" for s, w in stated[:2])
            wrong.append(
                f"The project's files state VAT ({places}); the letter quotes a price and does "
                "not say whether VAT is in it. Say it, citing the file."
            )
        if term == "vat" and stated and has_total and said:
            if not (_VAT_AMOUNT.search(text or "") and _WITH_VAT.search(text or "")):
                wrong.append(
                    "A priced letter gives the VAT amount and the total with VAT beside the "
                    "total: each worked out with calculate (the total × the file's VAT rate, "
                    'cited to it) and put in as {"type": "num"}.'
                )
    if has_total:
        missing = [name for name, words in _BID_FIELDS if not words.search(text or "")]
        if missing:
            wrong.append(
                f"A priced letter has the bid fields: {', '.join(missing)}. ONE never invents "
                "them: write each as a field the engineer fills, e.g. «مقدم العطاء: [يملأه "
                'المهندس: اسم مقدم العطاء]» or "Bidder: [to be filled by the engineer]".'
            )
    return wrong


_VAT_AMOUNT = re.compile(r"قيم[ةه]\s+(?:ال)?ضريب[ةه]|مبلغ\s+(?:ال)?ضريب[ةه]|\bvat\s+amount\b", re.I)
_WITH_VAT = re.compile(
    r"شامل(?:ا|ًا|اً)?\s+(?:ال)?ضريب[ةه]|شامل(?:ة)?\s+ضريب[ةه]|\b(?:incl(?:uding|\.)?|with)\s+vat\b",
    re.I,
)
_BID_FIELDS = (
    (
        "bidder",
        re.compile(r"مقد[ّ]?م\s+العطاء|اسم\s+(?:الشركة|المقاول)|\b(?:bidder|tenderer)\b", re.I),
    ),
    (
        "tender number",
        re.compile(r"رقم\s+(?:المناقص[ةه]|العطاء|الممارس[ةه])|\btender\s+(?:no|number|ref)", re.I),
    ),
    ("signature", re.compile(r"التوقيع|توقيع|\bsignature\b|\bsigned\b", re.I)),
)


def read_passages(returns: list[tuple[str, str]]) -> list[tuple[str, dict, str]]:
    """Only text actually returned by full read tools, not search hits or files in storage.

    Parse the read tools' own locator lines. A continuation contributes only its returned
    lines; neither a requested page range nor a source footer proves the text was returned.
    """
    found = []
    decoder = json.JSONDecoder()
    for name, result in returns:
        if name not in {"files_read", "read_chunk"}:
            continue
        file, locator, lines, file_name = None, None, [], None

        def flush(file, locator, lines, file_name):
            text = "\n".join(lines).strip()
            if file and locator and text and text != "[no text on this page]":
                found.append((file, locator | {"_file_name": file_name}, text))

        for line in result.splitlines():
            if line.startswith("sources:") or line.startswith("<</data"):
                break
            if line.startswith("file_id: "):
                file = line[9:].split(" |", 1)[0]
                named = re.search(r"(?:^| \| )file: (.*?)(?: \||$)", line)
                file_name = named[1] if named else None
            if line.startswith("{"):
                try:
                    data, end = decoder.raw_decode(line)
                except ValueError:
                    data = {}
                if isinstance(data, dict) and (
                    "locator" in data or any(k in data for k in _PLACE_KEYS)
                ):
                    flush(file, locator, lines, file_name)
                    file = data.get("file_id", file)
                    file_name = data.get("file", file_name)
                    locator = data.get("locator", data)
                    lines = [line[end:].strip()]
                    continue
            if locator:
                lines.append(line)
        flush(file, locator, lines, file_name)
    return found


def unread_citations(text: str, returns: list[tuple[str, str]]) -> list[Problem]:
    """A cited place must occur in this Brief's returned text, including specialists' reads."""
    passages = read_passages(returns)
    problems = []
    for _, places, numbers in citations(text):
        for place in places:

            def matches(loc, coordinate, place=place):
                if place.file_name and loc.get("_file_name") != place.file_name:
                    return False
                if place.sheet == "":
                    return loc.get("line") == coordinate
                if place.sheet is not None:
                    return (
                        str(loc.get("sheet", "")).strip().casefold()
                        == place.sheet.strip().casefold()
                        and loc.get("row") == coordinate
                    )
                return loc.get("page") == coordinate

            coordinates = place.rows if place.sheet is not None else place.pages
            read_text = [
                words for _, loc, words in passages if any(matches(loc, n) for n in coordinates)
            ]
            have = numbers_guard.known_values(read_text)
            if not all(any(matches(loc, n) for _, loc, _ in passages) for n in coordinates) or any(
                value not in have for _, value in numbers
            ):
                where = place.words()
                if any(p.fix.startswith(where["en"] + " was") for p in problems):
                    continue
                problems.append(
                    Problem(
                        "unread_citation",
                        where["en"]
                        + " was not read in this Brief. Read it with files_read or read_chunk "
                        "before citing it; if unavailable, remove that claim "
                        "and say what is missing.",
                        copy.fill(copy.TRUTH_UNREAD_PLACE, place=where),
                    )
                )
    return problems
