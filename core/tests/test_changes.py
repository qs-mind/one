"""Operations, Suggested changes and Saved versions (synthetic «عينة» data only)."""

from datetime import date

import pytest

from qsone import copy
from qsone.calc.engine import calculate
from qsone.calc.spec import CalcRequest
from qsone.deliverables import changes, events, ops
from qsone.deliverables.changes import accept, accept_mine, pending, propose, reject
from qsone.deliverables.store import view
from qsone.records import ledger
from qsone.records.project import RecordsError
from tests.samples import sample_document, sample_sheet, sample_source

# Helpers ------------------------------------------------------------------------------------


def row_by_code_in(v: dict, code: str) -> dict:
    return next(r for r in v["rows"] if r.get("code") == code)


def row_by_code(rec, d: str, code: str) -> dict:
    return row_by_code_in(view(rec, d), code)


def section_of(v: dict, title: str) -> dict:
    return next(r for r in v["rows"] if r["kind"] == "section" and r["title"] == title)


def set_rate(row: dict, value: str, **extra) -> dict:
    return {
        "op": "set_number",
        "row": row["id"],
        "name": "rate",
        "value": value,
        "expect": row["cells"]["rate"]["number_id"],
        **extra,
    }


def table(rec, name: str) -> list:
    with rec.read() as c:
        return c.execute(f"select * from {name} order by rowid").fetchall()


def count(rec, sql: str, *args) -> int:
    with rec.read() as c:
        return c.execute(sql, args).fetchone()[0]


def correct_outside(rec, number_id: str, value: str, reason: str = "عرض جديد - عينة") -> str:
    return ledger.correct_number(
        rec,
        number_id,
        value=value,
        reason=reason,
        source_id=sample_source(rec),
        dated="2026-11-04",
        actor="estimator",
    )


def strip_volatile(v: dict) -> dict:
    """What a Saved version holds: not the counts and statuses that move with time."""
    volatile = {"status", "code", "same_provider", "pending", "open_comments", "records_moved"}
    return {k: value for k, value in v.items() if k not in volatile | {"revision"}}


# A proposed change ---------------------------------------------------------------------------


def test_a_proposed_change_leaves_the_ledger_alone(rec):
    d = sample_sheet(rec)
    row = row_by_code(rec, d, "03/02")
    old = row["cells"]["rate"]
    numbers, parts, versions = table(rec, "numbers"), table(rec, "parts"), table(rec, "versions")
    [ch] = propose(
        rec, d, [set_rate(row, "40000.00", source_id=sample_source(rec))], actor="estimator"
    )
    assert ch.status == "pending" and ch.author == "estimator"
    assert ch.before["value"] == old["value"] and ch.after["value"] == "40000.00"
    mine = {(f["column"], f["after"]["value"]) for f in ch.follows if f["row"] == row["id"]}
    assert mine == {("amount", "4800000.00")}
    v = view(rec, d)
    concrete = section_of(v, "أعمال الخرسانة")["id"]
    assert {f["row"] for f in ch.follows} == {row["id"], concrete, "total"}
    assert row_by_code(rec, d, "03/02")["cells"]["rate"] == old
    assert table(rec, "numbers") == numbers and table(rec, "parts") == parts
    assert table(rec, "versions") == versions
    assert v["pending"] == 1 and [c.id for c in pending(rec, d)] == [ch.id]


def test_accept_writes_ledger_version_and_audit_in_one_go(rec):
    d = sample_sheet(rec)
    row = row_by_code(rec, d, "03/02")
    old_rate = row["cells"]["rate"]["number_id"]
    [ch] = propose(
        rec, d, [set_rate(row, "40000.00", source_id=sample_source(rec))], actor="estimator"
    )
    audit_before = count(rec, "select max(id) from audit")
    out = accept(rec, d, [ch.id], actor="engineer")
    assert out == {"version": 2, "accepted": [ch.id], "stale": []}
    v = view(rec, d)
    now = row_by_code_in(v, "03/02")["cells"]
    assert now["rate"]["value"] == "40000.00" and now["amount"]["value"] == "4800000.00"
    assert now["amount"]["calculated"]
    concrete = section_of(v, "أعمال الخرسانة")["cells"]["amount"]
    assert concrete["value"] == "5095925.00" and concrete["calculated"]
    assert v["total"]["value"] == "5200695.00" and v["total"]["calculated"]
    with rec.read() as c:
        assert c.execute("select valid_until from numbers where id = ?", (old_rate,)).fetchone()[0]
        replaces = c.execute(
            "select replaces from numbers where id = ?", (now["rate"]["number_id"],)
        ).fetchone()[0]
        assert replaces == old_rate
        assert c.execute("select changes from versions where n = 2").fetchone()[0] == (
            f'["{ch.id}"]'
        )
        status, version_n, by = c.execute(
            "select status, version_n, decided_by from changes where id = ?", (ch.id,)
        ).fetchone()
        assert (status, version_n, by) == ("accepted", 2, "engineer")
        actions = {
            (t, a)
            for t, a in c.execute(
                "select table_name, action from audit where id > ?", (audit_before,)
            )
        }
    assert {("numbers", "correct"), ("calculations", "create"), ("versions", "create")} <= actions
    assert ("changes", "update") in actions
    assert v["status"] == "draft" and v["version"] == 2 and not v["records_moved"]
    assert pending(rec, d) == []


