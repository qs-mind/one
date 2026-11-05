"""The ledger side of the engine: project units, items by id or code, selectors and inputs."""

from decimal import Decimal

import pytest

from qsone import copy
from qsone.calc.errors import CalcError
from qsone.calc.formula import names, parse
from qsone.calc.resolve import (
    UNIT_KIND,
    current_number,
    current_of,
    define_unit,
    find_item,
    ledger_columns,
    ledger_unit,
    resolve,
    select,
    unit_table,
)
from qsone.calc.spec import CalcRequest, Selector, UnitRequest
from qsone.calc.units import UnitTable
from qsone.records.ledger import add_source, correct_number, numbers, record_number
from qsone.records.project import RecordsError
from tests.calc_samples import DATED, add, sample_project, source_id

T = UnitTable()


@pytest.fixture
def rec(tmp_path):
    rec = sample_project(tmp_path)
    yield rec
    rec.close()


@pytest.fixture
def source(rec):
    return add_source(
        rec, kind="datasheet", title="نشرة الأسمنت - عينة", dated=DATED, actor="estimator"
    )


@pytest.fixture
def boq(rec):
    """03/02 with a quantity and a rate; 03/03 with a quantity only."""
    add(rec, "03/02", quantity=("120", "m3", None, "boq"), rate=("39850.50", "m3", "EGP", "quote"))
    add(rec, "03/03", quantity=("45", "m2", None, "boq"))
    return rec


def unit(rec, symbol, equals, source, reason=None):
    req = UnitRequest(symbol=symbol, equals=equals, source_id=source, dated=DATED, reason=reason)
    return define_unit(rec, req, actor="estimator")


def table(rec) -> UnitTable:
    with rec.read() as c:
        return unit_table(c)


def run(rec, formula, *, item=None, **request):
    req = CalcRequest(formula=formula, item=item, **request)
    with rec.read() as c:
        t = unit_table(c)
        target = find_item(c, item) if item else None
        return resolve(c, req, t, item=target, used_names=names(parse(formula)))


def refused(call, *args, **kwargs) -> CalcError:
    with pytest.raises(CalcError) as e:
        call(*args, **kwargs)
    return e.value


def number_id(rec, code, name) -> str:
    with rec.read() as c:
        return current_number(c, find_item(c, code)["id"], name)["id"]


def row_counts(rec) -> tuple:
    with rec.read() as c:
        return tuple(
            c.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
            for t in ("items", "numbers", "audit")
        )


# Unit definitions.


def test_a_unit_definition_lives_in_the_ledger(rec, source):
    n = unit(rec, "bag", "50 kg", source)
    t = table(rec)
    assert t.ratio(t.parse("bag"), t.parse("kg")) == 50
    assert t.definitions(t.parse("bag")) == {"bag": n}
    with rec.read() as c:
        item, name, value, unit_text, src = c.execute(
            "SELECT i.kind, n.name, n.value, n.unit, n.source_id FROM numbers n"
            " JOIN items i ON i.id = n.item_id WHERE n.id = ?",
            (n,),
        ).fetchone()
    assert (item, name, value, unit_text, src) == (UNIT_KIND, "equals", "50", "kg", source)


def test_a_chain_of_definitions(rec, source):
    unit(rec, "bag", "50 kg", source)
    unit(rec, "sack", "2 bag", source)
    t = table(rec)
    assert t.ratio(t.parse("sack"), t.parse("t")) == Decimal("0.1")


def test_arabic_digits_in_a_definition(rec, source):
    unit(rec, "شيكارة", "٥٠ كجم", source)
    t = table(rec)
    assert t.ratio(t.parse("شيكارة"), t.parse("kg")) == 50


