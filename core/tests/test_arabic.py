import pytest

from qsone.records.arabic import clean, display_text, normalise


@pytest.mark.parametrize(
    "a, b",
    [
        ("الخرسانة المسلّحة", "خرسانه مسلحه"),
        ("والخرسانات", "خرسانة"),
        ("بالأسمنت", "اسمنت"),
        ("إسمنت", "أسمنت"),
        ("مبنى", "مبني"),
        ("للمباني", "المباني"),
        ("المقاولين", "المقاولون"),
        ("ﺧﺮﺳﺎﻧﺔ", "خرسانة"),  # presentation forms
        ("تطل ـب", "تطلب"),  # kashida split by a space
        ("تطـــلب", "تطلب"),
    ],
)
def test_same_word_same_form(a, b):
    assert normalise(a) == normalise(b)


def test_digits():
    assert normalise("٥١٩٣ م.ط") == normalise("5193 م.ط") == normalise("۵۱۹۳ م.ط")


def test_codes():
    assert normalise("\u200f03/02") == "03 02"  # a right-to-left mark before the code
    assert normalise("Sub-Clause 14.2") == "sub clause 14 2"


def test_short_words_keep_their_letters():
    assert normalise("وزن") == "وزن"


def test_idempotent():
    # Light stemming strips again on a second pass («خرسان» -> «خرس»), so `normalise` runs once,
    # on any form of the text; the folding before it is idempotent.
    s = "والخرسانة ٣٩٨٥٠٫٥ EGP"
    assert clean(clean(s)) == clean(s)
    assert normalise(clean(s)) == normalise(display_text(s)) == normalise(s)


def test_display_keeps_what_the_engineer_wrote():
    assert display_text("ﺧﺮﺳﺎﻧﺔ ٥١٩٣ m³") == "خرسانة ٥١٩٣ m³"
