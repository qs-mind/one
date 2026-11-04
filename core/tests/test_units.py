"""Units and currencies: exact conversions, units of their own, project units, currencies apart."""

import decimal
from decimal import Decimal

import pytest

from qsone.calc import CONTEXT
from qsone.calc.currencies import CURRENCIES
from qsone.calc.errors import CalcError
from qsone.calc.units import BUILT_IN, UnitTable

T = UnitTable()
P = T.parse


@pytest.mark.parametrize("text", ["m3", "m^3", "m³", "M3", "م3", "م٣", "م³", "m*m*m", "m m m"])
def test_one_unit_many_spellings(text):
    assert P(text).dims == (("m", 3),) and P(text).factor == 1


@pytest.mark.parametrize(
    "value, frm, to, out",
    [
        ("1500", "mm", "m", "1.5"),
        ("2.5", "t", "kg", "2500"),
        ("1", "m3", "L", "1000"),
        ("3", "h", "min", "180"),
        ("5", "%", "", "0.05"),
        ("1", "ha", "م2", "10000"),
        ("12", "م.ط", "m", "12"),
        ("2", "طن", "كجم", "2000"),
        ("1", "ساعة", "ث", "3600"),
        ("1", "KG", "g", "1000"),
        ("750", "لتر", "m3", "0.75"),
    ],
)
def test_conversions_are_exact(value, frm, to, out):
    assert Decimal(value) * T.ratio(P(frm), P(to)) == Decimal(out)


def test_kg_and_tonnes_cancel_exactly():
    factor, unit = T.simplify(P("kg") * P("EGP/t"))
    assert factor == Decimal("0.001") and T.format(unit) == "EGP"


def test_simplify_cancels_volumes_and_folds_percent():
    factor, unit = T.simplify(P("EGP/L") * P("m3"))
    assert factor == 1000 and T.format(unit) == "EGP"
    factor, unit = T.simplify(P("EGP") * P("%"))
    assert factor == Decimal("0.01") and T.format(unit) == "EGP" and unit.plain is False
    assert T.simplify(P("%") * P("%"))[0] == Decimal("0.0001")


def test_an_inexact_factor_raises_the_flag_in_the_callers_context():
    with decimal.localcontext(CONTEXT) as ctx:
        T.ratio(P("m3"), P("L"))
        assert not ctx.flags[decimal.Inexact]
        T.ratio(P("min"), P("h"))  # 1/60 does not end
        assert ctx.flags[decimal.Inexact]


def test_units_that_do_not_match():
    with pytest.raises(CalcError) as e:
        T.ratio(P("m2"), P("m3"))
    assert e.value.key == "CALC_UNITS_DIFFER" and e.value.values == {"left": "m2", "right": "m3"}


def test_currencies_are_apart():
    assert T.is_currency("EGP") and T.is_currency("SAR") and not T.is_currency("NOS")
    with pytest.raises(CalcError) as e:
        T.ratio(P("EGP"), P("USD"))
    assert e.value.key == "CALC_CURRENCIES_DIFFER" and e.value.values == {
        "left": "EGP",
        "right": "USD",
    }
    assert T.format(T.simplify(P("USD") * P("EGP/USD"))[1]) == "EGP"
    with pytest.raises(CalcError) as e:
        T.ratio(P("EGP/m3"), P("USD/m3"))
    assert e.value.key == "CALC_CURRENCIES_DIFFER"


def test_a_currency_is_three_capitals():
    assert P("egp").dims == (("egp", 1),)  # a unit of its own, not the currency
    assert T.own_units(P("egp")) == ["egp"]


def test_ledger_currencies_count_as_currencies():
    t = UnitTable(currencies={"NOS"})
    assert t.is_currency("NOS") and t.parse("NOS").dims == (("NOS", 1),)
    with pytest.raises(CalcError) as e:
        t.ratio(t.parse("NOS"), t.parse("EGP"))
    assert e.value.key == "CALC_CURRENCIES_DIFFER"


def test_unknown_units_are_their_own():
    assert P("LS") == P("ls") and P("nr").dims == (("nr", 1),)
    assert T.own_units(P("trip/day")) == ["trip", "day"]
    with pytest.raises(CalcError):
        T.ratio(P("nr"), P("item"))


def test_defined_units():
    t = UnitTable(
        {
            "bag": (Decimal(50), "kg", "n1"),
            "sack": (Decimal(2), "bag", "n2"),
            "عدد": (Decimal(1), "nr", "n3"),
        }
    )
    assert t.ratio(t.parse("sack"), t.parse("kg")) == 100
    assert t.ratio(t.parse("عدد"), t.parse("nr")) == 1
    assert t.definitions(t.parse("sack/m3")) == {"sack": "n2", "bag": "n1"}
    assert t.definitions(t.parse("kg")) == {}
    assert t.parse("Bag") == t.parse("bag")  # case is ignored, as for every other unit
    assert t.ratio(t.parse("bag2"), t.parse("kg2")) == 2500


