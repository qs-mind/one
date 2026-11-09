"""Whether a number is what its source says (`_check_number`)."""

import json

from qsone.calc.units import UnitTable
from qsone.engine import truth
from qsone.engine.tools import ModelRetry
from qsone.engine.tools_records.shared import _RATES


def _check_number(conn, item: dict, name: str, value: str, unit: str | None, source_id: str):
    """Raises `ModelRetry` when the number is not what its source says: a value its file has
    not at the place cited (2,500 cited to a quote page with no 2,500; 3,795 = 3,450 × 1.1 cited
    as read), a rate per one unit on an item measured in another (a block's price per «عدد» on
    a wall in m2), or a supply-only quote's price on an item that is installed."""
    found = truth.value_at(conn, source_id, value)
    if found is not None and not found[0]:
        _, where, seen = found
        raise ModelRetry(
            f"record_number: {value} is not at the place its source cites ({where}); that place "
            f"has {', '.join(seen) or 'no numbers'}. Record the value as written there. A number "
            "you worked out (a total, an average, a price with waste or a margin) is not read "
            "from a file: record its inputs, then calculate it with its formula."
        )
    if truth.per_day_at(conn, source_id, value) and not truth.says_per_day(unit or ""):
        raise ModelRetry(
            f"record_number: its source writes {value} per day, and the unit «{unit or ''}» "
            "leaves the day out. Give the unit as the source has it, e.g. «% per day»."
        )
    if name.lower() not in _RATES:
        return
    fields = item["fields"]
    measured = fields.get("unit") or _quantity_unit(conn, item["id"])
    if unit and measured and not _same_measure(unit, measured):
        raise ModelRetry(
            f"record_number: the rate is per {unit} but item {item['code'] or item['id']} is "
            f"measured in {measured}. Record the source's price on a resource item in its own "
            "unit, then work out the item's rate with calculate (the conversion as an input)."
        )
    row = conn.execute("SELECT locator FROM sources WHERE id = ?", (source_id,)).fetchone()
    covers = json.loads(row[0]).get("covers") if row else None
    description = str(fields.get("description") or "")
    if covers == "supply" and item["kind"] == "boq_item" and description:
        if not truth.supply_only_item(description):
            raise ModelRetry(
                f"record_number: the source is a supply-only quote, and item "
                f"{item['code'] or item['id']} («{description[:80]}») is supplied and installed. "
                "Record the quote's price on a resource item (add_item kind resource), and build "
                "the item's rate with calculate, with labour from another source; or ask the "
                "engineer for an installed rate."
            )


def _quantity_unit(conn, item_id: str) -> str | None:
    row = conn.execute(
        "SELECT unit FROM numbers WHERE item_id = ? AND name = 'quantity' AND valid_until IS NULL",
        (item_id,),
    ).fetchone()
    return row[0] if row else None


_BASE = {"m", "kg", "s", "h"}  # measured dimensions; any other unit counts things


def _same_measure(a: str, b: str) -> bool:
    """Whether two units measure the same thing (m3 and م3; عدد and nr), as far as ONE's unit
    table knows them: an unknown unit is never refused."""
    table = UnitTable()
    try:
        da, db = table.parse(a).dims, table.parse(b).dims
    except Exception:  # noqa: BLE001 - a unit the table does not know: nothing to compare
        return True
    kind = lambda d: tuple(x for x in d if x[0] in _BASE) or "count"  # noqa: E731
    return kind(da) == kind(db)