def test_redefining_needs_a_reason_and_keeps_the_old(rec, source):
    rec.clock = lambda: "2026-11-02T08:00:00.000000+00:00"
    first = unit(rec, "bag", "50 kg", source)
    rec.clock = lambda: "2026-11-03T08:00:00.000000+00:00"
    with pytest.raises(RecordsError) as e:
        unit(rec, "bag", "25 kg", source)
    assert e.value.text == copy.CORRECTION_NEEDS_REASON
    second = unit(rec, "bag", "25 kg", source, reason="شيكارة 25 كجم - عينة")
    t = table(rec)
    assert t.ratio(t.parse("bag"), t.parse("kg")) == 25 and t.definitions(t.parse("bag")) == {
        "bag": second
    }
    with rec.read() as c:
        assert current_of(c, first) == second
        (unit_item,) = c.execute("SELECT item_id FROM numbers WHERE id = ?", (first,)).fetchone()
        assert (
            c.execute("SELECT count(*) FROM items WHERE kind = ?", (UNIT_KIND,)).fetchone()[0] == 1
        )
    assert numbers(rec, unit_item, as_of="2026-11-02")[-1].value == Decimal("50")
    assert numbers(rec, unit_item)[-1].value == Decimal("25")


@pytest.mark.parametrize(
    "equals, key",
    [
        ("48 EGP", "CALC_UNIT_CURRENCY"),
        ("2 EGP/m3", "CALC_UNIT_CURRENCY"),
        ("0 kg", "CALC_UNIT_FACTOR"),
        ("-5 kg", "CALC_UNIT_FACTOR"),
        ("kg", "CALC_UNIT_FACTOR"),
        ("50", "CALC_UNIT_FACTOR"),
        ("50 %", "CALC_UNIT_FACTOR"),
        ("1,000 kg", "CALC_UNIT_FACTOR"),
        ("50 kg/", "CALC_UNIT_UNREADABLE"),
    ],
)
def test_definition_refusals(rec, source, equals, key):
    before = row_counts(rec)
    assert refused(unit, rec, "bag", equals, source).key == key
    assert row_counts(rec) == before


@pytest.mark.parametrize(
    "symbol, key",
    [
        ("m", "CALC_UNIT_BUILT_IN"),
        ("M", "CALC_UNIT_BUILT_IN"),
        ("KG", "CALC_UNIT_BUILT_IN"),
        ("طن", "CALC_UNIT_BUILT_IN"),
        ("USD", "CALC_UNIT_CURRENCY"),
        ("usd", "CALC_UNIT_CURRENCY"),
    ],
)
def test_built_in_and_currency_symbols_cannot_be_defined(rec, source, symbol, key):
    assert refused(unit, rec, symbol, "50 kg", source).key == key


def test_a_symbol_differing_only_in_case_is_refused(rec, source):
    unit(rec, "bag", "50 kg", source)
    before = row_counts(rec)
    e = refused(unit, rec, "Bag", "25 kg", source, reason="عينة")
    assert (e.key, e.values["existing"], e.field) == ("CALC_UNIT_CASE", "bag", "symbol")
    assert "bag" in e.text["ar"] and "Bag" in e.text["en"]
    assert row_counts(rec) == before


def test_a_loop_is_refused_and_nothing_written(rec, source):
    unit(rec, "a", "2 kg", source)
    unit(rec, "b", "3 a", source)
    before = row_counts(rec)
    assert refused(unit, rec, "a", "4 b", source, reason="عينة").key == "CALC_UNIT_LOOP"
    assert row_counts(rec) == before


def test_a_ledger_currency_is_a_currency(rec, source):
    add(rec, "P1", price=("5", None, "QQQ", "quote"))
    assert table(rec).is_currency("QQQ") and not T.is_currency("QQQ")
    assert refused(unit, rec, "QQQ", "1 kg", source).key == "CALC_UNIT_CURRENCY"
    assert refused(unit, rec, "x", "1 QQQ", source).key == "CALC_UNIT_CURRENCY"


# How a ledger number's unit is read, and saved.


def test_ledger_unit_rule():
    assert ledger_unit("rate", "m3", "EGP") == "EGP/m3"
    assert ledger_unit("amount", "LS", "EGP") == "EGP"
    assert ledger_unit("quantity", "m3", None) == "m3"
    assert ledger_unit("exchange_rate", "EGP/USD", None) == "EGP/USD"
    assert ledger_unit("waste", "%", None) == "%"
    assert ledger_unit("price", None, "USD") == "USD"
    assert ledger_unit("factor", None, None) == ""
    # A compound unit stays per the whole unit.
    assert ledger_unit("rate", "m3·day", "EGP") == "EGP/m3/day"