def test_accept_publishes_the_deliverable(rec):
    d = sample_sheet(rec)
    seen = []
    stop = events.listen(lambda project, event: seen.append(event))
    try:
        [ch] = propose(rec, d, [set_rate(row_by_code(rec, d, "1-1"), "15")], actor="engineer")
        accept(rec, d, [ch.id], actor="engineer")
    finally:
        stop()
    assert [e["deliverable"]["pending"] for e in seen] == [1, 0]


def test_a_failed_accept_rolls_back_everything(rec, monkeypatch):
    d = sample_sheet(rec)
    a = propose(rec, d, [set_rate(row_by_code(rec, d, "1-1"), "15")], actor="engineer")[0]
    b = propose(rec, d, [set_rate(row_by_code(rec, d, "1-2"), "25")], actor="engineer")[0]
    numbers, parts, versions = table(rec, "numbers"), table(rec, "parts"), table(rec, "versions")
    calls, real = [], ops.apply

    def apply(*args, **kwargs):
        calls.append(1)
        if len(calls) == 2:
            raise RuntimeError("the second apply fails")
        return real(*args, **kwargs)

    monkeypatch.setattr(ops, "apply", apply)
    with pytest.raises(RuntimeError):
        accept(rec, d, [a.id, b.id], actor="engineer")
    assert table(rec, "numbers") == numbers and table(rec, "parts") == parts
    assert table(rec, "versions") == versions
    assert {c.status for c in pending(rec, d)} == {"pending"}


# Who may do what ------------------------------------------------------------------------------


def test_engineer_numbers_get_an_engineer_source(rec):
    d = sample_sheet(rec)
    row = row_by_code(rec, d, "03/02")
    [ch] = propose(rec, d, [set_rate(row, "41000")], actor="engineer")
    assert ch.after["value"] == "41000" and ch.after["dated"] == date.today().isoformat()
    accept(rec, d, [ch.id], actor="engineer")
    v = view(rec, d)
    rate = row_by_code_in(v, "03/02")["cells"]["rate"]
    source = v["sources"][rate["source"]]
    assert source["kind"] == "engineer" and source["title"] == copy.ENTERED_BY_ENGINEER["ar"]
    assert rate["dated"] == date.today().isoformat()
    with rec.read() as c:
        reason = c.execute(
            "select reason from numbers where id = ?", (rate["number_id"],)
        ).fetchone()[0]
    assert reason == copy.fill(copy.MANUAL_EDIT_REASON, title="جدول الكميات - عينة")["ar"]


def test_agent_numbers_need_a_source(rec):
    d = sample_sheet(rec)
    with pytest.raises(RecordsError) as e:
        propose(rec, d, [set_rate(row_by_code(rec, d, "03/02"), "1")], actor="lead_qs")
    assert e.value.text == copy.NUMBER_NEEDS_SOURCE and e.value.field == "ops[0].source_id"


def test_amount_cannot_be_typed(rec):
    d = sample_sheet(rec)
    row = row_by_code(rec, d, "03/02")
    op = {"op": "set_number", "row": row["id"], "name": "amount", "value": "1", "expect": None}
    with pytest.raises(RecordsError) as e:
        propose(rec, d, [op], actor="engineer")
    assert e.value.text == copy.AMOUNT_IS_COMPUTED and e.value.field == "ops[0].name"


def test_every_op_is_checked_before_any_is_stored(rec):
    d = sample_sheet(rec)
    row = row_by_code(rec, d, "03/02")
    with pytest.raises(RecordsError) as e:
        propose(rec, d, [set_rate(row, "1"), set_rate(row, "1,000")], actor="engineer")
    assert e.value.text == copy.NUMBER_NOT_EXACT and e.value.field == "ops[1].value"
    assert table(rec, "changes") == []


