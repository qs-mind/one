"""The words the engineer reads (R4, R17): Arabic counts in their own forms, Arabic commas in
Arabic lists, one page said as one page, and never a stop after a blank that ends its own
sentence. Synthetic «عينة» data only."""

from qsone import copy
from qsone.tools.files import _doing


def test_arabic_counts_take_their_own_forms():
    said = {n: copy.counted(n, copy.ITEMS)["ar"] for n in (1, 2, 4, 10, 11, 100, 103)}
    assert said == {
        1: "بند واحد",
        2: "بندين",
        4: "4 بنود",
        10: "10 بنود",
        11: "11 بند",
        100: "100 بند",
        103: "103 بنود",
    }
    assert copy.counted(1, copy.ROWS)["en"] == "1 row"
    assert copy.counted(3, copy.HEADINGS)["en"] == "3 headings"


def test_the_boq_card_counts_read_naturally():
    counts = {"items": copy.counted(1, copy.ITEMS), "headings": copy.counted(2, copy.HEADINGS)}
    detail = copy.fill(copy.BOQ_CONFIRM_DETAIL, first="5", last="40", **counts)
    assert detail == {
        "en": "Rows 5 to 40: 1 item and 2 headings.",
        "ar": "الصفوف من 5 لـ 40: بند واحد وعنوانين.",
    }
    skipped = copy.fill(copy.BOQ_CONFIRM_SKIPPED, count=copy.counted(11, copy.ROWS))
    assert skipped == {"en": "Left out: 11 rows.", "ar": "واتساب 11 صف."}


def test_an_arabic_list_takes_the_arabic_comma():
    assert copy.listed(["أسمنت - عينة", "رمل - عينة"]) == {
        "en": "أسمنت - عينة, رمل - عينة",
        "ar": "أسمنت - عينة، رمل - عينة",
    }


def test_one_page_is_said_as_one_page_and_a_file_without_pages_by_its_name():
    name = copy.file_name("مواصفات - عينة.pdf")
    assert _doing(name, pages=[1])["ar"] == f"يقرا {name}، صفحة 1"
    assert _doing(name, pages=[1, 2, 3])["ar"] == f"يقرا {name}، صفحات 1-3"
    assert _doing(name)["ar"] == f"يقرا {name}"
    assert "صفحات 1" not in _doing(name)["ar"]
    assert _doing(name, pages=[12], of=64) == {
        "en": f"Read {name}, page 12 of 64",
        "ar": f"يقرا {name}، صفحة 12 من 64",
    }
    assert _doing(name, pages=[1, 2], of=64)["ar"] == f"يقرا {name}، صفحات 1-2 من 64"
    rows = _doing(name, sheet="BOQ", rows="1-200")
    assert rows == {
        "en": f"Read {name}, sheet BOQ, rows 1-200",
        "ar": f"يقرا {name}، شيت BOQ، الصفوف 1-200",
    }


def test_no_stop_after_a_blank_that_ends_its_own_sentence():
    asked = {"en": "{step}.", "ar": "{step}."}
    assert copy.fill(asked, step={"en": "Ready?", "ar": "جاهزة؟"}) == {
        "en": "Ready?",
        "ar": "جاهزة؟",
    }
    assert copy.fill(asked, step={"en": "Ready", "ar": "جاهزة"}) == {"en": "Ready.", "ar": "جاهزة."}
