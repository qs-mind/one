"""The Source Ledger: sources, items and the numbers that hang on them.

Every number has a source and a date and is exact decimal text, never a float. A number is never
edited or deleted (triggers in the file refuse it); a correction is a new entry with a reason,
and the old one is marked `valid_until`. The ledger stores numbers; it does no arithmetic.
"""

import json
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

from qsone import copy
from qsone.records import audit
from qsone.records.project import Records, RecordsError

_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹٫", "01234567890123456789.")
_EXACT = re.compile(r"[+-]?[0-9]+(\.[0-9]+)?")
_CURRENCY = re.compile(r"[A-Z]{3}")
_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")

_NUMBER_COLUMNS = (
    "id, item_id, name, value, unit, currency, source_id, dated,"
    " recorded_at, recorded_by, replaces, reason, valid_until"
)


@dataclass(frozen=True)
class Number:
    id: str
    item_id: str
    name: str
    value: Decimal
    unit: str | None
    currency: str | None
    source_id: str
    dated: str
    recorded_at: str
    recorded_by: str
    replaces: str | None
    reason: str | None
    valid_until: str | None


def _refuse(text: dict[str, str], field: str) -> RecordsError:
    return RecordsError(text, status=422, field=field)


def _exact(value) -> str:
    """The value as exact decimal text, digits as written (`"39850.50"` stays so)."""
    if isinstance(value, Decimal):
        text = format(value, "f") if value.is_finite() else ""
    elif isinstance(value, int) and not isinstance(value, bool):
        text = str(value)
    elif isinstance(value, str):
        text = value.translate(_DIGITS)
    else:  # float, bool, None and anything else
        text = ""
    if not _EXACT.fullmatch(text):
        raise _refuse(copy.NUMBER_NOT_EXACT, "value")
    return text


def _checked(name: str, value, unit: str | None, currency: str | None, dated: str):
    """Checks a number's own rules (not its source); returns value, unit and currency."""
    text = _exact(value)
    unit = (unit or "").strip() or None
    if unit is None and name in ("quantity", "rate"):
        raise _refuse(copy.NUMBER_NEEDS_UNIT, "unit")
    if currency is None and name in ("rate", "amount"):
        raise _refuse(copy.NUMBER_NEEDS_CURRENCY, "currency")
    if currency is not None and not _CURRENCY.fullmatch(currency):
        raise _refuse(copy.NUMBER_NEEDS_CURRENCY, "currency")
    try:
        if not (isinstance(dated, str) and _DATE.fullmatch(dated)):
            raise ValueError(dated)
        date.fromisoformat(dated)
    except ValueError:
        raise _refuse(copy.NUMBER_NEEDS_DATE, "dated") from None
    return text, unit, currency


def _need_source(conn, source_id: str) -> None:
    if conn.execute("SELECT 1 FROM sources WHERE id = ?", (source_id,)).fetchone() is None:
        raise _refuse(copy.NUMBER_NEEDS_SOURCE, "source_id")


def _row(conn, table: str, row_id: str, columns: str = "*") -> dict | None:
    cursor = conn.execute(f"SELECT {columns} FROM {table} WHERE id = ?", (row_id,))
    found = cursor.fetchone()
    if found is None:
        return None
    row = dict(zip([d[0] for d in cursor.description], found, strict=True))
    for key in ("fields", "locator"):
        if key in row:
            row[key] = json.loads(row[key])
    return row


def _insert(conn, table: str, row: dict) -> None:
    cols = ", ".join(row)
    marks = ", ".join("?" * len(row))
    conn.execute(f"INSERT INTO {table} ({cols}) VALUES ({marks})", tuple(row.values()))


def _dump(value: dict) -> str:
    return json.dumps(value, ensure_ascii=False)


# The four writers below run inside a transaction the caller holds (`rec.write(actor)`), so a
# calculation can write its source, its number and its own rows together. Each makes the same
# checks and audit rows as the `rec`-level function that wraps it.


