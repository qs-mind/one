"""A synthetic sample project for the QS Calc Engine tests («عينة» / "sample"). Never real data."""

from pathlib import Path
from uuid import uuid4

from qsone.records import ledger
from qsone.records.project import Records

ACTOR = "estimator"
DATED = "2026-11-02"

# Source kind -> title. `add` takes a source by its kind.
SOURCES = {
    "quote": "عرض سعر مورد - عينة",
    "mix_design": "تصميم خلطة - عينة",
    "exchange_rate": "البنك المركزي - عينة",
    "contract": "العقد - عينة",
    "boq": "جدول الكميات - عينة",
}


def sample_project(tmp_path: Path) -> Records:
    """A new project holding the sample sources. Close it when done."""
    rec = Records.create(tmp_path / uuid4().hex, name="مشروع - عينة", actor=ACTOR)
    with rec.write(ACTOR) as conn:
        for kind, title in SOURCES.items():
            ledger.write_source(
                conn, at=rec.clock(), actor=ACTOR, kind=kind, title=title, dated=DATED
            )
    return rec


def source_id(rec: Records, kind: str) -> str:
    """The sample source of that kind."""
    with rec.read() as conn:
        row = conn.execute(
            "SELECT id FROM sources WHERE kind = ? AND title = ?", (kind, SOURCES[kind])
        ).fetchone()
    return row[0]


def add(
    rec: Records, code: str, kind: str = "boq_item", *, fields: dict | None = None, **numbers
) -> str:
    """Adds an item and records each `name=(value, unit, currency, source kind)`, dated 2026-11-02.

    Returns the item id."""
    sources = {k: source_id(rec, k) for k in {n[3] for n in numbers.values()}}
    with rec.write(ACTOR) as conn:
        item = ledger.write_item(
            conn, at=rec.clock(), actor=ACTOR, kind=kind, code=code, fields=fields
        )
        for name, (value, unit, currency, source) in numbers.items():
            ledger.write_number(
                conn,
                at=rec.clock(),
                actor=ACTOR,
                item_id=item,
                name=name,
                value=value,
                unit=unit,
                currency=currency,
                source_id=sources[source],
                dated=DATED,
            )
    return item
