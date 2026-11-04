from decimal import Decimal

import pytest

from qsone.calc.errors import CalcError
from qsone.calc.evaluate import Input, Quantity, evaluate
from qsone.calc.formula import MAX_NODES, parse
from qsone.calc.spec import Rounding
from qsone.calc.units import UnitTable

T = UnitTable()
NO_UNIT = {"en": "no unit", "ar": "من غير وحدة"}


def run(formula, unit=None, rounding=None, table=T, **values):
    """values: name=("120", "m3"), or name=[("1", "EGP"), ...] for a list."""
    inputs = {}
    for name, value in values.items():
        many = isinstance(value, list)
        members = value if many else [value]
        quantities = tuple(Quantity(Decimal(v), table.parse(u)) for v, u in members)
        inputs[name] = Input(name, quantities, many, "ledger")
    return evaluate(
        parse(formula), formula, inputs, table, unit=unit, rounding=rounding or Rounding()
    )


def refused(formula, unit=None, **values) -> CalcError:
    with pytest.raises(CalcError) as e:
        run(formula, unit, **values)
    return e.value


def test_quantity_times_rate():
    e = run("quantity * rate", "EGP", quantity=("120", "m3"), rate=("39850.50", "EGP/m3"))
    assert (e.value, e.exact) == (Decimal("4782060.00"), True)
    assert e.steps[-1]["args"] == [
        {"value": "120", "unit": "m3"},
        {"value": "39850.50", "unit": "EGP/m3"},
    ]
    assert e.steps[-1]["text"] == "quantity * rate" and "factor" not in e.steps[-1]
    assert T.format(e.unit) == "EGP" and e.unrounded == Decimal("4782060.00")
    assert e.rounding == {"places": 2, "mode": "half_up", "from": "4782060.00", "to": "4782060.00"}
    assert e.units == {"m", "EGP"}


def test_decimals_are_exact():
    assert run("a + b", "", a=("0.1", ""), b=("0.2", "")).value == Decimal("0.30")


@pytest.mark.parametrize(
    "mode, x, out",
    [("half_up", "2.665", "2.67"), ("half_even", "2.665", "2.66"), ("up", "2.661", "2.67")]
    + [("down", "2.669", "2.66"), ("half_up", "-2.665", "-2.67"), ("up", "-2.661", "-2.67")],
)
def test_rounding_modes(mode, x, out):
    assert run("a", "", Rounding(places=2, mode=mode), a=(x, "")).value == Decimal(out)


def test_rounding_to_tens_and_no_negative_zero():
    assert f"{run('a', '', Rounding(places=-1), a=('1234.5', '')).value:f}" == "1230"
    assert str(run("-a", "", a=("0", "")).value) == "0.00"
    assert str(run("a", "", a=("-0.001", "")).value) == "0.00"


def test_a_division_that_does_not_end_is_noted():
    e = run("a / 3", "EGP", a=("10", "EGP"))
    assert e.value == Decimal("3.33") and e.exact is False and e.steps[-1]["exact"] is False


def test_rate_build_up_units():
    e = run(
        "c * p + s * sp + gang / output",
        "EGP/m3",
        c=("350", "kg/m3"),
        p=("3000", "EGP/t"),
        s=("0.4", "m3/m3"),
        sp=("250", "EGP/m3"),
        gang=("2400", "EGP/day"),
        output=("8", "m3/day"),
    )
    assert e.value == Decimal("1450.00") and e.exact  # 1050 + 100 + 300
    assert e.steps[0] == {
        "n": 1,
        "text": "c * p",
        "op": "*",
        "args": [{"value": "350", "unit": "kg/m3"}, {"value": "3000", "unit": "EGP/t"}],
        "value": "1050.000",
        "unit": "EGP/m3",
        "factor": "0.001",
        "exact": True,
    }
    assert [s["n"] for s in e.steps] == [1, 2, 3, 4, 5]


def test_percent():
    assert run("a * (1 + w)", "EGP", a=("1000", "EGP"), w=("5", "%")).value == Decimal("1050.00")
    e = run("a * 5% + a * 0", "EGP", a=("1000", "EGP"))
    assert e.value == Decimal("50.00")
    assert e.constants == [
        {"value": "5", "unit": "%", "at": 4},
        {"value": "0", "unit": "", "at": 13},
    ]
    assert run("(a + a)%", "EGP", a=("100", "EGP")).steps[-1]["factor"] == "0.01"