@pytest.mark.parametrize(
    ("make", "text", "field"),
    [
        (lambda v: {"op": "drop_table"}, copy.OP_UNKNOWN, "ops[0].op"),
        (lambda v: {"op": "update_from_records", "cells": []}, copy.OP_UNKNOWN, "ops[0].op"),
        (
            lambda v: {"op": "set_block", "block": "x", "node": {}, "expect": 1},
            copy.OP_NOT_IN_TEMPLATE,
            "ops[0].op",
        ),
        (
            lambda v: {"op": "set_field", "row": "nope", "key": "description", "value": "x"},
            copy.ROW_NOT_FOUND,
            "ops[0].row",
        ),
        (
            lambda v: {
                "op": "set_number",
                "row": v["rows"][1]["id"],
                "name": "floor",
                "value": "1",
            },
            copy.OP_NOT_IN_TEMPLATE,
            "ops[0].name",
        ),
        (
            lambda v: {"op": "set_field", "row": v["rows"][1]["id"], "key": "code", "value": "x"},
            copy.OP_NOT_IN_TEMPLATE,
            "ops[0].key",
        ),
        (
            lambda v: {"op": "set_section_title", "row": v["rows"][1]["id"], "title": "x"},
            copy.ROW_NOT_FOUND,
            "ops[0].row",
        ),
    ],
)
def test_bad_ops_say_what_to_fix(rec, make, text, field):
    d = sample_sheet(rec)
    with pytest.raises(RecordsError) as e:
        propose(rec, d, [make(view(rec, d))], actor="engineer")
    assert e.value.text == text and e.value.field == field


def test_only_the_engineer_accepts_or_rejects(rec):
    d = sample_sheet(rec)
    [ch] = propose(rec, d, [set_rate(row_by_code(rec, d, "1-1"), "15")], actor="engineer")
    with pytest.raises(ValueError):
        accept(rec, d, [ch.id], actor="lead_qs")
    with pytest.raises(ValueError):
        reject(rec, d, [ch.id], actor="checking_qs")


def test_accept_all_mine_takes_only_the_engineers_own(rec):
    d = sample_sheet(rec)
    mine = propose(rec, d, [set_rate(row_by_code(rec, d, "1-1"), "15")], actor="engineer")[0]
    theirs = propose(
        rec,
        d,
        [set_rate(row_by_code(rec, d, "1-2"), "25", source_id=sample_source(rec))],
        actor="lead_qs",
    )[0]
    out = accept_mine(rec, d, actor="engineer")
    assert out == {"version": 2, "accepted": [mine.id], "stale": []}
    assert [c.id for c in pending(rec, d)] == [theirs.id]


def test_reject_leaves_everything_but_the_change(rec):
    d = sample_sheet(rec)
    [ch] = propose(rec, d, [set_rate(row_by_code(rec, d, "1-1"), "15")], actor="engineer")
    numbers, versions = table(rec, "numbers"), table(rec, "versions")
    assert reject(rec, d, [ch.id], actor="engineer") == [ch.id]
    assert table(rec, "numbers") == numbers and table(rec, "versions") == versions
    assert pending(rec, d) == []
    with pytest.raises(RecordsError) as e:
        reject(rec, d, [ch.id], actor="engineer")
    assert e.value.text == copy.CHANGE_NOT_PENDING
    with pytest.raises(RecordsError) as e:
        accept(rec, d, [ch.id], actor="engineer")
    assert e.value.text == copy.CHANGE_NOT_PENDING


# Stale changes ----------------------------------------------------------------------------------


def test_stale_change_is_never_applied(rec):
    d = sample_sheet(rec)
    row = row_by_code(rec, d, "03/02")
    a = propose(rec, d, [set_rate(row, "100")], actor="engineer")[0]
    b = propose(rec, d, [set_rate(row, "200", source_id=sample_source(rec))], actor="lead_qs")[0]
    assert accept(rec, d, [a.id], actor="engineer")["version"] == 2
    assert accept(rec, d, [b.id], actor="engineer") == {
        "version": None,
        "accepted": [],
        "stale": [b.id],
    }
    assert row_by_code(rec, d, "03/02")["cells"]["rate"]["value"] == "100"
    assert view(rec, d)["version"] == 2
    assert count(rec, "select count(*) from changes where status = 'stale'") == 1


