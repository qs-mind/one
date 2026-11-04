"""Calculate, save with its trace, explain any number (synthetic «عينة» data only)."""

from decimal import Decimal

import pytest

from qsone import copy
from qsone.calc.engine import calculate, explain
from qsone.calc.errors import CalcError
from qsone.calc.resolve import define_unit
from qsone.calc.spec import CalcRequest, UnitRequest
from qsone.records.ledger import add_source, numbers, record_number
from tests.calc_samples import DATED, add, sample_project, source_id

TABLES = ("numbers", "sources", "calculations", "calc_inputs", "audit")


@pytest.fixture
def boq(tmp_path):
    """03/02: 120 m3 at 39850.50 EGP/m3; 03/03: 45 m2 at 180.25 EGP/m2; section item "03"."""
    rec = sample_project(tmp_path)
    add(rec, "03/02", quantity=("120", "m3", None, "boq"), rate=("39850.50", "m3", "EGP", "quote"))
    add(rec, "03/03", quantity=("45", "m2", None, "boq"), rate=("180.25", "m2", "EGP", "quote"))
    add(rec, "03", kind="section")
    yield rec
    rec.close()


def run(rec, formula, *, actor="estimator", **request) -> object:
    return calculate(rec, CalcRequest(formula=formula, **request), actor=actor)


def amounts(rec, **request):
    return run(
        rec,
        "quantity * rate",
        for_each={"code_prefix": "03/"},
        result={"unit": "EGP"},
        save={"name": "amount"},
        **request,
    )


def refused(call, *args, **kwargs) -> CalcError:
    with pytest.raises(CalcError) as e:
        call(*args, **kwargs)
    return e.value


def item_of(rec, code) -> str:
    with rec.read() as c:
        return c.execute("SELECT id FROM items WHERE code = ?", (code,)).fetchone()[0]


def counts(rec) -> dict:
    with rec.read() as c:
        return {t: c.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in TABLES}


def inputs_of(rec, calc_id) -> list[tuple]:
    with rec.read() as c:
        return c.execute(
            "SELECT name, seq, number_id FROM calc_inputs WHERE calc_id = ? ORDER BY rowid",
            (calc_id,),
        ).fetchall()


def test_save_writes_a_number_whose_source_is_the_calculation(boq):
    out = run(boq, "quantity * rate", item="03/02", result={"unit": "EGP"}, save={"name": "amount"})
    r = out.results[0]
    assert (r.value, r.unit, r.unchanged, r.dated) == ("4782060.00", "EGP", False, DATED)
    assert (r.item, r.code, r.exact) == (item_of(boq, "03/02"), "03/02", True)
    assert out.defaults_used == {
        "round": {"places": 2, "mode": "half_up"},
        "from_item": ["quantity", "rate"],
    }
    assert out.steps == [] and out.notes == [] and out.skipped == []
    n = numbers(boq, item_of(boq, "03/02"))[-1]
    assert (n.id, n.name, n.value, n.currency, n.unit) == (
        r.number,
        "amount",
        Decimal("4782060.00"),
        "EGP",
        None,
    )
    assert n.dated == DATED
    e = explain(boq, r.number)
    assert e["source"]["kind"] == "calculation"
    assert e["source"]["locator"] == {"calculation": r.calculation}
    calc = e["calculation"]
    assert (calc["id"], calc["formula"], calc["unit"], calc["exact"]) == (
        r.calculation,
        "quantity * rate",
        "EGP",
        True,
    )
    assert calc["rounding"]["places"] == 2 and calc["engine"] == 1
    assert (calc["stale"], calc["because"]) == (False, [])
    assert {i["name"]: i["source"]["title"] for i in calc["inputs"]} == {
        "quantity": "جدول الكميات - عينة",
        "rate": "عرض سعر مورد - عينة",
    }
    rate = next(i for i in calc["inputs"] if i["name"] == "rate")
    assert (rate["value"], rate["unit"], rate["dated"], rate["calculated"]) == (
        "39850.50",
        "EGP/m3",
        DATED,
        False,
    )
    assert calc["steps"][-1]["value"] == "4782060.00"
    assert e["number"]["current"] is True and e["number"]["replaced_by"] is None