def write_source(
    conn,
    *,
    at: str,
    actor: str,
    kind: str,
    title: str,
    file_id: str | None = None,
    locator: dict | None = None,
    url: str | None = None,
    dated: str | None = None,
) -> str:
    source_id = uuid4().hex
    row = {
        "id": source_id,
        "kind": kind,
        "title": title,
        "file_id": file_id,
        "locator": locator or {},
        "url": url,
        "dated": dated,
        "recorded_at": at,
        "recorded_by": actor,
    }
    _insert(conn, "sources", {**row, "locator": _dump(row["locator"])})
    audit.record(
        conn,
        at=at,
        actor=actor,
        action="create",
        table="sources",
        row_id=source_id,
        before=None,
        after=row,
    )
    return source_id


def write_item(
    conn, *, at: str, actor: str, kind: str, code: str | None = None, fields: dict | None = None
) -> str:
    item_id = uuid4().hex
    row = {
        "id": item_id,
        "kind": kind,
        "code": code,
        "fields": fields or {},
        "version": 1,
        "created_at": at,
        "created_by": actor,
        "updated_at": at,
        "updated_by": actor,
    }
    _insert(conn, "items", {**row, "fields": _dump(row["fields"])})
    audit.record(
        conn,
        at=at,
        actor=actor,
        action="create",
        table="items",
        row_id=item_id,
        before=None,
        after=row,
    )
    return item_id


def add_source(
    rec: Records,
    *,
    kind: str,
    title: str,
    actor: str,
    file_id: str | None = None,
    locator: dict | None = None,
    url: str | None = None,
    dated: str | None = None,
) -> str:
    with rec.write(actor) as conn:
        return write_source(
            conn,
            at=rec.clock(),
            actor=actor,
            kind=kind,
            title=title,
            file_id=file_id,
            locator=locator,
            url=url,
            dated=dated,
        )


def add_item(
    rec: Records, *, kind: str, actor: str, code: str | None = None, fields: dict | None = None
) -> str:
    with rec.write(actor) as conn:
        return write_item(conn, at=rec.clock(), actor=actor, kind=kind, code=code, fields=fields)


def update_item(rec: Records, item_id: str, *, fields: dict, actor: str) -> int:
    """Replaces the item's fields; returns the new version. Raises `KeyError` for an unknown id."""
    at = rec.clock()
    with rec.write(actor) as conn:
        before = _row(conn, "items", item_id)
        if before is None:
            raise KeyError(item_id)
        version = before["version"] + 1
        conn.execute(
            "UPDATE items SET fields = ?, version = ?, updated_at = ?, updated_by = ? WHERE id = ?",
            (_dump(fields), version, at, actor, item_id),
        )
        after = {
            **before,
            "fields": fields,
            "version": version,
            "updated_at": at,
            "updated_by": actor,
        }
        audit.record(
            conn,
            at=at,
            actor=actor,
            action="update",
            table="items",
            row_id=item_id,
            before=before,
            after=after,
        )
    return version


def write_number(
    conn,
    *,
    at: str,
    actor: str,
    item_id: str,
    name: str,
    value: str | Decimal | int,
    source_id: str,
    dated: str,
    unit: str | None = None,
    currency: str | None = None,
) -> str:
    text, unit, currency = _checked(name, value, unit, currency, dated)
    number_id = uuid4().hex
    row = {
        "id": number_id,
        "item_id": item_id,
        "name": name,
        "value": text,
        "unit": unit,
        "currency": currency,
        "source_id": source_id,
        "dated": dated,
        "recorded_at": at,
        "recorded_by": actor,
        "replaces": None,
        "reason": None,
        "valid_until": None,
    }
    _need_source(conn, source_id)
    _insert(conn, "numbers", row)
    audit.record(
        conn,
        at=at,
        actor=actor,
        action="create",
        table="numbers",
        row_id=number_id,
        before=None,
        after=row,
    )
    return number_id