def test_mixed_lengths_add():
    e = run("a + b", "m", a=("1500", "mm"), b=("2", "m"))
    assert e.value == Decimal("3.50") and e.steps[-1]["factor"] == "1000"
    assert run("a + b", "m", a=("1", "م"), b=("2", "M")).steps[-1].get("factor") is None
    # the same unit with its terms in another order converts nothing, so no factor is shown
    e = run("c * p + r", "EGP/m3", c=("350", "kg/m3"), p=("3000", "EGP/t"), r=("1", "EGP/m3"))
    assert e.value == Decimal("1051.00") and "factor" not in e.steps[-1]


def test_exchange_rate():
    assert run("p * fx", "EGP", p=("900", "USD"), fx=("50", "EGP/USD")).value == Decimal("45000.00")


def test_currencies_never_mix():
    e = refused("a + b", "EGP", a=("1", "EGP"), b=("1", "USD"))
    assert e.key == "CALC_CURRENCIES_DIFFER" and (e.values["left"], e.values["right"]) == (
        "EGP",
        "USD",
    )
    assert "EGP/USD" in e.text["en"] and e.field == "formula"
    assert refused('to(p, "EGP")', "EGP", p=("1", "USD")).key == "CALC_CURRENCIES_DIFFER"


def test_units_that_do_not_match_read_in_each_language():
    e = refused("a + 1", "m", a=("2", "m"))
    assert e.key == "CALC_UNITS_DIFFER" and e.values == {"at": 0, "left": "m", "right": NO_UNIT}
    assert "«no unit»" in e.text["en"] and "«من غير وحدة»" in e.text["ar"]
    assert refused("a < b", None, a=("1", "m2"), b=("1", "m3")).key == "CALC_UNITS_DIFFER"


def test_result_unit_is_checked():
    e = refused("q * r", "EGP", q=("120", "m2"), r=("10", "EGP/m3"))
    assert e.key == "CALC_RESULT_UNIT" and e.values["got"] == "EGP/m" and e.field == "result.unit"
    e = refused("a / b", "EGP", a=("1", "EGP"), b=("2", "EGP"))
    assert e.values["got"] == NO_UNIT and "gives no unit, not EGP" in e.text["en"]
    assert "من غير وحدة" in e.text["ar"]
    assert refused("a", "EGP", a=("1", "USD")).key == "CALC_RESULT_UNIT"


def test_the_result_converts_into_the_asked_unit():
    e = run("a", "t", a=("2500", "kg"))
    assert e.value == Decimal("2.50") and T.format(e.unit) == "t"


def test_a_preview_keeps_the_unit_it_found():
    assert T.format(run("q * r", None, q=("2", "m3"), r=("10", "EGP/m3")).unit) == "EGP"


def test_lists():
    costs = [("1", "EGP"), ("2", "EGP"), ("4", "EGP")]
    assert run("sum(l)", "EGP", l=costs).value == Decimal("7.00")
    assert run("avg(l)", "EGP", l=costs).value == Decimal("2.33")
    assert run("min(l)", "EGP", l=costs).value == Decimal("1.00")
    assert run("max(l)", "EGP", l=costs).value == Decimal("4.00")
    e = run("count(l)", "", l=costs)
    assert e.value == Decimal("3.00") and len(e.steps) == 1 and e.steps[0]["count"] == 3
    assert run("sum(l)", "m", l=[("1", "m"), ("500", "mm")]).value == Decimal("1.50")
    e = refused("l * 2", "EGP", l=costs)
    assert e.key == "CALC_LIST_HERE" and e.values["name"] == "l"
    assert refused("l", "EGP", l=costs).key == "CALC_LIST_HERE"
    assert refused("max(l, 1)", "EGP", l=costs).key == "CALC_LIST_HERE"
    assert refused("sum(l)", "EGP", l=[("1", "EGP"), ("1", "m")]).key == "CALC_UNITS_DIFFER"


def test_min_and_max_of_values():
    assert run("max(a - b, 0)", "EGP", a=("5", "EGP"), b=("7", "EGP")).value == Decimal("0.00")
    assert run("min(a, b)", "m", a=("1500", "mm"), b=("2", "m")).value == Decimal("1.50")


def test_round_inside():
    e = run("round(r, 0) * q", "EGP", r=("10.6", "EGP/m3"), q=("2", "m3"))
    assert e.value == Decimal("22.00") and e.exact
    assert run('round(r, 1, "down")', "EGP", r=("1.29", "EGP")).value == Decimal("1.20")
    assert refused("round(r, 1.5)", "EGP", r=("1", "EGP")).key == "CALC_USAGE"
    assert refused("round(r, q)", "EGP", r=("1", "EGP"), q=("1", "m")).key == "CALC_USAGE"


