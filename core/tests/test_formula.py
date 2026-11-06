import random
from pathlib import Path

import pytest

import qsone.calc
from qsone.calc import formula
from qsone.calc.errors import CalcError
from qsone.calc.formula import CONSTANTS, FUNCTIONS, MAX_DEPTH, MAX_NODES, names, parse, show
from qsone.calc.spec import RESERVED_NAMES


def refused(text: str) -> CalcError:
    with pytest.raises(CalcError) as e:
        parse(text)
    assert e.value.field == "formula"
    return e.value


def test_precedence():
    assert show(parse("a + b * c ^ 2 ^ 2")) == "(a + (b * (c ^ (2 ^ 2))))"
    assert show(parse("a - b - c")) == "((a - b) - c)"
    assert show(parse("-a ^ 2")) == "(-(a ^ 2))"
    assert show(parse("a ^ -b ^ c")) == "(a ^ (-(b ^ c)))"
    assert show(parse("a + b < c * d")) == "((a + b) < (c * d))"


def test_percent_and_unary():
    assert show(parse("-a * 5%")) == "((-a) * (5 %))"
    assert show(parse("(a + b)% ^ 2")) == "(((a + b) %) ^ 2)"


def test_unicode_operators_read_as_ascii():
    assert show(parse("a × b ÷ c − d")) == show(parse("a * b / c - d"))
    assert show(parse("a · b")) == show(parse("a * b"))
    for uni, ascii_ in [("≤", "<="), ("≥", ">="), ("≠", "!="), ("==", "=")]:
        assert show(parse(f"a {uni} b")) == show(parse(f"a {ascii_} b"))
    assert show(parse("max(a، b)")) == show(parse("max(a, b)"))


def test_arabic_digits_and_names():
    tree = parse("الكمية * ٣٩٨٥٠٫٥٠")
    assert names(tree) == {"الكمية"} and tree.right.text == "39850.50"
    assert parse("۱۲۳").text == "123"
    assert names(parse("x٣ + ب_2")) == {"x٣", "ب_2"}


def test_spans_cover_the_text():
    text = "(a + b) * round(c, 2)"
    tree = parse(text)
    assert text[tree.start : tree.end] == text
    assert text[tree.left.start : tree.left.end] == "(a + b)"
    assert text[tree.right.start : tree.right.end] == "round(c, 2)"


def test_calls_and_text():
    assert show(parse('round(to(p, "EGP/t"), 2, "up")')) == '(round (to p "EGP/t") 2 "up")'
    assert show(parse("round(r, 0)")) == "(round r 0)"
    assert show(parse("to(x, 'م3')")) == '(to x "م3")'
    assert show(parse("max(a, b, c) + min(l) + if(a > b, a, 0)")) == (
        "(((max a b c) + (min l)) + (if (a > b) a 0))"
    )


def test_errors_name_the_place():
    e = refused("a * (b + c")
    assert e.key == "CALC_UNEXPECTED" and e.values["at"] == 10
    # The text counts characters as a person does, from 1.
    e = refused("a ! b")
    assert e.values["at"] == 2 and e.text["en"].startswith("At character 3,")
    assert e.text["ar"].startswith("عند الحرف 3،") and str(e).startswith("At character 3,")


@pytest.mark.parametrize(
    "text, key, at",
    [
        ("1,000 * a", "CALC_UNEXPECTED", 1),
        ("1e3 * a", "CALC_UNEXPECTED", 1),
        ("a +", "CALC_UNEXPECTED", 3),
        ("a b", "CALC_UNEXPECTED", 2),
        ("(a", "CALC_UNEXPECTED", 2),
        ("a)", "CALC_UNEXPECTED", 1),
        ("round(a)", "CALC_USAGE", 0),
        ('a + "m"', "CALC_UNEXPECTED", 4),
        ("foo(a)", "CALC_UNKNOWN_FUNCTION", 0),
    ],
)
def test_refusals_say_what_was_expected(text, key, at):
    e = refused(text)
    assert (e.key, e.values["at"]) == (key, at)
    if key == "CALC_UNEXPECTED":
        assert set(e.values["expected"]) == {"en", "ar"}
        assert e.values["expected"]["en"] in e.text["en"]
        assert e.values["expected"]["ar"] in e.text["ar"]


def test_the_number_hints():
    assert "1,000" in refused("1,000 * a").values["expected"]["en"]
    assert "1e3" in refused("1e3 * a").values["expected"]["en"]
    assert "1e3" not in refused("a b").values["expected"]["en"]