@pytest.mark.parametrize(
    "name, text, out",
    [
        ("rate", "EGP/m3", ("m3", "EGP")),
        ("rate", "EGP/m3/day", ("m3·day", "EGP")),
        ("amount", "EGP", (None, "EGP")),
        ("quantity", "m3", ("m3", None)),
        ("escalated", "EGP", (None, "EGP")),
        ("exchange_rate", "EGP/USD", ("EGP/USD", None)),
        ("cement_content", "kg/m3", ("kg/m3", None)),
        ("factor", "", (None, None)),
    ],
)
def test_ledger_columns_for_saving(name, text, out):
    assert ledger_columns(name, T.parse(text), T) == out
    unit_text, currency = out
    assert ledger_unit(name, unit_text, currency) == text


@pytest.mark.parametrize(
    "name, text, key",
    [
        ("rate", "m3", "CALC_SAVE_RATE"),
        ("rate", "EGP", "CALC_SAVE_RATE"),
        ("rate", "EGP/USD", "CALC_SAVE_RATE"),
        ("amount", "EGP/m3", "CALC_SAVE_AMOUNT"),
        ("amount", "m3", "CALC_SAVE_AMOUNT"),
        ("quantity", "EGP", "CALC_SAVE_QUANTITY"),
    ],
)
def test_ledger_columns_refusals(name, text, key):
    e = refused(ledger_columns, name, T.parse(text), T)
    assert e.key == key and e.values["unit"] == text


# Items, numbers and selectors.


def test_items_by_id_or_code(rec, source):
    one = add(rec, "03/02")
    two = add(rec, "03/02")
    other = add(rec, "04/01")
    unit(rec, "bag", "50 kg", source)
    with rec.read() as c:
        assert find_item(c, one)["id"] == one
        assert find_item(c, "04/01") == {
            "id": other,
            "kind": "boq_item",
            "code": "04/01",
            "fields": {},
        }
        e = refused(find_item, c, "03/02")
        assert e.key == "CALC_ITEM_AMBIGUOUS" and e.values["n"] == 2
        assert one in e.values["choices"] and two in e.values["choices"]
        assert refused(find_item, c, "05/01").key == "CALC_ITEM_NOT_FOUND"
        assert refused(find_item, c, "bag").key == "CALC_ITEM_NOT_FOUND"


def test_a_corrected_number_names_the_current_one(boq):
    old = number_id(boq, "03/02", "rate")
    mid = correct_number(
        boq, old, value="40000", reason="عرض جديد - عينة", source_id=source_id(boq, "quote"),
        dated=DATED, actor="estimator",
    )  # fmt: skip
    new = correct_number(
        boq, mid, value="41000", reason="عرض أحدث - عينة", source_id=source_id(boq, "quote"),
        dated=DATED, actor="estimator",
    )  # fmt: skip
    with boq.read() as c:
        assert current_of(c, old) == new and current_of(c, new) == new
    e = refused(run, boq, "r", inputs={"r": {"number": old}})
    assert (e.key, e.values["now"], e.field) == ("CALC_NUMBER_OLD", new, "inputs.r")
    e = refused(run, boq, "r", inputs={"r": {"numbers": [new, mid]}})
    assert (e.key, e.values["now"]) == ("CALC_NUMBER_OLD", new)
    assert refused(run, boq, "r", inputs={"r": {"number": "x" * 32}}).key == "CALC_NUMBER_NOT_FOUND"


def test_a_newer_number_of_one_name_is_the_one_read(boq):
    with boq.read() as c:
        item = find_item(c, "03/02")["id"]
    record_number(
        boq, item_id=item, name="rate", value="1", unit="m3", currency="EGP",
        source_id=source_id(boq, "quote"), dated=DATED, actor="estimator",
    )  # fmt: skip
    r = run(boq, "r", inputs={"r": {"item": "03/02", "name": "rate"}})
    assert [q.value for q in r.inputs["r"].values] == [Decimal("1")]


