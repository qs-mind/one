"""A newer number of the same name on an item takes the older one's place (tender day, 5 Nov 2026):
the AI recorded a second rate for an item, both stayed current, and the priced BOQ never opened
again. The older entry is kept with its source, marked `valid_until`; a deliverable whose records
still hold two current numbers (written before this) opens, with a plain-words problem on that row.
Synthetic «عينة» data only."""

import json
import re

from qsone.calc.resolve import current_of
from qsone.deliverables import api, store
from qsone.records import audit, ledger
from tests.samples import SAMPLE_DATED, sample_sheet, sample_source

_HEX = re.compile(r"[0-9a-f]{32}")


def _row(v: dict, code: str) -> dict:
    return next(r for r in v["rows"] if r.get("code") == code)


def _current(rec, item_id: str, name: str) -> list[tuple]:
    with rec.read() as c:
        return c.execute(
            "SELECT id, value, source_id FROM numbers WHERE item_id = ? AND name = ?"
            " AND valid_until IS NULL",
            (item_id, name),
        ).fetchall()


def _record_rate(rec, item_id: str, value: str, source_id: str) -> str:
    return ledger.record_number(
        rec, item_id=item_id, name="rate", value=value, unit="m3", currency="EGP",
        source_id=source_id, dated=SAMPLE_DATED, actor="lead_qs",
    )  # fmt: skip


def _legacy_rate(rec, item_id: str, value: str, source_id: str) -> str:
    """A second current rate, as the ledger wrote it before 5 Nov 2026: no `replaces`."""
    number_id = "f" * 31 + value[-1]
    with rec.write("lead_qs") as c:
        row = {
            "id": number_id, "item_id": item_id, "name": "rate", "value": value, "unit": "m3",
            "currency": "EGP", "source_id": source_id, "dated": SAMPLE_DATED,
            "recorded_at": rec.clock(), "recorded_by": "lead_qs", "replaces": None,
            "reason": None, "valid_until": None,
        }  # fmt: skip
        c.execute(
            f"INSERT INTO numbers ({', '.join(row)}) VALUES ({', '.join('?' * len(row))})",
            tuple(row.values()),
        )
        audit.record(
            c, at=row["recorded_at"], actor="lead_qs", action="create", table="numbers",
            row_id=number_id, before=None, after=row,
        )  # fmt: skip
    return number_id


def test_a_second_rate_replaces_the_first_and_keeps_its_history(rec):
    d = sample_sheet(rec)
    item_id = _row(store.view(rec, d), "1-1")["item_id"]
    [(first, _, first_source)] = _current(rec, item_id, "rate")
    quote = ledger.add_source(
        rec, kind="document", title="عرض المورد - عينة", actor="lead_qs", dated=SAMPLE_DATED
    )
    second = _record_rate(rec, item_id, "15", quote)
    assert _current(rec, item_id, "rate") == [(second, "15", quote)]
    with rec.read() as c:
        old = c.execute(
            "SELECT value, source_id, valid_until FROM numbers WHERE id = ?", (first,)
        ).fetchone()
        replaces = c.execute("SELECT replaces FROM numbers WHERE id = ?", (second,)).fetchone()[0]
        assert current_of(c, first) == second
    assert old[:2] == ("14", first_source) and old[2] is not None
    assert replaces == first
    assert [h["action"] for h in ledger.history(rec, first)] == ["create", "correct"]


def test_the_sheet_still_brings_its_amounts_up_to_date(rec):
    d = sample_sheet(rec)
    item_id = _row(store.view(rec, d), "1-1")["item_id"]
    _record_rate(rec, item_id, "15", sample_source(rec))
    _record_rate(rec, item_id, "16", sample_source(rec))
    v = api.current_view(rec, d)
    assert _row(v, "1-1").get("problem") is None
    assert v["pending"] == 1  # the Update from Project Records: amount 5555 × 16


def test_a_deliverable_with_two_current_rates_still_opens(rec):
    d = sample_sheet(rec)
    item_id = _row(store.view(rec, d), "1-1")["item_id"]
    _legacy_rate(rec, item_id, "15", sample_source(rec))
    v = api.current_view(rec, d)  # was CALC_NUMBER_AMBIGUOUS, a 422 with hex ids
    problem = _row(v, "1-1")["problem"]
    assert set(problem) == {"en", "ar"}
    assert "14" in problem["ar"] and "15" in problem["ar"] and "الفئة" in problem["ar"]
    assert not _HEX.search(json.dumps(problem))
    assert _row(v, "1-2").get("problem") is None


def test_typing_the_rate_settles_two_current_rates(rec):
    d = sample_sheet(rec)
    item_id = _row(store.view(rec, d), "1-1")["item_id"]
    _legacy_rate(rec, item_id, "15", sample_source(rec))
    [kept, _] = _current(rec, item_id, "rate")
    ledger.correct_number(
        rec, kept[0], value="15", reason="عرض المورد - عينة", source_id=sample_source(rec),
        dated=SAMPLE_DATED, actor="engineer",
    )  # fmt: skip
    assert [v for _, v, _ in _current(rec, item_id, "rate")] == ["15"]
    assert _row(api.current_view(rec, d), "1-1").get("problem") is None