def test_the_calculation_row_keeps_request_and_trace(boq):
    r = run(boq, "quantity * rate", item="03/02", result={"unit": "EGP"}, save={"name": "amount"})
    r = r.results[0]
    with boq.read() as c:
        row = c.execute(
            "SELECT value, unit, exact, engine, output, replaces, valid_until, request, trace"
            " FROM calculations WHERE id = ?",
            (r.calculation,),
        ).fetchone()
        audit = c.execute(
            "SELECT action, table_name FROM audit WHERE row_id = ?", (r.calculation,)
        ).fetchall()
    assert row[:7] == ("4782060.00", "EGP", 1, 1, r.number, None, None)
    assert '"item": "' + item_of(boq, "03/02") + '"' in row[7]
    assert '"steps"' in row[8] and '"defaults_used"' in row[8]
    assert audit == [("create", "calculations")]
    assert [name for name, _, _ in inputs_of(boq, r.calculation)] == ["quantity", "rate"]


def test_a_preview_writes_nothing(boq):
    before = counts(boq)
    out = run(boq, "quantity * rate", item="03/02", result={"unit": "EGP"})
    r = out.results[0]
    assert (r.value, r.number, r.calculation, r.unchanged) == ("4782060.00", None, None, False)
    assert out.steps and out.steps[-1]["text"] == "quantity * rate"
    assert counts(boq) == before


def test_a_preview_without_a_unit_keeps_the_one_found(boq):
    r = run(boq, "quantity * rate", item="03/02").results[0]
    assert (r.value, r.unit) == ("4782060.00", "EGP")


def test_a_preview_has_at_most_twenty_steps(boq):
    out = run(boq, " + ".join(["quantity"] * 30), item="03/02", result={"unit": "m3"})
    assert len(out.steps) == 20 and out.results[0].value == "3600.00"


def test_for_each_prices_a_section_in_one_call(boq):
    out = amounts(boq)
    assert [(r.code, r.value) for r in out.results] == [
        ("03/02", "4782060.00"),
        ("03/03", "8111.25"),
    ]
    assert all(r.number and r.calculation and not r.unchanged for r in out.results)
    assert out.steps == []
    assert numbers(boq, item_of(boq, "03/03"))[-1].value == Decimal("8111.25")


def test_running_it_again_is_a_no_op(boq):
    first = amounts(boq)
    before = counts(boq)
    again = amounts(boq)
    assert [r.unchanged for r in again.results] == [True, True]
    assert [(r.number, r.calculation, r.value) for r in again.results] == [
        (r.number, r.calculation, r.value) for r in first.results
    ]
    assert counts(boq) == before


def test_replacing_a_number_needs_a_reason(boq):
    boq_source = source_id(boq, "boq")
    typed = record_number(
        boq,
        item_id=item_of(boq, "03/02"),
        name="amount",
        value="4782000",
        currency="EGP",
        source_id=boq_source,
        dated=DATED,
        actor="estimator",
    )
    before = counts(boq)
    request = {"item": "03/02", "result": {"unit": "EGP"}}
    e = refused(run, boq, "quantity * rate", save={"name": "amount"}, **request)
    assert (e.key, e.field) == ("CALC_SAVE_NEEDS_REASON", "save.reason")
    assert e.values == {
        "item": "03/02",
        "name": "amount",
        "value": "4782000",
        "unit": "EGP",
        "source": "جدول الكميات - عينة",
    }
    assert counts(boq) == before
    reason = "حساب الكمية في الفئة - عينة"
    r = run(boq, "quantity * rate", save={"name": "amount", "reason": reason}, **request)
    r = r.results[0]
    (n,) = [n for n in numbers(boq, item_of(boq, "03/02")) if n.name == "amount"]
    assert (n.id, n.replaces, n.reason, n.value) == (
        r.number,
        typed,
        reason,
        Decimal("4782060.00"),
    )
    assert explain(boq, typed)["number"]["replaced_by"] == r.number


