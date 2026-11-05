"""The Deliverable store: templates, parts, the pinned view, calculations and Saved versions
(synthetic «عينة» data only)."""

import json
from decimal import Decimal

import pytest

import qsone.calc.engine
from qsone import copy
from qsone.deliverables import calc, events, template
from qsone.deliverables.calc import bring_up_to_date, dry_run, requests
from qsone.deliverables.store import (
    create,
    list_deliverables,
    part_now,
    put_part,
    save_version,
    status,
    view,
)
from qsone.records import ledger
from qsone.records.project import RecordsError
from tests.samples import (
    SAMPLE_ACTOR,
    sample_boq_rows,
    sample_document,
    sample_sheet,
    sample_source,
)

# Helpers ------------------------------------------------------------------------------------


def row_by_code_in(v: dict, code: str) -> dict:
    return next(r for r in v["rows"] if r.get("code") == code)


def row_by_code(rec, d: str, code: str) -> dict:
    return row_by_code_in(view(rec, d), code)


def correct_rate(rec, d: str, code: str, value: str) -> str:
    """Corrects the item's rate in Project Records, outside the Deliverable."""
    number_id = row_by_code(rec, d, code)["cells"]["rate"]["number_id"]
    return ledger.correct_number(
        rec,
        number_id,
        value=value,
        reason="عرض جديد - عينة",
        source_id=sample_source(rec),
        dated="2026-11-04",
        actor="estimator",
    )


def dump_tables(rec) -> dict:
    with rec.read() as c:
        names = [
            n
            for (n,) in c.execute(
                "select name from sqlite_master where type = 'table'"
                " and name not like 'chunks_fts%' and name not like 'price_cache_fts%'"
                " order by name"
            )
        ]
        return {n: c.execute(f"select * from {n} order by rowid").fetchall() for n in names}


def section_of(v: dict, title: str) -> dict:
    return next(r for r in v["rows"] if r["kind"] == "section" and r["title"] == title)


# The Sheet's cells point at the ledger ------------------------------------------------------


def test_sheet_cells_point_at_the_ledger(rec):
    d = sample_sheet(rec)
    v = view(rec, d)
    item = row_by_code_in(v, "03/02")
    rate, amount = item["cells"]["rate"], item["cells"]["amount"]
    assert rate["number_id"] and v["sources"][rate["source"]]["kind"] == "sample" and rate["dated"]
    assert (rate["value"], rate["unit"], rate["currency"]) == ("39850.50", "m3", "EGP")
    assert amount["calculated"] and v["sources"][amount["source"]]["kind"] == "calculation"
    assert amount["value"] == "4782060.00"  # 120 × 39850.50, saved by the QS Calc Engine
    assert item["cells"]["unit"] == {"text": "m3"} and item["cells"]["code"] == {"text": "03/02"}
    assert "ـ" in item["cells"]["description"]["text"]  # tatweel kept
    assert v["sample"] and v["version"] == 1 and v["language"] == "ar"
    assert [c["key"] for c in v["columns"]] == [
        "code",
        "description",
        "unit",
        "quantity",
        "rate",
        "amount",
    ]
    assert {c["key"]: c["kind"] for c in v["columns"]}["amount"] == "calc"
    assert "dir" not in v


def test_section_and_bill_totals_are_saved_calculations(rec):
    v = view(rec, sample_sheet(rec))
    digging = section_of(v, "أعمال الحفر")
    concrete = section_of(v, "أعمال الخرسانة")
    assert digging["cells"]["amount"]["calculated"] and v["total"]["calculated"]
    assert digging["cells"]["amount"]["value"] == "104770.00"  # 77770.00 + 27000.00
    # 235125.00 + 4782060.00 + 60800.00; the rate-only 2-4 has no amount
    assert concrete["cells"]["amount"]["value"] == "5077985.00"
    assert v["total"]["value"] == "5182755.00" and v["total"]["currency"] == "EGP"
    assert v["sources"][v["total"]["source"]]["kind"] == "calculation"


