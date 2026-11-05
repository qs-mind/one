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


def test_a_file_name_on_screen_is_isolated_with_its_extension_last():
    from qsone import copy

    name = "مواصفات - عينة اختبار (sample spec).docx"
    shown = copy.file_name(name)
    # the Latin words at the end of an Arabic name go left to right with the extension:
    # «(sample spec).docx», never «.docx(sample spec» (as ui/src/ui/FileName.tsx)
    assert shown == "\u2068مواصفات - عينة اختبار \u2066(sample spec).docx\u2069\u2069"
    assert shown.translate({0x2066: None, 0x2068: None, 0x2069: None}) == name
    assert copy.file_name("مواصفات.docx") == "\u2068مواصفات\u2066.docx\u2069\u2069"
    assert copy.file_name("Spec (v2).docx") == "\u2068Spec (v2)\u2066.docx\u2069\u2069"
    assert copy.file_name("README") == "\u2068README\u2069"
    words = copy.fill(copy.DOING_BOQ_IMPORT, name=shown, sheet="BOQ")
    assert shown in words["ar"] and shown in words["en"]


def test_every_tool_has_plain_progress_words_never_its_id():
    import qsone.app  # noqa: F401 - registers every tool
    from qsone import copy
    from qsone.engine.tools import REGISTRY

    assert set(REGISTRY) <= set(copy.TOOL_WORDS), set(REGISTRY) - set(copy.TOOL_WORDS)
    for name, words in copy.TOOL_WORDS.items():
        assert words["en"].strip() and words["ar"].strip(), name
        assert "_" not in words["en"] + words["ar"], name  # no tool id such as files_list
        assert name not in words["ar"], name
    assert copy.tool_step("a_tool_from_nowhere") == copy.TOOL_STEP