def test_a_new_formula_replaces_the_old_calculation(boq):
    request = {"item": "03/02", "result": {"unit": "EGP"}}
    old = run(boq, "quantity * rate", save={"name": "amount"}, **request).results[0]
    new = run(
        boq, "round(rate, 0) * quantity", save={"name": "amount", "reason": "عينة"}, **request
    )
    new = new.results[0]
    assert new.value == "4782120.00" and new.calculation != old.calculation
    with boq.read() as c:
        rows = dict(
            c.execute(
                "SELECT id, valid_until FROM calculations WHERE id IN (?, ?)",
                (old.calculation, new.calculation),
            ).fetchall()
        )
        replaces, reason = c.execute(
            "SELECT replaces, reason FROM calculations WHERE id = ?", (new.calculation,)
        ).fetchone()
        audit = c.execute(
            "SELECT action FROM audit WHERE row_id = ? ORDER BY id", (old.calculation,)
        ).fetchall()
    assert rows[old.calculation] is not None and rows[new.calculation] is None
    assert (replaces, reason) == (old.calculation, "عينة")
    assert audit == [("create",), ("replace",)]


def test_a_failed_for_each_saves_nothing(boq):
    add(boq, "03/04", quantity=("10", "m3", None, "boq"))
    before = counts(boq)
    e = refused(amounts, boq)
    assert (e.key, e.values["n"], e.values["name"], e.values["codes"]) == (
        "CALC_MISSING_IN_ITEMS",
        1,
        "rate",
        "03/04",
    )
    assert counts(boq) == before
    assert [n.name for n in numbers(boq, item_of(boq, "03/02"))] == ["quantity", "rate"]


def test_a_refusal_in_for_each_names_the_item(boq):
    add(boq, "03/04", quantity=("10", "m3", None, "boq"), rate=("5", "m2", "EGP", "quote"))
    before = counts(boq)
    e = refused(amounts, boq)
    assert (e.key, e.values["item"]) == ("CALC_RESULT_UNIT", "03/04")
    assert counts(boq) == before


def test_skip_missing_lists_the_skipped(boq):
    add(boq, "03/04", quantity=("10", "m3", None, "boq"))
    out = amounts(boq, skip_missing=True)
    assert [r.code for r in out.results] == ["03/02", "03/03"] and out.skipped == ["03/04"]
    assert out.notes == [copy.fill(copy.CALC_NOTE_SKIPPED, n=1, name="rate", codes="03/04")]


def test_for_each_with_no_match(boq):
    e = refused(run, boq, "quantity * rate", for_each={"code_prefix": "09/"})
    assert (e.key, e.field) == ("CALC_NO_MATCH", "for_each")


def test_needs_a_ledger_input(boq):
    before = counts(boq)
    e = refused(run, boq, "2 * 3", item="03", result={"unit": ""}, save={"name": "factor"})
    assert e.key == "CALC_NEEDS_LEDGER_INPUT"
    assert counts(boq) == before


def test_save_shapes(boq):
    request = {"item": "03/02", "result": {"unit": "EGP"}}
    e = refused(run, boq, "quantity * rate", save={"name": "rate", "reason": "عينة"}, **request)
    assert e.key == "CALC_SAVE_RATE"


def test_cannot_correct_its_own_input(boq):
    e = refused(
        run,
        boq,
        "rate * 1.1",
        item="03/02",
        result={"unit": "EGP/m3"},
        save={"name": "rate", "reason": "عينة"},
    )
    assert (e.key, e.values["name"]) == ("CALC_SAVE_OWN_INPUT", "rate")


def test_totals_over_a_section(boq):
    amounts(boq)
    out = run(
        boq,
        "sum(a)",
        inputs={"a": {"each": {"code_prefix": "03/"}, "name": "amount"}},
        item="03",
        result={"unit": "EGP"},
        save={"name": "amount"},
    )
    r = out.results[0]
    assert (r.value, r.code) == ("4790171.25", "03")
    assert [(name, seq) for name, seq, _ in inputs_of(boq, r.calculation)] == [("a", 0), ("a", 1)]
    first = explain(boq, r.number)["calculation"]["inputs"][0]
    assert first["calculated"] is True and first["source"]["kind"] == "calculation"