def test_to_converts():
    assert run('to(p, "EGP/t")', "EGP/t", p=("3", "EGP/kg")).value == Decimal("3000.00")
    bag = UnitTable({"bag": (Decimal(50), "kg", "n1")})
    e = run('to(c, "bag/m3")', "bag/m3", table=bag, c=("350", "kg/m3"))
    assert e.value == Decimal("7.00") and "bag" in e.units


def test_if_with_zero():
    formula = "if(a > b, a - b, 0)"
    assert run(formula, "EGP", a=("5", "EGP"), b=("7", "EGP")).value == Decimal("0.00")
    assert run(formula, "EGP", a=("9", "EGP"), b=("7", "EGP")).value == Decimal("2.00")


def test_if_runs_only_the_chosen_branch_but_checks_both():
    e = run("if(b = 0, 0, a / b)", "EGP", a=("5", "EGP"), b=("0", ""))
    assert e.value == Decimal("0.00") and [s["op"] for s in e.steps] == ["=", "if"]
    e = refused("if(a > 0, a, c)", "EGP", a=("1", "EGP"), c=("1", "m"))
    assert e.key == "CALC_UNITS_DIFFER"
    assert refused("if(a, a, a)", "EGP", a=("1", "EGP")).key == "CALC_USAGE"
    assert refused("a > 0", "", a=("1", "EGP")).key == "CALC_USAGE"
    assert refused("(a > 0) * 2", "", a=("1", "EGP")).key == "CALC_USAGE"


def test_pythagoras_and_pi():
    e = run("sqrt(a^2 + b^2)", "m", a=("3", "m"), b=("4", "m"))
    assert (e.value, e.exact) == (Decimal("5.00"), True)
    e = run("pi * d^2 / 4 * L", "m3", d=("0.5", "m"), L=("10", "m"))
    assert e.value == Decimal("1.96") and e.exact is False and e.steps[1]["exact"] is False
    assert run("pi", "").exact is False


def test_powers_and_roots_are_checked():
    assert run("a ^ -2", "", a=("2", "")).value == Decimal("0.25")
    assert refused("a ^ 13", "", a=("2", "")).key == "CALC_POWER"
    assert refused("a ^ b", "", a=("2", ""), b=("2", "")).key == "CALC_POWER"
    assert refused("a ^ 1.5", "", a=("2", "")).key == "CALC_POWER"
    assert refused("sqrt(a)", "", a=("4", "m")).key == "CALC_SQRT"
    assert refused("sqrt(a)", "", a=("-4", "")).key == "CALC_SQRT"


def test_divide_by_zero():
    e = refused("a / b", "EGP", a=("1", "EGP"), b=("0", ""))
    assert e.key == "CALC_DIVIDE_BY_ZERO" and e.values["text"] == "a / b"
    assert refused("a ^ -1", "", a=("0", "")).key == "CALC_DIVIDE_BY_ZERO"
    assert run("a ^ 0", "", a=("0", "")).value == 1
    assert refused("avg(l) / 0", "", l=[("0", "")]).key == "CALC_DIVIDE_BY_ZERO"


def test_huge_values():
    big = "1" + "0" * 40
    e = run("a ^ 2", "", a=(big, ""))
    assert e.exact and e.value == Decimal(big) ** 2
    e = refused("a ^ 12", "", a=("1" + "0" * 100_000, ""))
    assert e.key == "CALC_TOO_BIG" and e.values["text"] == "a ^ 12"
    e = run("a * a", "", a=("1" + "0" * 49, ""))  # 99 digits after rounding: more than 50
    assert e.exact and f"{e.value:f}" == "1" + "0" * 98 + ".00"


def test_result_keeps_the_asked_spelling():
    assert UnitTable().format(run("q * 1", "م3", q=("2", "m3")).unit) == "م3"


def test_unknown_names():
    e = refused("quantity * rat", "EGP", quantity=("1", "m3"), rate=("1", "EGP/m3"))
    assert e.key == "CALC_UNKNOWN_NAME" and e.values == {"name": "rat", "names": "quantity, rate"}
    assert refused("x", "").values["names"] == {"en": "none", "ar": "مفيش"}


def test_the_largest_trees_need_no_recursion():
    e = run("+".join(["a"] * 1000), "m", a=("1", "m"))  # 1999 nodes, 999 deep
    assert e.value == Decimal("1000.00") and len(e.steps) == 999
    e = run("-" * (MAX_NODES - 1) + "a", "m", a=("1", "m"))  # 2000 nodes, all one chain
    assert e.value == Decimal("-1.00") and len(e.steps) == MAX_NODES - 1
