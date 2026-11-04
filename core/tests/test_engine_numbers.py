"""The numbers guard (Plan 4, Task 7): a typed number with no source is marked, never removed.

Synthetic «عينة» data only."""

import pytest

from qsone.engine.numbers_guard import known_values, numbers_in, unsourced


@pytest.mark.parametrize(
    "text, known, marked",
    [
        ("rate 39,850.50 EGP for 120 m3, total 7,500 EGP", {"39850.50", "120"}, ["7,500"]),
        ("السعر ٣٩٨٥٠٫٥٠ ج.م", {"39850.50"}, []),
        ("see page 12, clause 14.2, item 03/02, 2 specialists", set(), []),
    ],
)
def test_numbers_guard(text, known, marked):
    assert unsourced(text, known) == marked


def test_what_counts_as_a_number():
    text = "3 items, 12 floors, 2.5 m, 450 bags, 5% waste, 8 EGP, 120m3, dated 2026-11-05, in 2026"
    assert numbers_in(text) == ["2.5", "450", "5", "8", "120"]


def test_arabic_numbers_are_kept_as_written():
    text = "الكمية ١٢٠ م٣ والسعر ٣٩٬٨٥٠٫٥٠ جنيه، البند ٠٣/٠٢، صفحة ١٤٫٢"
    assert numbers_in(text) == ["١٢٠", "٣٩٬٨٥٠٫٥٠"]
    assert unsourced(text, {"120"}) == ["٣٩٬٨٥٠٫٥٠"]


def test_a_currency_before_the_number_counts():
    assert numbers_in("EGP 75 and $40 and 7 days") == ["75", "40", "7"]


def test_known_values_are_every_number_in_the_tool_results():
    results = ['{"value": "39850.50", "unit": "m3"}', "الكمية ١٢٠ م٣، والإجمالي 7,500"]
    known = known_values(results)
    assert {"39850.5", "120", "7500"} <= known
    assert unsourced("39,850.5 EGP for 120 m3 is 7,500.00 EGP", known) == []


def test_a_number_is_marked_once_in_order():
    assert unsourced("4,200 EGP, then 1.5 m, then 4,200 EGP again", set()) == ["4,200", "1.5"]