def test_a_change_made_against_an_old_value_is_refused(rec):
    d = sample_sheet(rec)
    row = row_by_code(rec, d, "03/02")
    with pytest.raises(RecordsError) as e:
        propose(rec, d, [{**set_rate(row, "1"), "expect": "someone-else"}], actor="engineer")
    assert e.value.text == copy.CHANGE_STALE and e.value.field == "ops[0].expect"


def test_expect_is_filled_when_left_out(rec):
    d = sample_sheet(rec)
    row = row_by_code(rec, d, "03/02")
    op = set_rate(row, "1")
    del op["expect"]
    [ch] = propose(rec, d, [op], actor="engineer")
    assert ch.op["expect"] == row["cells"]["rate"]["number_id"]


def test_batch_accept_is_one_version(rec):
    d = sample_sheet(rec)
    v = view(rec, d)
    out = propose(
        rec,
        d,
        [
            set_rate(row_by_code_in(v, "1-1"), "15"),
            set_rate(row_by_code_in(v, "1-2"), "25"),
            {
                "op": "set_field",
                "row": row_by_code_in(v, "2-1")["id"],
                "key": "description",
                "value": "خرسانة عادية - عينة معدلة",
                "expect": row_by_code_in(v, "2-1")["item_version"],
            },
        ],
        actor="engineer",
    )
    result = accept(rec, d, [c.id for c in out], actor="engineer")
    assert result["version"] == 2 and result["accepted"] == [c.id for c in out]
    with rec.read() as c:
        assert c.execute("select count(*) from versions").fetchone()[0] == 2
    now = view(rec, d)
    assert section_of(now, "أعمال الحفر")["cells"]["amount"]["value"] == "113325.00"
    assert row_by_code_in(now, "2-1")["cells"]["description"]["text"] == "خرسانة عادية - عينة معدلة"


def test_paste_of_arabic_digits_is_exact(rec):
    d = sample_sheet(rec)
    row = row_by_code(rec, d, "03/02")
    [ch] = propose(rec, d, [set_rate(row, "٣٩٨٥٠٫٥٠")], actor="engineer")
    assert ch.after["value"] == "39850.50"
    accept(rec, d, [ch.id], actor="engineer")
    assert row_by_code(rec, d, "03/02")["cells"]["rate"]["value"] == "39850.50"


def test_a_missing_quantity_can_be_entered(rec):
    d = sample_sheet(rec)
    row = row_by_code(rec, d, "2-4")  # «فئة فقط»: a rate and no quantity
    op = {"op": "set_number", "row": row["id"], "name": "quantity", "value": "10", "expect": None}
    [ch] = propose(rec, d, [op], actor="engineer")
    assert ch.before == {"text": "فئة فقط"} and ch.after["unit"] == "م2"
    assert {f["column"] for f in ch.follows if f["row"] == row["id"]} == {"amount"}
    accept(rec, d, [ch.id], actor="engineer")
    v = view(rec, d)
    assert row_by_code_in(v, "2-4")["cells"]["amount"]["value"] == "1200.00"
    assert v["incomplete"]["amount"] == 0


# A rate that was calculated --------------------------------------------------------------------


def build_up_rate(rec, d: str, labour: str = "10000") -> None:
    """A rate build-up saved by an agent with Plan 3's calculate: material + labour."""
    item_id = row_by_code(rec, d, "03/02")["item_id"]
    for name, value in (("material", "30000"), ("labour", labour)):
        ledger.record_number(
            rec,
            item_id=item_id,
            name=name,
            value=value,
            unit="m3",
            currency="EGP",
            source_id=sample_source(rec),
            dated="2026-11-03",
            actor="lead_qs",
        )
    req = CalcRequest(
        formula="material + labour",
        item=item_id,
        result={"unit": "EGP/m3"},
        save={"name": "rate", "reason": "تحليل سعر - عينة"},
    )
    calculate(rec, req, actor="lead_qs")


def test_records_change_from_an_agent_calculation(rec):
    d = sample_sheet(rec)
    build_up_rate(rec, d)
    v = view(rec, d)
    assert row_by_code_in(v, "03/02")["cells"]["rate"]["value"] == "39850.50"
    [up] = pending(rec, d)
    assert up.op["op"] == "update_from_records" and up.author == "calc_engine"
    cells = {(c["row"], c["column"]): c for c in up.op["cells"]}
    rate = cells[(row_by_code_in(v, "03/02")["id"], "rate")]
    assert rate["after"]["value"] == "40000.00" and rate["after"]["calculated"]
    assert rate["why"] == {"recalculated": True}
    assert cells[("total", "amount")]["after"]["value"] == "5200695.00"
    assert accept(rec, d, [up.id], actor="engineer")["version"] == 2
    assert row_by_code(rec, d, "03/02")["cells"]["rate"]["value"] == "40000.00"