def test_two_current_numbers_of_one_name(boq):
    """Records written before 5 Nov 2026 can hold two; the engine still names them."""
    with boq.read() as c:
        item = find_item(c, "03/02")["id"]
        [row] = c.execute(
            "SELECT * FROM numbers WHERE item_id = ? AND name = 'rate'", (item,)
        ).fetchall()
    with boq.write("estimator") as c:
        c.execute(
            "INSERT INTO numbers VALUES (" + ", ".join("?" * len(row)) + ")",
            ("e" * 32, *row[1:3], "1", *row[4:]),
        )
    e = refused(run, boq, "r", inputs={"r": {"item": "03/02", "name": "rate"}})
    assert (e.key, e.values["n"], e.values["item"]) == ("CALC_NUMBER_AMBIGUOUS", 2, "03/02")
    assert refused(run, boq, "rate", item="03/02").key == "CALC_NUMBER_AMBIGUOUS"


def test_selector_kind_prefix_and_fields(rec, source):
    ground = {"section": "03", "floor": "الدور الأرضي"}
    add(rec, "03/03", fields=ground)
    add(rec, "03/02", fields=ground)
    add(rec, "04/01", fields={"section": "04", "floor": "الدور الأول", "count": 2, "done": True})
    add(rec, "03", kind="section")
    unit(rec, "bag", "50 kg", source)

    def codes(**sel):
        with rec.read() as c:
            return [i["code"] for i in select(c, Selector(**sel))]

    assert codes(code_prefix="03/") == ["03/02", "03/03"]
    assert codes(where={"floor": "الدور الأرضي"}) == ["03/02", "03/03"]
    assert codes(kind="section") == ["03"]
    assert codes(kind="boq_item", where={"section": "04", "count": 2, "done": True}) == ["04/01"]
    assert codes(where={"count": "2"}) == []
    assert codes(kind=UNIT_KIND) == [] and codes(code_prefix="b") == []
    with rec.read() as c:
        e = refused(select, c, Selector(where={'a"b': "x"}))
    assert e.key == "CALC_REQUEST_SHAPE" and e.field == "where"


def test_missing_members_listed_or_skipped(boq):
    add(boq, "03/04", amount=("100", None, "EGP", "quote"))
    each = {"a": {"each": {"code_prefix": "03/"}, "name": "amount"}}
    e = refused(run, boq, "sum(a)", inputs=each)
    assert e.key == "CALC_MISSING_IN_ITEMS" and e.values["n"] == 2
    assert e.values["codes"] == "03/02, 03/03" and e.field == "inputs.a"
    r = run(boq, "sum(a)", inputs=each, skip_missing=True)
    assert r.skipped == ["03/02", "03/03"]
    assert r.inputs["a"].is_list and [q.value for q in r.inputs["a"].values] == [Decimal(100)]
    assert r.used == [("a", 0, number_id(boq, "03/04", "amount"))]
    assert r.request["inputs"]["a"] == {"each": {"code_prefix": "03/"}, "name": "amount"}
    e = refused(run, boq, "sum(a)", inputs={"a": {"each": {"code_prefix": "09/"}, "name": "x"}})
    assert e.key == "CALC_NO_MATCH" and "09/" in e.text["en"]


def test_each_lists_every_member_in_order(boq):
    add(boq, "03/04", quantity=("10", "m3", None, "boq"))
    r = run(boq, "sum(q)", inputs={"q": {"each": {"code_prefix": "03/"}, "name": "quantity"}})
    assert [(n, s) for n, s, _ in r.used] == [("q", 0), ("q", 1), ("q", 2)]
    assert [T.format(q.unit) for q in r.inputs["q"].values] == ["m3", "m2", "m3"]


def test_bare_names_read_the_item(boq):
    r = run(boq, "quantity * rate", item="03/02")
    assert r.from_item == ["quantity", "rate"]
    q, p = r.inputs["quantity"], r.inputs["rate"]
    assert (q.values[0].value, T.format(q.values[0].unit), q.origin) == (
        Decimal(120),
        "m3",
        "ledger",
    )
    assert (p.values[0].value, T.format(p.values[0].unit)) == (Decimal("39850.50"), "EGP/m3")
    with boq.read() as c:
        item = find_item(c, "03/02")["id"]
    assert r.request["item"] == item
    assert r.request["inputs"] == {
        "quantity": {"number": number_id(boq, "03/02", "quantity")},
        "rate": {"number": number_id(boq, "03/02", "rate")},
    }
    assert r.dated == DATED and r.skipped == []


