"""The numbers guard (Plan 4, Task 7): a typed number with no source is marked, never removed.

Synthetic «عينة» data only."""

import json

import pytest

from qsone.engine.numbers_guard import known_values, numbers_in, sourced, unsourced


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


# A number's source, shown (decision 16.3): a number in the reply that exactly one ledger number
# in a tool result gave opens into that number's source card.
N1, N2, N3 = "a" * 32, "b" * 32, "c" * 32


def test_a_reply_number_given_by_one_ledger_number_names_it():
    found = {"candidates": [{"number_id": N1, "value": "39850.50", "currency": "EGP"}]}
    results = [
        f"2 prices found\ndata: {json.dumps(found)}\nsources:\n- prices:own/x | عرض - عينة",
        json.dumps({"number": {"id": N2, "value": "120", "unit": "m3"}, "source": {"id": "s"}}),
    ]
    reply = "الفئة ٣٩٬٨٥٠٫٥٠ ج.م للكمية 120 m3، والإجمالي 7,500 EGP"
    assert sourced(reply, results) == {
        "٣٩٬٨٥٠٫٥٠": {"id": N1, "value": "39850.50"},
        "120": {"id": N2, "value": "120"},
    }


def test_a_value_two_ledger_numbers_share_is_left_unnamed():
    data = [{"number_id": N1, "value": "3950"}, {"number_id": N2, "value": "3950.00"}]
    assert sourced("cement 3,950 EGP", [f"data: {json.dumps(data)}"]) == {}


def test_only_ledger_ids_count_and_calc_inputs_and_outputs_too():
    calc = {
        "inputs": [{"name": "rate", "number": N3, "value": "14.5"}],
        "output": N1,
        "value": "1740",
    }
    results = [
        f"data: {json.dumps(calc)}",
        "data: " + json.dumps({"number": "03/02", "value": "99.9"}),  # not a ledger id
        "plain text with 450 bags",
    ]
    assert sourced("rate 14.5 EGP, amount 1,740 EGP, 99.9 m, 450 bags", results) == {
        "14.5": {"id": N3, "value": "14.5"},
        "1,740": {"id": N1, "value": "1740"},
    }