def test_typing_over_a_calculated_rate_says_so(rec):
    d = sample_sheet(rec)
    build_up_rate(rec, d)
    [up] = pending(rec, d)
    accept(rec, d, [up.id], actor="engineer")
    [ch] = propose(rec, d, [set_rate(row_by_code(rec, d, "03/02"), "41000")], actor="engineer")
    assert ch.note == copy.fill(copy.NUMBER_WAS_CALCULATED, formula="material + labour")
    plain = propose(rec, d, [set_rate(row_by_code(rec, d, "1-1"), "15")], actor="engineer")[0]
    assert plain.note is None


# Ledger moves from outside ---------------------------------------------------------------------


def test_outside_ledger_moves_arrive_as_one_change(rec):
    d = sample_sheet(rec)
    row = row_by_code(rec, d, "03/02")
    new = correct_outside(rec, row["cells"]["rate"]["number_id"], "40000")
    assert row_by_code(rec, d, "03/02")["cells"]["rate"]["value"] == "39850.50"
    [up] = pending(rec, d)
    assert up.op["op"] == "update_from_records" and up.status == "pending"
    cells = {(c["row"], c["column"]): c for c in up.op["cells"]}
    assert cells[(row["id"], "rate")]["why"] == {"corrected": "عرض جديد - عينة"}
    assert cells[(row["id"], "rate")]["before"]["value"] == "39850.50"
    assert cells[(row["id"], "amount")]["after"]["value"] == "4800000.00"
    assert cells[(row["id"], "amount")]["why"] == {"recalculated": True}
    assert [c.id for c in pending(rec, d)] == [up.id]  # read again: the same one
    correct_outside(rec, new, "40500", reason="عرض أحدث - عينة")
    [fresh] = pending(rec, d)
    assert fresh.id != up.id
    assert (
        count(
            rec,
            "select count(*) from changes where json_extract(op, '$.op') = 'update_from_records'",
        )
        == 2
    )
    rate = next(c for c in fresh.op["cells"] if c["column"] == "rate")
    assert rate["after"]["value"] == "40500" and rate["why"] == {"corrected": "عرض أحدث - عينة"}
    assert accept(rec, d, [up.id], actor="engineer")["stale"] == [up.id]
    assert accept(rec, d, [fresh.id], actor="engineer")["version"] == 2
    v = view(rec, d)
    assert row_by_code_in(v, "03/02")["cells"]["amount"]["value"] == "4860000.00"
    assert not v["records_moved"] and pending(rec, d) == []


def test_an_accept_takes_the_records_change_with_it(rec):
    """The view of a version reads the ledger as of that version, so the moves outside come in
    with any accept: the pending Update from Project Records is accepted with it, never lost."""
    d = sample_sheet(rec)
    row = row_by_code(rec, d, "03/02")
    correct_outside(rec, row["cells"]["rate"]["number_id"], "40000")
    [up] = pending(rec, d)
    [ch] = propose(rec, d, [set_rate(row_by_code(rec, d, "1-1"), "15")], actor="engineer")
    out = accept(rec, d, [ch.id], actor="engineer")
    assert out["version"] == 2 and out["accepted"] == [ch.id, up.id]
    v = view(rec, d)
    assert row_by_code_in(v, "03/02")["cells"]["amount"]["value"] == "4800000.00"
    assert v["total"]["value"] == "5206250.00"  # both changes in the totals
    assert pending(rec, d) == []


def test_no_records_change_when_nothing_moved(rec):
    d = sample_sheet(rec)
    assert changes.refresh_records_change(rec, d) is None and pending(rec, d) == []


# Rows and sections -------------------------------------------------------------------------------