def test_unit_definitions_used_are_inputs(boq):
    sheet = add_source(boq, kind="datasheet", title="نشرة الأسمنت - عينة", actor="estimator")
    bag = define_unit(
        boq,
        UnitRequest(symbol="bag", equals="50 kg", source_id=sheet, dated="2026-11-04"),
        actor="estimator",
    )
    add(
        boq,
        "03/05",
        cement_bags=("7", "bag/m3", None, "mix_design"),
        cement_price=("3000", "t", "EGP", "quote"),
    )
    out = run(
        boq,
        "cement_bags * cement_price",
        item="03/05",
        result={"unit": "EGP/m3"},
        save={"name": "cement_cost"},
    )
    r = out.results[0]
    assert (r.value, r.dated) == ("1050.00", "2026-11-04")
    assert ("unit:bag", 0, bag) in inputs_of(boq, r.calculation)


def test_a_unit_only_in_the_result_is_an_input_once(boq):
    sheet = add_source(boq, kind="datasheet", title="نشرة الأسمنت - عينة", actor="estimator")
    bag = define_unit(
        boq,
        UnitRequest(symbol="bag", equals="50 kg", source_id=sheet, dated="2026-11-04"),
        actor="estimator",
    )
    add(boq, "03/05", cement=("350", "kg", None, "mix_design"), bags=("2", "bag", None, "boq"))
    only_result = run(
        boq, 'to(cement, "bag")', item="03/05", result={"unit": "bag"}, save={"name": "need"}
    )
    r = only_result.results[0]
    assert (r.value, r.dated) == ("7.00", "2026-11-04")
    assert ("unit:bag", 0, bag) in inputs_of(boq, r.calculation)
    both = run(boq, "need + bags", item="03/05", result={"unit": "bag"}, save={"name": "total"})
    names = [name for name, _, _ in inputs_of(boq, both.results[0].calculation)]
    assert names.count("unit:bag") == 1


def test_notes_say_what_the_result_is(boq):
    add(boq, "03/06", pieces=("7", "nr", None, "boq"), price=("10", None, "EGP", "quote"))
    out = run(boq, "price / 3 * pieces / pieces", item="03/06", result={"unit": "EGP"})
    assert out.results[0].exact is False
    assert out.notes == [copy.CALC_NOTE_INEXACT, copy.fill(copy.CALC_NOTE_OWN_UNIT, unit="nr")]


def test_explain_pages_a_long_list(tmp_path):
    rec = sample_project(tmp_path)
    for k in range(120):
        add(rec, f"05/{k:03d}", amount=(str(k), None, "EGP", "boq"))
    add(rec, "05", kind="section")
    out = run(
        rec,
        "sum(a)",
        inputs={"a": {"each": {"code_prefix": "05/"}, "name": "amount"}},
        item="05",
        result={"unit": "EGP"},
        save={"name": "amount"},
    )
    number = out.results[0].number
    pages = [explain(rec, number, page=p, per_page=50)["calculation"] for p in (1, 2, 3)]
    assert [p["pages"] for p in pages] == [3, 3, 3] and [p["page"] for p in pages] == [1, 2, 3]
    assert [len(p["inputs"]) for p in pages] == [50, 50, 20]
    assert [len(p["steps"]) for p in pages] == [1, 0, 0]
    assert pages[2]["inputs"][-1]["seq"] == 119
    rec.close()


def test_explain_a_plain_ledger_number(boq):
    with boq.read() as c:
        (rate,) = c.execute("SELECT id FROM numbers WHERE name = 'rate' LIMIT 1").fetchone()
    e = explain(boq, rate)
    assert e["calculation"] is None
    assert (e["source"]["kind"], e["source"]["title"]) == ("quote", "عرض سعر مورد - عينة")
    assert (e["number"]["value"], e["number"]["unit"], e["number"]["currency"]) == (
        "39850.50",
        "m3",
        "EGP",
    )
    assert e["number"]["item"] == {"id": item_of(boq, "03/02"), "code": "03/02", "kind": "boq_item"}