def test_the_view_never_calls_the_calc_engine(rec, monkeypatch):
    d = sample_sheet(rec)
    monkeypatch.setattr(qsone.calc.engine, "calculate", lambda *a, **k: pytest.fail("computed"))
    monkeypatch.setattr(calc, "calculate", lambda *a, **k: pytest.fail("view computed"))
    assert view(rec, d)["total"]["value"]


def test_rate_only_item_shows_its_note_and_is_counted_incomplete(rec):
    v = view(rec, sample_sheet(rec, with_rate_only=True))
    row = next(r for r in v["rows"] if r["cells"].get("quantity", {}).get("text") == "فئة فقط")
    assert "amount" not in row["cells"] and v["incomplete"]["amount"] == 1
    assert row["cells"]["rate"]["value"] == "120"
    assert v["progress"] == {"done": 6, "total": 6}


def test_the_view_is_pinned_to_its_version(rec):
    d = sample_sheet(rec)
    assert not view(rec, d)["records_moved"]
    correct_rate(rec, d, "03/02", "40000")
    v = view(rec, d)
    assert row_by_code_in(v, "03/02")["cells"]["rate"]["value"] == "39850.50" and v["records_moved"]
    assert row_by_code_in(v, "03/02")["cells"]["amount"]["value"] == "4782060.00"


def test_a_past_version_is_rebuilt_from_parts_items_and_ledger(rec):
    d = sample_sheet(rec)
    first = view(rec, d)
    item_id = row_by_code_in(first, "03/02")["item_id"]
    ledger.update_item(rec, item_id, fields={"description": "وصف جديد - عينة"}, actor="estimator")
    correct_rate(rec, d, "03/02", "40000")
    bring_up_to_date(rec, d, actor="engineer")
    with rec.write("engineer") as c:
        assert save_version(c, rec, d, by="engineer", change_ids=[]) == 2
    now = view(rec, d)
    row = row_by_code_in(now, "03/02")
    assert row["cells"]["rate"]["value"] == "40000" and row["cells"]["amount"]["value"] == (
        "4800000.00"
    )
    assert row["cells"]["description"]["text"] == "وصف جديد - عينة" and row["item_version"] == 2
    assert now["version"] == 2 and not now["records_moved"]
    assert view(rec, d, version=1) == first | {"records_moved": True}


def test_dry_run_leaves_nothing_behind(rec):
    d = sample_sheet(rec)
    before = dump_tables(rec)
    _, cells = dry_run(rec, d, lambda: correct_rate(rec, d, "03/02", "40000"))
    row = row_by_code(rec, d, "03/02")["id"]
    amount = next(c for c in cells if c["row"] == row and c["column"] == "amount")
    assert amount["before"]["value"] == "4782060.00" and amount["after"]["value"] == "4800000.00"
    assert {c["row"] for c in cells} >= {"total", section_of(view(rec, d), "أعمال الخرسانة")["id"]}
    assert dump_tables(rec) == before


def test_dry_run_inside_a_write_leaves_the_outer_work(rec):
    d = sample_sheet(rec)
    with rec.write("engineer"):
        kept = ledger.add_source(rec, kind="sample", title="مصدر - عينة", actor="engineer")
        dry_run(rec, d, lambda: correct_rate(rec, d, "03/02", "40000"))
    with rec.read() as c:
        assert c.execute("select count(*) from sources where id = ?", (kept,)).fetchone()[0] == 1
    assert row_by_code(rec, d, "03/02")["cells"]["rate"]["value"] == "39850.50"


def test_bring_up_to_date_writes_nothing_when_nothing_moved(rec):
    d = sample_sheet(rec)
    before = dump_tables(rec)
    assert bring_up_to_date(rec, d, actor="engineer") == []
    assert dump_tables(rec) == before