def test_remove_and_move_rows_keep_history(rec):
    d = sample_sheet(rec)
    v1 = view(rec, d)
    gone, moved = row_by_code_in(v1, "1-2"), row_by_code_in(v1, "2-3")
    [rm] = propose(
        rec,
        d,
        [{"op": "remove_row", "row": gone["id"], "expect": gone["version"]}],
        actor="engineer",
    )
    assert rm.before["id"] == gone["id"] and rm.after is None
    digging = section_of(v1, "أعمال الحفر")
    assert {(f["row"], f["after"]["value"]) for f in rm.follows if f["row"] == digging["id"]} == {
        (digging["id"], "77770.00")
    }
    mv = propose(
        rec,
        d,
        [
            {
                "op": "move_row",
                "row": moved["id"],
                "after": digging["id"],
                "expect": moved["version"],
            }
        ],
        actor="engineer",
    )[0]
    accept(rec, d, [rm.id, mv.id], actor="engineer")
    v2 = view(rec, d)
    codes = [r.get("code") or r["title"] for r in v2["rows"]]
    assert codes == ["أعمال الحفر", "2-3", "1-1", "أعمال الخرسانة", "2-1", "03/02", "2-4"]
    assert section_of(v2, "أعمال الحفر")["cells"]["amount"]["value"] == "138570.00"
    assert section_of(v2, "أعمال الخرسانة")["cells"]["amount"]["value"] == "5017185.00"
    assert v2["total"]["value"] == "5155755.00"
    assert view(rec, d, version=1)["rows"] == v1["rows"]
    with rec.read() as c:
        assert (
            c.execute(
                "select removed from parts where id = ? and valid_until is null", (gone["id"],)
            ).fetchone()[0]
            == 1
        )


def test_removing_every_priced_row_under_a_section_ends_its_total(rec):
    """A section with nothing priced under it has no total, as when it was made with none: its
    old total is ended in the ledger (kept, marked valid_until); the bill no longer counts it."""
    d = sample_sheet(rec)
    v1 = view(rec, d)
    digging = section_of(v1, "أعمال الحفر")
    first = row_by_code_in(v1, "1-2")
    [rm] = propose(
        rec, d, [{"op": "remove_row", "row": first["id"], "expect": 1}], actor="engineer"
    )
    accept(rec, d, [rm.id], actor="engineer")
    old_total = section_of(view(rec, d), "أعمال الحفر")["cells"]["amount"]
    assert old_total["value"] == "77770.00"
    [rm] = propose(
        rec,
        d,
        [{"op": "remove_row", "row": row_by_code(rec, d, "1-1")["id"], "expect": 1}],
        actor="engineer",
    )
    ended = [f for f in rm.follows if f["row"] == digging["id"]]
    assert ended == [{"row": digging["id"], "column": "amount", "before": old_total, "after": None}]
    accept(rec, d, [rm.id], actor="engineer")
    v2 = view(rec, d)
    assert "amount" not in section_of(v2, "أعمال الحفر")["cells"]
    assert v2["total"]["value"] == "5077985.00"  # the concrete works alone
    with rec.read() as c:
        assert c.execute(
            "select valid_until is not null from numbers where id = ?", (old_total["number_id"],)
        ).fetchone()[0]
    assert section_of(view(rec, d, version=2), "أعمال الحفر")["cells"]["amount"] == old_total
    # A priced row added back gives the section a total again.
    [add] = propose(
        rec,
        d,
        [
            {
                "op": "add_item_row",
                "after": digging["id"],
                "code": "1-3",
                "fields": {"description": "حفر يدوي - عينة"},
                "numbers": [
                    {"name": "quantity", "value": "10", "unit": "m3"},
                    {"name": "rate", "value": "50", "unit": "m3", "currency": "EGP"},
                ],
            }
        ],
        actor="engineer",
    )
    accept(rec, d, [add.id], actor="engineer")
    v3 = view(rec, d)
    assert section_of(v3, "أعمال الحفر")["cells"]["amount"]["value"] == "500.00"
    assert v3["total"]["value"] == "5078485.00"


def test_add_section_and_rename_it(rec):
    d = sample_sheet(rec)
    v = view(rec, d)
    last = v["rows"][-1]
    [add] = propose(
        rec,
        d,
        [{"op": "add_section", "after": last["id"], "title": "أعمال التشطيبات - عينة", "level": 1}],
        actor="engineer",
    )
    assert add.before is None and add.after["title"] == "أعمال التشطيبات - عينة"
    accept(rec, d, [add.id], actor="engineer")
    new = section_of(view(rec, d), "أعمال التشطيبات - عينة")
    [ren] = propose(
        rec,
        d,
        [{"op": "set_section_title", "row": new["id"], "title": "التشطيبات - عينة", "expect": 1}],
        actor="engineer",
    )
    assert ren.before == {"text": "أعمال التشطيبات - عينة"}
    assert ren.after == {"text": "التشطيبات - عينة"}
    accept(rec, d, [ren.id], actor="engineer")
    v = view(rec, d)
    assert v["rows"][-1]["title"] == "التشطيبات - عينة" and v["rows"][-1]["version"] == 2
    assert v["total"]["value"] == "5182755.00"  # an empty section adds nothing


