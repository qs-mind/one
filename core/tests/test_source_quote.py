"""A file source carries the line it was read from (Workspace plan, Task 3). Synthetic «عينة»
data only."""

import json

from qsone.deliverables import store
from qsone.deliverables import tools as outputs
from qsone.engine.tools import call
from qsone.records import ledger
from tests.fakes_tools import tool_ctx

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


def priced_sheet(rec, items: int) -> tuple[str, str]:
    """A Sheet of `items` rows, each one's rate and quantity from the one quoted file source."""
    sid = file_source(rec, file_with_text(rec, LINE))
    rows: list[dict] = [{"section": "أعمال - عينة", "level": 1}]
    with rec.write("engineer") as conn:
        for n in range(items):
            item = ledger.write_item(
                conn, at=AT, actor="engineer", kind="boq_item", code=f"3/{n:02}",
                fields={"description": f"خرسانة - عينة {n}"},
            )  # fmt: skip
            for name, value, currency in (("rate", "3450", "EGP"), ("quantity", "10", None)):
                ledger.write_number(
                    conn, at=AT, actor="engineer", item_id=item, name=name, value=value,
                    source_id=sid, dated="2026-11-05", unit="م3", currency=currency,
                )  # fmt: skip
            rows.append({"item_id": item})
    d = store.create(
        rec, kind="sheet", variant="boq", title="جدول الكميات - عينة", language="ar",
        actor="engineer", rows=rows,
    )  # fmt: skip
    return d, sid


def counting(monkeypatch) -> list[dict]:
    """Every read of a file's text at a place, as `_quote` asks for it."""
    asked: list[dict] = []
    texts_at = store.truth.texts_at

    def counted(conn, file_id, locator):
        asked.append(locator)
        return texts_at(conn, file_id, locator)

    monkeypatch.setattr(store.truth, "texts_at", counted)
    monkeypatch.setattr(store.truth.sources, "texts_at", counted)  # for value_in, per_day_at
    return asked


def test_the_screens_view_reads_each_sources_line_once(rec, monkeypatch):
    d, sid = priced_sheet(rec, 40)  # 80 numbers from one source
    asked = counting(monkeypatch)
    v = store.view(rec, d)
    assert asked == [] and "quote" not in v["sources"][sid]  # the view itself reads no quote
    shown = store.with_quotes(rec, v)
    assert shown["sources"][sid]["quote"] == LINE
    assert len(asked) == 1  # once for the view, not once per number


def test_the_list_never_reads_a_quote(rec, monkeypatch):
    priced_sheet(rec, 5)
    asked = counting(monkeypatch)
    assert store.list_deliverables(rec)
    assert asked == []


async def test_the_agents_read_has_no_quote(rec, monkeypatch):
    d, sid = priced_sheet(rec, 5)
    asked = counting(monkeypatch)
    page = json.loads(await call("deliverable_read", {"id": d}, tool_ctx(rec)))
    assert sid in page["sources"] and "quote" not in page["sources"][sid]
    assert asked == []
    assert "deliverable_read" in outputs.OUTPUTS_TOOLS