def test_bring_up_to_date_after_an_outside_correction(rec):
    d = sample_sheet(rec)
    v = view(rec, d)
    correct_rate(rec, d, "03/02", "40000")
    cells = bring_up_to_date(rec, d, actor="engineer")
    shown = {(c["row"], c["column"]): (c["before"]["value"], c["after"]["value"]) for c in cells}
    assert shown == {
        (row_by_code_in(v, "03/02")["id"], "amount"): ("4782060.00", "4800000.00"),
        (section_of(v, "أعمال الخرسانة")["id"], "amount"): ("5077985.00", "5095925.00"),
        ("total", "amount"): ("5182755.00", "5200695.00"),
    }
    with rec.read() as c:
        reason = c.execute(
            "select reason from numbers where id = ?", (cells[0]["after"]["number_id"],)
        ).fetchone()[0]
    assert reason == copy.fill(copy.DELIVERABLE_CALC_REASON, title="جدول الكميات - عينة")["ar"]


def test_requests_run_items_then_sections_deepest_first_then_the_bill(rec):
    rows = sample_boq_rows(rec, 5, with_rate_only=False)
    # «أعمال الحفر» (1-1, 1-2) holds a level-2 section «أعمال الخرسانة» (2-1, 03/02, 2-3).
    rows[3]["level"] = 2
    d = create(
        rec, kind="sheet", variant="boq", title="جدول - عينة", language="ar", actor="lead_qs",
        rows=rows,
    )  # fmt: skip
    v = view(rec, d)
    outer, inner = section_of(v, "أعمال الحفر"), section_of(v, "أعمال الخرسانة")
    assert inner["level"] == 2 and inner["cells"]["amount"]["value"] == "5077985.00"
    assert outer["cells"]["amount"]["value"] == "5182755.00"  # 104770.00 + the inner section
    assert v["total"]["value"] == "5182755.00"
    reqs = requests(rec, d)
    targets = [r.item for r in reqs]
    items = [r["item_id"] for r in v["rows"] if r["kind"] == "item"]
    with rec.read() as c:
        (bill,) = c.execute("select total_item_id from deliverables where id = ?", (d,)).fetchone()
    assert targets == [*items, inner["item_id"], outer["item_id"], bill]
    assert reqs[-1].inputs["amount"].numbers == [outer["cells"]["amount"]["number_id"]]
    assert reqs[0].formula == "quantity * rate" and reqs[0].result.unit == "EGP"
    only = requests(rec, d, rows=[row_by_code_in(v, "1-1")["id"]])
    assert [r.item for r in only] == [items[0], outer["item_id"], bill]


def test_view_reads_in_a_few_queries(rec):
    d = sample_sheet(rec, rows=200)
    count = []
    with rec.read() as c:
        c.set_trace_callback(count.append)
    try:
        v = view(rec, d)
    finally:
        with rec.read() as c:
            c.set_trace_callback(None)
    assert len(v["rows"]) == 200 + 2 + 4 and len(count) <= 15


# Templates and columns ----------------------------------------------------------------------


def test_columns_from_the_lead_qs_are_checked(rec):
    with pytest.raises(RecordsError) as e:
        create(
            rec, kind="sheet", variant="boq", title="x", language="ar", actor="lead_qs",
            columns=[{"key": "total", "from": "eval:__import__('os')"}],
        )  # fmt: skip
    assert e.value.text == copy.COLUMN_NOT_ALLOWED and e.value.field == "columns[0].from"


@pytest.mark.parametrize(
    ("column", "field"),
    [
        ({"key": "x", "label": {"en": "x", "ar": "x"}, "from": "number:"}, "columns[0].from"),
        ({"key": "x", "label": {"en": "x", "ar": "x"}, "from": "field:a b"}, "columns[0].from"),
        ({"key": "X y", "label": {"en": "x", "ar": "x"}, "from": "code"}, "columns[0].key"),
        ({"key": "x", "from": "code"}, "columns[0].label"),
        ({"key": "x", "label": {"en": "x", "ar": "x"}, "from": "code", "run": 1}, "columns[0]"),
        (
            {"key": "x", "label": {"en": "x", "ar": "x"}, "from": "number:x",
             "calc": {"formula": "quantity *", "unit": "currency_of:rate"}},
            "columns[0].calc.formula",
        ),
        (
            {"key": "x", "label": {"en": "x", "ar": "x"}, "from": "number:x",
             "calc": {"formula": "secret * 2", "unit": "currency_of:secret"}},
            "columns[0].calc.formula",
        ),
    ],
)  # fmt: skip
def test_bad_columns_say_which_field(column, field):
    with pytest.raises(RecordsError) as e:
        template.columns_for([column])
    assert e.value.text == copy.COLUMN_NOT_ALLOWED and e.value.field == field