def test_explain_an_unknown_number(boq):
    assert refused(explain, boq, "nope").key == "CALC_NUMBER_NOT_FOUND"


def test_five_hundred_items_in_one_call(tmp_path):
    rec = sample_project(tmp_path)
    with rec.write("estimator") as c:
        rows = [(f"i{k}", f"07/{k:03d}") for k in range(500)]
        c.executemany(
            "INSERT INTO items (id, kind, code, created_at, created_by, updated_at, updated_by)"
            " VALUES (?, 'boq_item', ?, 'x', 'estimator', 'x', 'estimator')",
            rows,
        )
        quote = c.execute("SELECT id FROM sources WHERE kind = 'quote'").fetchone()[0]
        c.executemany(
            "INSERT INTO numbers (id, item_id, name, value, unit, currency, source_id, dated,"
            " recorded_at, recorded_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'x', 'estimator')",
            [(f"q{i}", i, "quantity", "2", "m3", None, quote, DATED) for i, _ in rows]
            + [(f"r{i}", i, "rate", "10.5", "m3", "EGP", quote, DATED) for i, _ in rows],
        )
    out = run(
        rec,
        "quantity * rate",
        for_each={"code_prefix": "07/"},
        result={"unit": "EGP"},
        save={"name": "amount"},
    )
    assert len(out.results) == 500 and {r.value for r in out.results} == {"21.00"}
    assert counts(rec)["calculations"] == 500
    rec.close()


def test_nothing_readable_on_disk(boq):
    add(boq, "03/07", **{"الكمية": ("3", "m3", None, "boq")})
    run(boq, "quantity * rate", item="03/02", result={"unit": "EGP"}, save={"name": "amount"})
    run(boq, "الكمية * 2", item="03/07", result={"unit": "m3"}, save={"name": "double"})
    folder = boq.folder
    for phase in ("open", "closed"):
        blob = b"".join(p.read_bytes() for p in folder.rglob("*") if p.is_file())
        for word in ["quantity * rate", "الكمية", "4782060.00"]:
            assert word.encode() not in blob, (phase, word)
        boq.close()


def test_the_sample_rate_build_up(boq):
    add(
        boq,
        "03/09",
        cement_content=("350", "kg/m3", None, "mix_design"),
        cement_price=("3000", "t", "EGP", "quote"),
        sand=("0.4", "m3/m3", None, "mix_design"),
        gravel=("0.8", "m3/m3", None, "mix_design"),
        sand_price=("250", "m3", "EGP", "quote"),
        gravel_price=("300", "m3", "EGP", "quote"),
        steel=("100", "kg/m3", None, "mix_design"),
        steel_price=("900", "t", "USD", "quote"),
        fx=("50", "USD", "EGP", "exchange_rate"),
        gang=("2400", "day", "EGP", "contract"),
        output=("8", "m3/day", None, "contract"),
    )
    out = run(
        boq,
        "(cement_content * cement_price + sand * sand_price + gravel * gravel_price"
        " + steel * steel_price * fx) * (1 + waste) + gang / output",
        inputs={"waste": {"constant": "5", "unit": "%", "why": "هالك - عينة"}},
        item="03/09",
        result={"unit": "EGP/m3"},
        save={"name": "rate"},
    )
    r = out.results[0]
    assert (r.value, r.unit, r.exact) == ("6484.50", "EGP/m3", True)
    assert out.notes == [copy.fill(copy.CALC_NOTE_OWN_UNIT, unit="day")]
    n = numbers(boq, item_of(boq, "03/09"))[-1]
    assert (n.name, n.value, n.unit, n.currency) == ("rate", Decimal("6484.50"), "m3", "EGP")
    calc = explain(boq, r.number)["calculation"]
    assert "waste" not in {i["name"] for i in calc["inputs"]}