def write_correction(
    conn,
    number_id: str,
    *,
    at: str,
    actor: str,
    value,
    reason: str,
    source_id: str,
    dated: str,
    unit: str | None = None,
    currency: str | None = None,
) -> str:
    """A new entry replaces a current number; the old one is kept, marked `valid_until`.

    Unit and currency default to the old entry's."""
    if not (reason or "").strip():
        raise _refuse(copy.CORRECTION_NEEDS_REASON, "reason")
    new_id = uuid4().hex
    old = _row(conn, "numbers", number_id)
    if old is None or old["valid_until"] is not None:
        raise RecordsError(copy.ALREADY_CORRECTED, status=422, field="number_id")
    text, unit, currency = _checked(
        old["name"],
        value,
        old["unit"] if unit is None else unit,
        old["currency"] if currency is None else currency,
        dated,
    )
    _need_source(conn, source_id)
    row = {
        **old,
        "id": new_id,
        "value": text,
        "unit": unit,
        "currency": currency,
        "source_id": source_id,
        "dated": dated,
        "recorded_at": at,
        "recorded_by": actor,
        "replaces": number_id,
        "reason": reason,
        "valid_until": None,
    }
    _insert(conn, "numbers", row)
    conn.execute("UPDATE numbers SET valid_until = ? WHERE id = ?", (at, number_id))
    audit.record(
        conn,
        at=at,
        actor=actor,
        action="correct",
        table="numbers",
        row_id=number_id,
        before=old,
        after={**old, "valid_until": at},
    )
    audit.record(
        conn,
        at=at,
        actor=actor,
        action="create",
        table="numbers",
        row_id=new_id,
        before=None,
        after=row,
    )
    return new_id


def record_number(
    rec: Records,
    *,
    item_id: str,
    name: str,
    value: str | Decimal | int,
    source_id: str,
    dated: str,
    actor: str,
    unit: str | None = None,
    currency: str | None = None,
) -> str:
    with rec.write(actor) as conn:
        return write_number(
            conn,
            at=rec.clock(),
            actor=actor,
            item_id=item_id,
            name=name,
            value=value,
            source_id=source_id,
            dated=dated,
            unit=unit,
            currency=currency,
        )


def correct_number(
    rec: Records,
    number_id: str,
    *,
    value,
    reason: str,
    source_id: str,
    dated: str,
    actor: str,
    unit: str | None = None,
    currency: str | None = None,
) -> str:
    """A new entry replaces a current number; the old one is kept, marked `valid_until`.

    Unit and currency default to the old entry's."""
    with rec.write(actor) as conn:
        return write_correction(
            conn,
            number_id,
            at=rec.clock(),
            actor=actor,
            value=value,
            reason=reason,
            source_id=source_id,
            dated=dated,
            unit=unit,
            currency=currency,
        )


def _moment(as_of: str) -> str:
    """`as_of` in the ledger's time format. A date alone means the end of that day, UTC."""
    if _DATE.fullmatch(as_of):
        return f"{date.fromisoformat(as_of).isoformat()}T23:59:59.999999+00:00"
    moment = datetime.fromisoformat(as_of)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC).isoformat(timespec="microseconds")


def numbers(rec: Records, item_id: str, *, as_of: str | None = None) -> list[Number]:
    """The item's current numbers, or what the ledger said at `as_of`, oldest first."""
    sql = f"SELECT {_NUMBER_COLUMNS} FROM numbers WHERE item_id = ?"
    if as_of is None:
        args: tuple = (item_id,)
        sql += " AND valid_until IS NULL"
    else:
        moment = _moment(as_of)
        args = (item_id, moment, moment)
        sql += " AND recorded_at <= ? AND (valid_until IS NULL OR valid_until > ?)"
    with rec.read() as conn:
        rows = conn.execute(sql + " ORDER BY recorded_at, rowid", args).fetchall()
    return [Number(*r[:3], Decimal(r[3]), *r[4:]) for r in rows]


def history(rec: Records, row_id: str) -> list[dict]:
    """Every change to one source, item or number, oldest first."""
    with rec.read() as conn:
        return audit.history(conn, row_id)