def test_two_columns_with_one_key_are_refused():
    code = {"key": "code", "label": {"en": "x", "ar": "x"}, "from": "code"}
    with pytest.raises(RecordsError) as e:
        template.columns_for([code, code])
    assert e.value.field == "columns[1].key"


def test_extra_field_columns_are_allowed(rec):
    rows = sample_boq_rows(rec, 2, with_rate_only=False)
    item_id = rows[1]["item_id"]
    with rec.read() as c:
        (fields,) = c.execute("select fields from items where id = ?", (item_id,)).fetchone()
    ledger.update_item(
        rec, item_id, fields={**json.loads(fields), "floor": "الدور الأرضي"}, actor=SAMPLE_ACTOR
    )
    floor = {"key": "floor", "from": "field:floor", "label": {"en": "Floor", "ar": "الدور"}}
    d = create(
        rec, kind="sheet", variant="boq", title="x - عينة", language="ar", actor="lead_qs",
        columns=[*template.base("sheet")["default_columns"], floor], rows=rows,
    )  # fmt: skip
    v = view(rec, d)
    assert row_by_code_in(v, "1-1")["cells"]["floor"] == {"text": "الدور الأرضي"}
    assert v["columns"][-1] == {
        "key": "floor",
        "from": "field:floor",
        "label": {"en": "Floor", "ar": "الدور"},
        "kind": "text",
        "edit": False,
        "frozen": False,
        "wrap": False,
        "width": 120,
    }


def test_unknown_item_rows_are_refused(rec):
    with pytest.raises(RecordsError) as e:
        create(
            rec, kind="sheet", variant="boq", title="x", language="ar", actor="lead_qs",
            rows=[{"section": "أعمال - عينة", "level": 1}, {"item_id": "f" * 32}],
        )  # fmt: skip
    assert e.value.text == copy.ROW_NOT_FOUND and e.value.field == "rows[1]"
    with rec.read() as c:
        assert c.execute("select count(*) from deliverables").fetchone()[0] == 0


def test_unknown_kind_is_refused(rec):
    with pytest.raises(RecordsError) as e:
        create(rec, kind="board", variant="x", title="x", language="ar", actor="lead_qs")
    assert e.value.text == copy.TEMPLATE_UNKNOWN and e.value.field == "kind"


# Documents ----------------------------------------------------------------------------------


def test_document_refs_resolve_and_digits_outside_refs_are_untraced(rec):
    sheet = sample_sheet(rec)
    v = view(rec, sample_document(rec, sheet))
    assert v["kind"] == "document" and "rows" not in v and v["progress"] is None
    assert [b["node"]["type"] for b in v["blocks"]] == ["h1", "p", "p", "p"]
    assert any(r["calculated"] for r in v["refs"].values()) and v["untraced"][0]["text"] == "٣٠"
    total = v["refs"][f"cell:{sheet}:total:amount"]
    assert total["value"] == "5182755.00" and v["sources"][total["source"]]["kind"] == "calculation"
    assert v["untraced"] == [{"block": v["blocks"][3]["id"], "text": "٣٠"}] and v["sample"]


def test_a_num_reference_is_pinned_like_a_cell(rec):
    sheet = sample_sheet(rec)
    rate = row_by_code(rec, sheet, "03/02")["cells"]["rate"]["number_id"]
    num = {"type": "num", "number": rate, "children": [{"text": ""}]}
    d = create(
        rec, kind="document", variant="note", title="مذكرة - عينة", language="ar",
        actor="lead_qs", blocks=[{"type": "p", "children": [{"text": "الفئة "}, num]}],
    )  # fmt: skip
    assert view(rec, d)["refs"][f"num:{rate}"]["value"] == "39850.50"
    correct_rate(rec, sheet, "03/02", "40000")
    v = view(rec, d)
    assert v["refs"][f"num:{rate}"]["value"] == "39850.50" and v["records_moved"]