def test_an_agent_adds_a_row_with_sourced_numbers(rec):
    d = sample_sheet(rec)
    first = view(rec, d)["rows"][0]
    source = sample_source(rec)
    op = {
        "op": "add_item_row",
        "after": None,
        "code": "0-1",
        "fields": {"description": "أعمال تمهيدية - عينة"},
        "numbers": [{"name": "rate", "value": "500", "unit": "m3", "currency": "EGP"}],
    }
    with pytest.raises(RecordsError) as e:
        propose(rec, d, [op], actor="lead_qs")
    assert (
        e.value.text == copy.NUMBER_NEEDS_SOURCE and e.value.field == "ops[0].numbers[0].source_id"
    )
    op["numbers"][0]["source_id"] = source
    [ch] = propose(rec, d, [op], actor="lead_qs")
    assert ch.after["code"] == "0-1" and ch.after["cells"]["rate"]["value"] == "500"
    accept(rec, d, [ch.id], actor="engineer")
    rows = view(rec, d)["rows"]
    assert rows[0]["code"] == "0-1" and rows[1]["id"] == first["id"]


def test_parts_are_renumbered_when_there_is_no_room(rec):
    d = sample_sheet(rec)
    top = view(rec, d)["rows"][0]
    for n in range(32):  # each new row halves the gap before the first row
        [ch] = propose(
            rec,
            d,
            [{"op": "add_section", "after": None, "title": f"باب {n} - عينة", "level": 1}],
            actor="engineer",
        )
        accept(rec, d, [ch.id], actor="engineer")
    rows = view(rec, d)["rows"]
    assert [r["title"] for r in rows[:2]] == ["باب 31 - عينة", "باب 30 - عينة"]
    assert rows[32]["id"] == top["id"]
    with rec.read() as c:
        seqs = [
            s
            for (s,) in c.execute(
                "select seq from parts where deliverable_id = ? and valid_until is null"
                " order by seq",
                (d,),
            )
        ]
    assert min(b - a for a, b in zip(seqs, seqs[1:], strict=False)) >= 1e-6


def test_columns_change_by_a_new_template_version(rec):
    d = sample_sheet(rec)
    v1 = view(rec, d)
    columns = [
        {"key": "code", "label": {"en": "Item", "ar": "البند"}, "from": "code", "frozen": True},
        {
            "key": "rate",
            "label": {"en": "Rate", "ar": "الفئة"},
            "from": "number:rate",
            "edit": True,
        },
    ]
    [ch] = propose(
        rec, d, [{"op": "set_columns", "columns": columns, "expect": 1}], actor="lead_qs"
    )
    assert [c["key"] for c in ch.after["columns"]] == ["code", "rate"]
    accept(rec, d, [ch.id], actor="engineer")
    v2 = view(rec, d)
    assert [c["key"] for c in v2["columns"]] == ["code", "rate"]
    assert [c["key"] for c in view(rec, d, version=1)["columns"]] == [
        c["key"] for c in v1["columns"]
    ]
    with pytest.raises(RecordsError) as e:
        propose(rec, d, [{"op": "set_columns", "columns": columns, "expect": 1}], actor="lead_qs")
    assert e.value.text == copy.CHANGE_STALE
    with pytest.raises(RecordsError) as e:
        bad = [{"key": "x", "from": "eval:1", "label": {"en": "x", "ar": "x"}}]
        propose(rec, d, [{"op": "set_columns", "columns": bad, "expect": 2}], actor="lead_qs")
    assert e.value.text == copy.COLUMN_NOT_ALLOWED and e.value.field == "ops[0].columns[0].from"


# Documents ----------------------------------------------------------------------------------


def test_document_block_edit_shows_before_and_after(rec):
    d = sample_document(rec, sample_sheet(rec))
    blocks = view(rec, d)["blocks"]
    block = blocks[-1]
    node = {"type": "p", "children": [{"text": "الأسعار سارية حالياً لمدة ٤٥ يوماً"}]}
    [ch] = propose(
        rec,
        d,
        [{"op": "set_block", "block": block["id"], "node": node, "expect": block["version"]}],
        actor="lead_qs",
    )
    assert ch.before == block and ch.after == {"id": block["id"], "version": 2, "node": node}
    assert ch.follows == []
    accept(rec, d, [ch.id], actor="engineer")
    v = view(rec, d)
    assert v["blocks"][-1]["node"] == node and v["untraced"][0]["text"] == "٤٥"
    assert view(rec, d, version=1)["blocks"] == blocks