def test_an_unknown_name_lists_what_there_is(boq):
    e = refused(run, boq, "quantity * rat", item="03/02")
    assert e.text == copy.fill(copy.CALC_UNKNOWN_NAME, name="rat", names="quantity, rate")
    assert e.field == "formula"
    e = refused(run, boq, "q * rate", inputs={"q": {"item": "03/02", "name": "quantity"}})
    assert (e.key, e.values["names"]) == ("CALC_UNKNOWN_NAME", "q")


def test_slot_and_list_inputs(boq):
    q, r = number_id(boq, "03/02", "quantity"), number_id(boq, "03/03", "quantity")
    out = run(
        boq, "a * sum(b)",
        inputs={"a": {"item": "03/02", "name": "rate"}, "b": {"numbers": [q, r]}},
    )  # fmt: skip
    assert not out.inputs["a"].is_list and out.inputs["b"].is_list
    assert out.used == [("a", 0, number_id(boq, "03/02", "rate")), ("b", 0, q), ("b", 1, r)]
    assert out.request["inputs"]["a"] == {"number": number_id(boq, "03/02", "rate")}
    assert out.request["inputs"]["b"] == {"numbers": [q, r]}
    assert refused(run, boq, "a", inputs={"a": {"item": "09/09", "name": "x"}}).field == "inputs.a"


def test_constants_are_exact_and_plain(boq):
    r = run(boq, "w", inputs={"w": {"constant": "٥", "unit": "%", "why": "هالك - عينة"}})
    w = r.inputs["w"]
    assert (w.values[0].value, T.format(w.values[0].unit), w.origin) == (
        Decimal(5),
        "%",
        "constant",
    )
    assert r.request["inputs"]["w"] == {"constant": "5", "unit": "%", "why": "هالك - عينة"}
    assert r.used == [] and r.dated is None
    e = refused(run, boq, "k", inputs={"k": {"constant": "1,000", "why": "عينة"}})
    assert e.text == copy.NUMBER_NOT_EXACT and e.field == "inputs.k"


def test_dated_is_the_newest_input(boq):
    with boq.read() as c:
        item = find_item(c, "03/03")["id"]
    record_number(
        boq, item_id=item, name="rate", value="180.25", unit="m2", currency="EGP",
        source_id=source_id(boq, "quote"), dated="2026-10-01", actor="estimator",
    )  # fmt: skip
    assert run(boq, "rate", item="03/03").dated == "2026-10-01"
    assert run(boq, "quantity * rate", item="03/03").dated == DATED


def test_unit_definitions_used_are_inputs(rec, source):
    rec.clock = lambda: "2026-11-02T08:00:00.000000+00:00"
    bag = unit(rec, "bag", "50 kg", source)
    sack = unit(rec, "sack", "2 bag", source)
    add(rec, "03/02", cement=("7", "sack/m3", None, "mix_design"))
    r = run(rec, "cement", item="03/02")
    assert T.format(r.inputs["cement"].values[0].unit) == "sack/m3"
    assert r.used[1:] == [("unit:sack", 0, sack), ("unit:bag", 0, bag)]
    with rec.read() as c:
        t = unit_table(c)
    assert r.inputs["cement"].values[0].unit.factor == t.parse("sack/m3").factor == 100


def test_the_resolved_request_is_a_request_again(boq):
    r = run(
        boq, "quantity * rate * (1 + w)", item="03/02", result={"unit": "EGP"},
        inputs={"w": {"constant": "5", "unit": "%", "why": "هالك - عينة"}},
        save={"name": "amount", "reason": "x"},
    )  # fmt: skip
    again = CalcRequest(**r.request)
    assert again.item == r.request["item"] and again.save is None and again.for_each is None
    assert run(boq, **r.request).request == r.request