def test_sample_is_found_through_a_calculations_inputs(rec):
    sheet = sample_sheet(rec)
    amount = row_by_code(rec, sheet, "03/02")["cells"]["amount"]["number_id"]
    num = {"type": "num", "number": amount, "children": [{"text": ""}]}
    d = create(
        rec, kind="document", variant="note", title="مذكرة - عينة", language="ar",
        actor="lead_qs", blocks=[{"type": "p", "children": [num]}],
    )  # fmt: skip
    v = view(rec, d)
    assert {s["kind"] for s in v["sources"].values()} == {"calculation"} and v["sample"]


def test_unknown_node_type_is_refused(rec):
    for node, field in [
        ({"type": "script", "children": [{"text": "x"}]}, "blocks[0]"),
        ({"type": "p", "onclick": "x", "children": [{"text": "x"}]}, "blocks[0]"),
        ({"type": "p", "children": [{"text": "x", "color": "red"}]}, "blocks[0]"),
        ({"type": "p", "children": [{"type": "num", "children": [{"text": ""}]}]}, "blocks[0]"),
    ]:
        with pytest.raises(RecordsError) as e:
            create(
                rec, kind="document", variant="x", title="x", language="ar", actor="lead_qs",
                blocks=[node],
            )  # fmt: skip
        assert e.value.text == copy.NODE_NOT_ALLOWED and e.value.field == field


# Status, list and events --------------------------------------------------------------------


def test_status_starts_as_draft(rec):
    d = sample_sheet(rec)
    assert status(rec, d) == {
        "status": "draft",
        "code": None,
        "same_provider": False,
        "off_desk": False,
    }
    v = view(rec, d)
    assert (v["status"], v["code"], v["revision"], v["pending"], v["open_comments"]) == (
        "draft",
        None,
        None,
        0,
        0,
    )


def test_status_follows_checks_and_signed_off_revisions(rec):
    d = sample_sheet(rec)
    with rec.write("checking_qs") as c:
        c.execute(
            "insert into checks values ('k1', ?, 1, 'B', 'model-x - عينة', 1, '', ?)",
            (d, rec.clock()),
        )
    assert status(rec, d) == {"status": "checked", "code": "B", "same_provider": True,
                              "off_desk": False}  # fmt: skip
    with rec.write("engineer") as c:
        c.execute(
            "insert into revisions values (?, 1, 1, ?, 'engineer', 1, x'00', 'sha')",
            (d, rec.clock()),
        )
    assert status(rec, d)["status"] == "signed_off"
    assert view(rec, d)["revision"] == {"no": 1, "version": 1, "signed_off": True}


def test_a_revision_view_is_its_frozen_snapshot(rec):
    import hashlib
    import zlib

    d = sample_sheet(rec)
    frozen = view(rec, d)
    body = json.dumps(frozen, sort_keys=True, ensure_ascii=False).encode()
    with rec.write("engineer") as c:
        c.execute(
            "insert into revisions values (?, 1, 1, ?, 'engineer', 0, ?, ?)",
            (d, rec.clock(), zlib.compress(body), hashlib.sha256(body).hexdigest()),
        )
    correct_rate(rec, d, "03/02", "40000")
    assert view(rec, d, revision=1) == frozen
    with pytest.raises(RecordsError) as e:
        view(rec, d, revision=2)
    assert e.value.text == copy.DELIVERABLE_NOT_FOUND


def test_unknown_deliverable_or_version(rec):
    with pytest.raises(RecordsError) as e:
        view(rec, "f" * 32)
    assert e.value.text == copy.DELIVERABLE_NOT_FOUND and e.value.status == 404
    d = sample_sheet(rec)
    with pytest.raises(RecordsError) as e:
        view(rec, d, version=9)
    assert e.value.text == copy.DELIVERABLE_NOT_FOUND and e.value.field == "version"