def test_arabic_refusals_hold_no_english_words():
    for text in [
        "a b",
        "a +",
        "(a",
        "max(a b)",
        '"m',
        "a ! b",
        "1,000",
        "2m",
        'a + "m"',
        "round(a)",
    ]:
        ar = refused(text).text["ar"]
        assert not any(
            w in ar
            for w in [
                "operator",
                "number",
                "name",
                "bracket",
                "end",
                "quote",
                "list",
                "places",
                "unit",
            ]
        ), ar


def test_the_end_reads_in_each_language():
    e = refused("a +")
    assert e.values["found"]["en"] in e.text["en"] and e.values["found"]["ar"] in e.text["ar"]


@pytest.mark.parametrize(
    "text, fn",
    [
        ("sum()", "sum"),
        ("count()", "count"),
        ("abs(a, b)", "abs"),
        ("to(x)", "to"),
        ("to(x, y)", "to"),
        ('round(x, 2, "sideways")', "round"),
        ('round(x, "up")', "round"),
        ('sqrt("m")', "sqrt"),
        ("if(a > b, a)", "if"),
        ("sum + 1", "sum"),
    ],
)
def test_function_usage_is_checked_while_parsing(text, fn):
    e = refused(text)
    assert (
        e.key == "CALC_USAGE" and e.values["fn"] == fn and e.values["usage"]["en"] == FUNCTIONS[fn]
    )
    assert e.values["usage"]["en"] in e.text["en"] and e.values["usage"]["ar"] in e.text["ar"]


def test_text_is_only_a_unit_or_a_mode():
    assert refused('"EGP"').key == "CALC_UNEXPECTED"
    assert refused('round("a" + 1, 2)').key == "CALC_UNEXPECTED"
    assert refused('"unterminated').values["at"] == 0
    assert refused('to(x, "' + "m" * 65 + '")').key == "CALC_UNEXPECTED"
    assert show(parse('to(x, "' + "m" * 64 + '")')).count("m") == 64


def test_odd_characters_are_refused_where_they_stand():
    for text, at in [
        ("a ! b", 2),
        ("a & b", 2),
        ("1.", 1),
        (".5", 0),
        ("a < b < c", 6),
        ("a ٬ b", 2),
    ]:
        e = refused(text)
        assert (e.key, e.values["at"]) == ("CALC_UNEXPECTED", at), text


def test_limits():
    assert refused("a" * 4001).key == "CALC_TOO_LONG"
    parse("(" * MAX_DEPTH + "a" + ")" * MAX_DEPTH)
    assert refused("(" * (MAX_DEPTH + 1) + "a" + ")" * (MAX_DEPTH + 1)).key == "CALC_TOO_DEEP"
    assert refused("abs(" * (MAX_DEPTH + 1) + "a" + ")" * (MAX_DEPTH + 1)).key == "CALC_TOO_DEEP"
    assert refused("+".join(["a"] * 1001)).key == "CALC_TOO_DEEP"  # 2001 nodes


def test_the_largest_trees_need_no_recursion():
    long_sum = parse("+".join(["a"] * 1000))  # 1999 nodes, 999 deep
    assert names(long_sum) == {"a"} and show(long_sum).count("(") == 999
    signs = parse("-" * (MAX_NODES - 1) + "a")  # 2000 nodes, all one chain
    assert names(signs) == {"a"} and show(signs).endswith("a" + ")" * (MAX_NODES - 1))


def test_names_skips_pi_and_functions():
    assert names(parse("sum(x) + y * pi")) == {"x", "y"}


def test_dunder_is_only_a_name():
    assert names(parse("__import__ + 1")) == {"__import__"}
    assert refused('__import__("os")').key == "CALC_UNKNOWN_FUNCTION"


def test_functions_and_constants_are_the_reserved_names():
    assert set(FUNCTIONS) | CONSTANTS == RESERVED_NAMES


def test_fuzz_only_parses_or_refuses():
    rnd = random.Random(3)
    alphabet = list("ab_ 0123456789.,()+-*/^%<>=!\"'×÷−٣٫،") + [
        "sum",
        "round",
        "if",
        "pi",
        "الكمية",
    ]
    for _ in range(3000):
        text = "".join(rnd.choice(alphabet) for _ in range(rnd.randint(0, 40)))
        try:
            parse(text)
        except CalcError:
            pass


def test_the_calc_package_never_runs_code():
    src = "\n".join(
        p.read_text(encoding="utf-8") for p in Path(qsone.calc.__file__).parent.glob("*.py")
    )
    for banned in [
        "eval(",
        "exec(",
        "compile(",
        "import ast",
        "from ast",
        "__import__",
        "getattr(",
        "float(",
    ]:
        assert banned not in src, banned
    assert formula.__file__.endswith("formula.py")
