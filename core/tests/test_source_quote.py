"""A file source carries the line it was read from (Workspace plan, Task 3). Synthetic «عينة»
data only."""

import json

from qsone.deliverables import store
from qsone.records import ledger

LINE = "خرسانة C30 3,450 ج.م./م3"
AT = "2026-11-05T10:00:00+02:00"


def file_with_text(rec, *passages: str, page: int = 1) -> str:
    with rec.write("engineer") as conn:
        conn.execute(
            "INSERT INTO files(id, name, kind, size, sha256, status, added_at, added_by)"
            " VALUES ('f1', 'أسعار - عينة.pdf', 'pdf', 1, 'x', 'read', ?, 'engineer')",
            (AT,),
        )
        for seq, text in enumerate(passages):
            conn.execute(
                "INSERT INTO chunks(file_id, seq, locator, text) VALUES ('f1', ?, ?, ?)",
                (seq, json.dumps({"page": page}), text),
            )
    return "f1"


def file_source(rec, file_id: str, locator: dict | None = None) -> str:
    return ledger.add_source(
        rec,
        kind="file",
        title="أسعار - عينة",
        actor="engineer",
        file_id=file_id,
        locator=locator or {"page": 1},
    )


def test_file_source_has_its_line(rec):
    sid = file_source(rec, file_with_text(rec, LINE))
    assert store.sources_of(rec, [sid])[sid]["quote"] == LINE


def test_passages_are_joined_by_a_space(rec):
    sid = file_source(rec, file_with_text(rec, "خرسانة C30", "3,450 ج.م./م3"))
    assert store.sources_of(rec, [sid])[sid]["quote"] == "خرسانة C30 3,450 ج.م./م3"


def test_long_line_is_cut(rec):
    sid = file_source(rec, file_with_text(rec, "ب" * 600))
    quote = store.sources_of(rec, [sid])[sid]["quote"]
    assert len(quote) == 240 and quote.endswith("…") and quote[:-1] == "ب" * 239


def test_other_sources_have_no_quote(rec):
    engineer = ledger.add_source(rec, kind="engineer", title="المهندس", actor="engineer")
    calculation = ledger.add_source(rec, kind="calculation", title="حساب", actor="engineer")
    found = store.sources_of(rec, [engineer, calculation])
    assert found[engineer]["quote"] is None and found[calculation]["quote"] is None


def test_a_place_with_no_text_has_no_quote(rec):
    sid = file_source(rec, file_with_text(rec, LINE), {"page": 7})
    assert store.sources_of(rec, [sid])[sid]["quote"] is None
    sid = file_source(rec, "f1", {"column": "F"})  # a locator that names no place
    assert store.sources_of(rec, [sid])[sid]["quote"] is None


def test_a_sheets_numbers_carry_it_too(rec):
    fid = file_with_text(rec, LINE)
    sid = file_source(rec, fid)
    with rec.write("engineer") as conn:
        item = ledger.write_item(conn, at=AT, actor="engineer", kind="boq_item", code="3/02")
        ledger.write_number(
            conn, at=AT, actor="engineer", item_id=item, name="rate", value="3450",
            source_id=sid, dated="2026-11-05", unit="م3", currency="EGP",
        )  # fmt: skip
        _, sources = store._numbers(conn, [item], AT)
    assert sources[sid]["quote"] == LINE