def test_document_blocks_insert_move_and_remove(rec):
    d = sample_document(rec, sample_sheet(rec))
    blocks = view(rec, d)["blocks"]
    heading, last = blocks[0], blocks[-1]
    bad = {"type": "script", "children": [{"text": "x"}]}
    with pytest.raises(RecordsError) as e:
        propose(rec, d, [{"op": "insert_block", "after": None, "node": bad}], actor="lead_qs")
    assert e.value.text == copy.NODE_NOT_ALLOWED and e.value.field == "ops[0].node"
    node = {"type": "p", "children": [{"text": "وتفضلوا بقبول فائق الاحترام - عينة"}]}
    out = propose(
        rec,
        d,
        [
            {"op": "insert_block", "after": last["id"], "node": node},
            {"op": "move_block", "block": last["id"], "after": heading["id"], "expect": 1},
            {"op": "remove_block", "block": blocks[1]["id"], "expect": 1},
        ],
        actor="lead_qs",
    )
    accept(rec, d, [c.id for c in out], actor="engineer")
    ids = [b["id"] for b in view(rec, d)["blocks"]]
    assert ids[:2] == [heading["id"], last["id"]] and blocks[1]["id"] not in ids
    assert view(rec, d)["blocks"][-1]["node"] == node and len(ids) == 4


# Saved versions rebuild exactly ------------------------------------------------------------------


def _number(name: str, code: str, value: str):
    def make(rec, d, v):
        row = row_by_code_in(v, code)
        return {
            "op": "set_number",
            "row": row["id"],
            "name": name,
            "value": value,
            "expect": row["cells"][name]["number_id"],
        }

    return make


def _field(code: str, text: str):
    def make(rec, d, v):
        row = row_by_code_in(v, code)
        return {
            "op": "set_field",
            "row": row["id"],
            "key": "description",
            "value": text,
            "expect": row["item_version"],
        }

    return make


def _move(code: str, after_code: str | None):
    def make(rec, d, v):
        row = row_by_code_in(v, code)
        after = None if after_code is None else row_by_code_in(v, after_code)["id"]
        return {"op": "move_row", "row": row["id"], "after": after, "expect": row["version"]}

    return make


def _remove(code: str):
    def make(rec, d, v):
        row = row_by_code_in(v, code)
        return {"op": "remove_row", "row": row["id"], "expect": row["version"]}

    return make


def _outside(code: str, value: str):
    """A correction in Project Records, then its Update from Project Records accepted."""

    def make(rec, d, v):
        correct_outside(rec, row_by_code_in(v, code)["cells"]["rate"]["number_id"], value)
        return "records"

    return make


SCRIPT_A = [
    [_number("rate", "03/02", "40000.00"), _number("quantity", "1-1", "6000")],
    [_outside("2-1", "2800")],
    [_field("1-2", "ردم - عينة معدلة"), _move("2-3", "1-1")],
    [_number("rate", "2-3", "100")],
    [_remove("1-2")],
]
SCRIPT_B = [
    [_move("03/02", None)],
    [_number("rate", "03/02", "39000"), _field("03/02", "خرسانة - عينة معدلة")],
    [_outside("03/02", "39500")],
    [_remove("2-4"), _number("quantity", "2-1", "90")],
    [_move("1-1", "2-1"), _outside("1-2", "23")],
]


def run(rec, d: str, step: list) -> dict:
    v = view(rec, d)
    made = [make(rec, d, v) for make in step]
    out = {"version": None}
    ops_ = [op for op in made if op != "records"]
    ids = [c.id for c in propose(rec, d, ops_, actor="engineer")] if ops_ else []
    if "records" in made:
        ids += [c.id for c in pending(rec, d) if c.op["op"] == "update_from_records"]
    if ids:
        out = accept(rec, d, ids, actor="engineer")
    return out


@pytest.mark.parametrize("steps", [SCRIPT_A, SCRIPT_B], ids=["A", "B"])
def test_saved_versions_rebuild_exactly(rec, steps):
    d = sample_sheet(rec)
    seen = {1: strip_volatile(view(rec, d))}
    for step in steps:
        out = run(rec, d, step)
        assert out["version"] and not out["stale"]
        seen[out["version"]] = strip_volatile(view(rec, d))
    assert sorted(seen) == list(range(1, len(steps) + 2))
    for n, then in seen.items():
        assert strip_volatile(view(rec, d, version=n)) == then
