"""Whether the engineer asked for a client BOQ item's price (`_price_item_named`): a
rate goes on one only when the engineer named the item, asked for pricing, or named
their own priced copy."""

import json
import re

from qsone import copy
from qsone.calc import resolve
from qsone.engine.tools import ToolContext
from qsone.engine.tools_records.shared import _RATES
from qsone.records import arabic, boq
from qsone.records.project import Records, RecordsError


def _pricing_requested(message: str) -> bool:
    """Recognise pricing intent without interpreting its object or limiting BOQ scope."""
    text = re.sub(r"[\u064b-\u065f\u0670]", "", arabic.clean(message).casefold())
    text = text.translate(str.maketrans("أإآٱ", "اااا"))
    return bool(
        re.search(
            r"(?<!\w)(?:سعر|تسعير|اتسعر|يتسعر|تتسعر)(?!\w)"
            r"|\b(?:price|rate|cost)\s+(?=[a-z])|\bpricing\b",
            text,
        )
    )


def _engineers_priced_copy(target: Records, source_id: str | None, message: str) -> bool:
    """Whether the engineer identified this source file as their own priced BOQ copy."""
    if not source_id:
        return False
    with target.read() as conn:
        source = conn.execute(
            "SELECT file_id, locator FROM sources WHERE id = ?", (source_id,)
        ).fetchone()
    if not source or not source[0]:
        return False
    file_id, raw = source
    loc = json.loads(raw)
    if not isinstance(loc.get("row"), int) or not isinstance(loc.get("sheet"), str):
        return False
    try:
        book = boq.workbook(target, file_id)
        _, sheet = boq.read(book, loc["sheet"])
    except RecordsError:
        return False
    _, columns = boq.guess(sheet, boq.PREVIEW_ROWS)
    said = re.sub(r"[\u064b-\u065f]", "", arabic.clean(message).casefold())
    return (
        "rate" in columns
        and "quantity" in columns
        and book.name.casefold() in said
        and bool(re.search(r"my priced (?:copy|boq)|نسختي المسعر[ةه]|نسختي اللي سعرتها", said))
    )


def _price_item_named(
    ctx: ToolContext, target: Records, ref: str, name: str, source_id: str | None = None
) -> None:
    """A source row names evidence, not the BOQ item to which its price belongs."""
    if name.lower() not in _RATES:
        return
    with target.read() as conn:
        item = resolve.find_item(conn, ref, field="item")
    if item["kind"] != boq.ITEM:
        return
    code = arabic.clean(item.get("code") or "").casefold()
    row = item["fields"].get("row")
    item_word = r"(?:boq\s+)?(?:item|code)|(?:البند|بند|كود البند|كود)"

    def names_item(text: str, *, answer: bool = False) -> bool:
        text = arabic.clean(text).casefold()
        if code:
            escaped = re.escape(code)
            if answer and text.strip(' «»"') == code:
                return True
            if re.search(
                rf"(?:{item_word})\s*(?:no\.?|number|رقم)?\s*[:#«\"]?\s*{escaped}(?![\w/-]|\.\d)",
                text,
            ):
                return True
            # A compound code (16.1-1, 03/02) is unambiguous without the word item.
            if (
                any(c.isdigit() for c in code)
                and any(c in "/-" for c in code)
                and re.search(rf"(?<![\w./-]){escaped}(?![\w/-]|\.\d)", text)
            ):
                return True
        if isinstance(row, int):
            # An unqualified source's 'row 8' must never authorise BOQ row 8.
            pattern = (
                r"(?:boq\s+row|item\s+(?:at\s+)?row|صف\s+المقايسة|صف\s+البند)"
                rf"\s*[:#]?\s*{row}(?!\d)"
            )
            if re.search(pattern, text):
                return True
        return False

    message = ctx.store.brief(ctx.brief_id)["text"]
    if names_item(message):
        return
    if _pricing_requested(message) or _engineers_priced_copy(target, source_id, message):
        return
    with ctx.store.rec.read() as conn:
        answers = conn.execute(
            "SELECT card, choice FROM approvals WHERE brief_id = ? AND status = 'settled'",
            (ctx.brief_id,),
        ).fetchall()
    for card_json, choice in answers:
        try:
            answer = json.loads(choice)
        except (ValueError, TypeError):
            continue
        if not isinstance(answer, dict):
            continue
        card = json.loads(card_json)
        questions = {
            q["id"]: q.get("text", "") for q in card.get("payload", {}).get("questions", [])
        }
        for key, value in answer.get("answers", {}).items():
            if not isinstance(value, str):
                continue
            question = arabic.clean(str(questions.get(key, ""))).casefold()
            if names_item(value, answer=bool(re.search(item_word, question))):
                return
            if (
                isinstance(row, int)
                and arabic.clean(value).strip() == str(row)
                and re.search(r"boq\s+row|صف\s+المقايسة|صف\s+البند", question)
            ):
                return
    raise RecordsError(
        copy.fill(
            copy.BOQ_PRICE_ITEM_REQUIRED,
            item=item.get("code") or str(row or ref),
        ),
        status=422,
        field="item",
    )
