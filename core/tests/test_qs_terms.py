"""QS terms for search: a query naming a QS thing in Arabic is also searched under its English
names, and the reverse (records/qs_terms.json)."""

from qsone.records import arabic, qs_terms
from qsone.records.qs_terms import expand, language, named


def _first_en(text: str) -> list[str]:
    return [qs_terms._terms()[n]["en"][0] for n in named(text)]


def test_arabic_names_find_their_english_names():
    assert _first_en("نسبة المحتجز من المستخلصات") == ["retention", "interim payment certificate"]
    assert _first_en("غرامة التأخير") == ["delay damages"]
    assert _first_en("غرامات التأخير") == ["delay damages"]  # light stemming: plural, article
    assert _first_en("الدفعة المقدمة") == ["advance payment"]


def test_english_plurals_and_possessives_match():
    found = _first_en("retention percentage deducted from interim payments")
    assert found == ["retention", "interim payment certificate"]
    found = _first_en("Contractor's insurance of the works")
    assert found == ["contractor", "insurance of the works"]


def test_the_longest_name_wins():
    # «خطاب الضمان الابتدائي» is a bid security, not any letter of guarantee
    assert _first_en("خطاب الضمان الابتدائي") == ["bid security"]
    assert _first_en("ضمان حسن التنفيذ") == ["performance security"]


def test_expand_gives_the_other_language_and_every_name():
    other, phrases = expand(["نسبة المحتجز من المستخلصات"])
    assert other == ["retention, interim payment certificate"]
    assert "retention money" in phrases and arabic.normalise("ضمان الأعمال") in phrases
    other, _ = expand(["delay damages"])
    assert other == ["غرامة التأخير"]


def test_no_term_no_expansion():
    assert expand(["كشف حساب البنك"]) == ([], [])
    assert expand([""]) == ([], [])


def test_a_question_written_in_both_languages_is_not_translated_again():
    other, phrases = expand(["غرامة التأخير", "delay damages"])
    assert other == [] and "liquidated damages" in phrases


def test_language():
    assert language("غرامة التأخير") == "ar" and language("delay damages") == "en"
    assert language("خرسانة C30") == "ar" and language("C30 concrete grade") == "en"
    assert language("1 | 560 | 28") == ""  # a row of numbers is in neither


def test_every_entry_has_both_languages_and_no_name_twice():
    seen: dict[tuple[str, ...], int] = {}
    for n, term in enumerate(qs_terms._terms()):
        assert term["en"] and term["ar"], n
        for name in (*term["en"], *term["ar"]):
            keys = tuple(qs_terms._keys(name))
            assert keys, name
            assert seen.setdefault(keys, n) == n, f"{name!r} is in two entries"