def test_list_matches_the_canvas_contract(rec):
    first = sample_sheet(rec)
    second = sample_document(rec, first)
    entries = list_deliverables(rec)
    assert [e["id"] for e in entries] == [second, first]
    plan7 = {
        "id", "kind", "title", "language", "status", "code", "same_provider", "revision",
        "desk", "off_desk", "progress", "open_comments", "updated_at",
    }  # fmt: skip
    assert all(plan7 | {"pending", "total", "sample"} <= set(e) for e in entries)
    sheet = entries[1]
    assert sheet["progress"] == {"done": 6, "total": 6} and entries[0]["progress"] is None
    assert sheet["total"]["value"] == "5182755.00" and sheet["sample"]
    assert (sheet["kind"], sheet["revision"], sheet["desk"], sheet["off_desk"]) == (
        "sheet",
        None,
        None,
        False,
    )


def test_create_publishes_a_deliverable_event(rec):
    seen = []
    stop = events.listen(lambda project_id, event: seen.append((project_id, event)))
    try:
        d = sample_sheet(rec)
    finally:
        stop()
    assert len(seen) == 1
    project_id, event = seen[0]
    assert project_id == rec.id and event["type"] == "deliverable"
    assert event["deliverable"]["id"] == d and event["deliverable"]["status"] == "draft"
    sample_sheet(rec)
    assert len(seen) == 1  # stopped listening


def test_create_saves_version_one_with_its_parts_and_audit(rec):
    d = sample_sheet(rec)
    with rec.read() as c:
        versions = c.execute("select n, by, changes from versions where deliverable_id = ?", (d,))
        assert versions.fetchall() == [(1, SAMPLE_ACTOR, "[]")]
        seqs = [s for (s,) in c.execute("select seq from parts where deliverable_id = ?", (d,))]
        kinds = {
            t
            for (t,) in c.execute(
                "select distinct table_name from audit where table_name in"
                " ('deliverables', 'parts', 'versions', 'calculations')"
            )
        }
    assert seqs == [1024.0 * n for n in range(1, 9)]
    assert kinds == {"deliverables", "parts", "versions", "calculations"}


def test_a_part_changes_by_a_new_row_version(rec):
    d = sample_sheet(rec)
    section = section_of(view(rec, d), "أعمال الحفر")
    with rec.write("engineer") as c:
        old = part_now(c, section["id"])
        put_part(
            c, rec, deliverable_id=d, part_id=section["id"], kind="section", seq=old["seq"],
            item_id=old["item_id"], node={"title": "أعمال الحفر والردم", "level": 1},
            actor="engineer",
        )  # fmt: skip
        assert part_now(c, section["id"])["version"] == 2
        save_version(c, rec, d, by="engineer", change_ids=["c1"])
    assert section_of(view(rec, d), "أعمال الحفر والردم")["version"] == 2
    assert section_of(view(rec, d, version=1), "أعمال الحفر")["version"] == 1
    with rec.read() as c:
        rows = c.execute(
            "select version, valid_until is null from parts where id = ? order by rowid_",
            (section["id"],),
        ).fetchall()
        changes = c.execute(
            "select changes from versions where deliverable_id = ? and n = 2", (d,)
        ).fetchone()
    assert rows == [(1, 0), (2, 1)] and changes == ('["c1"]',)
    with rec.write("engineer") as c, pytest.raises(RecordsError) as e:
        put_part(
            c, rec, deliverable_id=d, part_id="f" * 32, kind="item", seq=1.0, item_id=None,
            node={}, actor="engineer",
        )  # fmt: skip
    assert e.value.text == copy.ROW_NOT_FOUND


def test_engine_rounding_stays_exact(rec):
    rows = sample_boq_rows(rec, 1, with_rate_only=False)
    item_id = rows[1]["item_id"]
    (rate,) = [n for n in ledger.numbers(rec, item_id) if n.name == "rate"]
    ledger.correct_number(
        rec, rate.id, value="14.005", reason="عينة", source_id=sample_source(rec),
        dated="2026-11-02", actor="estimator",
    )  # fmt: skip
    d = create(
        rec, kind="sheet", variant="boq", title="x - عينة", language="en", actor="lead_qs",
        rows=rows,
    )  # fmt: skip
    amount = row_by_code(rec, d, "1-1")["cells"]["amount"]["value"]
    assert amount == str((Decimal("5555") * Decimal("14.005")).quantize(Decimal("0.01")))