def test_a_defined_symbol_may_end_in_digits():
    t = UnitTable({"C30": (Decimal("2.5"), "t", "n1")})
    assert t.ratio(t.parse("C30"), t.parse("kg")) == 2500
    assert t.format(t.parse("C30^2")) == "C30^2"


@pytest.mark.parametrize(
    "defined, key",
    [
        ({"m": (Decimal(1), "mm", "n")}, "CALC_UNIT_BUILT_IN"),
        ({"KG": (Decimal(1), "g", "n")}, "CALC_UNIT_BUILT_IN"),
        ({"m3": (Decimal(1), "L", "n")}, "CALC_UNIT_BUILT_IN"),
        ({"USD": (Decimal(48), "EGP", "n")}, "CALC_UNIT_CURRENCY"),
        ({"x": (Decimal(48), "EGP", "n")}, "CALC_UNIT_CURRENCY"),
        ({"x": (Decimal(2), "kg/USD", "n")}, "CALC_UNIT_CURRENCY"),
        ({"a": (Decimal(2), "b", "n"), "b": (Decimal(3), "a", "n")}, "CALC_UNIT_LOOP"),
        ({"a": (Decimal(2), "a", "n")}, "CALC_UNIT_LOOP"),
        ({"z": (Decimal(0), "kg", "n")}, "CALC_UNIT_FACTOR"),
        ({"z": (Decimal(-1), "kg", "n")}, "CALC_UNIT_FACTOR"),
        ({"z": (Decimal(12), "", "n")}, "CALC_UNIT_FACTOR"),
        ({"z": (Decimal(2), "kg/", "n")}, "CALC_UNIT_UNREADABLE"),
        ({"a b": (Decimal(2), "kg", "n")}, "CALC_UNIT_UNREADABLE"),
    ],
)
def test_definitions_refused(defined, key):
    with pytest.raises(CalcError) as e:
        UnitTable(defined)
    assert e.value.key == key


def test_a_loop_names_a_symbol_on_the_loop():
    with pytest.raises(CalcError) as e:
        UnitTable(
            {
                "c": (Decimal(1), "a", "n"),
                "a": (Decimal(2), "b", "n"),
                "b": (Decimal(3), "a", "n"),
            }
        )
    assert e.value.values["symbol"] in {"a", "b"}


def test_format_round_trips():
    for text in ["EGP/m3", "kg/m3", "m3/day", "EGP/m3/day", "m2", "", "م3", "EGP/م.ط", "kg·m"]:
        assert T.format(P(text)) == text


def test_format_writes_what_parse_reads():
    for unit in [P("m") / P("s"), P("s").power(-1), P("day") * P("day"), P("nr2"), P("%") * P("%")]:
        assert P(T.format(unit)) == unit
    assert T.format(P("day").power(2)) == "day^2" and T.format(P("s").power(-1)) == "s^-1"


def test_units_combine_by_key():
    assert P("m3") / P("M") == P("m2")
    assert (P("EGP/m3") * P("m3")).dims == (("EGP", 1),)
    assert P("m").power(0).plain and P("").plain and P("%").plain and not P("m").plain


@pytest.mark.parametrize(
    "text",
    ["m3/", "/m", "m^x", "m^99", "m^0", "m//s", "kg-m", "5 kg", "m3^2", "m^3²", "(m)", "m^"],
)
def test_unreadable(text):
    with pytest.raises(CalcError) as e:
        P(text)
    assert e.value.key == "CALC_UNIT_UNREADABLE" and e.value.values == {"unit": text}


def test_built_ins_are_si_only():
    for spelling in ["day", "week", "month", "bag", "ton", "inch", "يوم"]:
        assert spelling not in BUILT_IN and P(spelling).terms[0][0].kind == "own"
    assert {"m", "mm", "cm", "km", "م", "م.ط", "ha", "هكتار", "L", "l", "لتر"} <= set(BUILT_IN)
    assert {
        "g",
        "kg",
        "t",
        "جم",
        "غ",
        "كجم",
        "كغ",
        "طن",
        "s",
        "min",
        "h",
        "ث",
        "دقيقة",
        "ساعة",
    } <= (set(BUILT_IN))
    assert BUILT_IN["ha"] == ("ha", "10000", (("m", 2),)) and BUILT_IN["%"] == ("%", "0.01", ())


def test_currency_list_is_iso_list_one():
    assert {"EGP", "SAR", "AED", "KWD", "OMR", "QAR", "BHD", "USD", "EUR"} <= CURRENCIES
    assert all(len(c) == 3 and c.isascii() and c.isupper() for c in CURRENCIES)
    assert not {"HRK", "VEF", "NOS"} & CURRENCIES  # withdrawn codes and non-codes
