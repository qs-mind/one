"""A number the reply says is at a row or a page must be there (the real walk, 6 Nov 2026): ceramic
72 cited to «تسعير بنود» row 18 (a different, empty item), «12 جنيه/م3 (شيت "تسعير"، صف 16)» for an
item the BOQ does not have, the retention limit to page 59 (it is on page 58); and the bid
security «350,000 دولار … الصفحة: 26», marked "no source yet" although page 26 has it.

Scripted models only; synthetic «عينة» files only; no real AI."""

# ruff: noqa: F811 (the engine fixtures, imported)

import pytest

from qsone.engine import truth
from qsone.engine.types import Unsourced
from qsone.records.files import add_file
from tests.engine_fakes import scripted
from tests.engine_fakes import text as said
from tests.samples import sample_pdf, sample_xlsx
from tests.test_engine_runner import (  # noqa: F401 - the runner's fixtures
    finish,
    links,
    make_engine,
    no_budget_card,
    project,
    registry,
    started,
)
from tests.test_truth_runner import datas

BOOK = sample_xlsx(
    {
        "مقايسة ": [  # a trailing space, as the Lahun sheet has it
            ["م", "البيان", "الوحدة", "الكمية", "الفئة", "الإجمالي"],
            ["16", "توريد وتركيب سيراميك أرضيات - عينة", "م2", 730, 72, 52560],
            ["17", "توريد وتركيب سيراميك حوائط - عينة", "م2", 1120, 72, 80640],
            ["18", "مرمات سيراميك - عينة", "م2", 50, 80, 4000],
        ],
        "تسعير": [
            ["البند", "الخامة", "المصنعية", "الهالك", "الفئة"],
            ["سيراميك - عينة", 27, 40, 5, 72],
            ["بياض - عينة", "أسمنت 480 للطن", "رمل 25", "", ""],
        ],
    }
)
TERMS = sample_pdf(
    [
        ["Bid security: USD 350,000 - SAMPLE"],
        ["Retention: 10% of each payment, up to a limit of 10% - SAMPLE"],
        ["Delay damages: 0.2% of the Contract Price per day - SAMPLE"],
    ]
)


@pytest.fixture
def files(registry, project):
    rec = registry.get(project)
    add_file(rec, "مقايسة - عينة.xlsx", BOOK, actor="engineer")
    add_file(rec, "terms - sample.pdf", TERMS, actor="engineer")
    return rec


def problems(rec, text: str) -> list[truth.Problem]:
    with rec.read() as c:
        return truth.miscited(c, text)


def test_a_number_cited_to_a_row_that_has_it_is_right(files):
    assert problems(files, "فئة السيراميك 72 جنيه (شيت «مقايسة»، صف 2).") == []
    assert problems(files, 'فئة السيراميك ٧٢ جنيه/م2 (من شيت "تسعير"، صف 2).') == []
    assert problems(files, "Retention 10% (page 2).") == []
    assert problems(files, "Bid security USD 350,000.00 (p. 1).") == []


def test_a_number_cited_to_the_wrong_row_or_page_is_found(files):
    [found] = problems(files, "فئة السيراميك 72 جنيه (شيت «مقايسة»، صف 4).")
    assert found.kind == "cited" and "72" in found.fix and "row 4" in found.fix
    assert "72" in found.flag["ar"] and "صف 4" in found.flag["ar"]
    [found] = problems(files, "The delay damages are 0.2% per day (page 2).")
    assert "0.2" in found.fix


def test_a_place_no_file_has_is_found(files):
    [found] = problems(files, 'بند حفر للأساسات: السعر 12 جنيه/م3 (من شيت "حفر"، صف 16).')
    assert "no project file has" in found.fix
    assert "مفيش ملف" in found.flag["ar"]


def test_a_number_at_a_cited_page_has_a_source(files):
    with files.read() as c:
        assert "350000" in truth.cited_values(
            c, "قيمة الضمان 350,000 دولار.\nالصفحة: 1 (بند 17.1)."
        )


async def test_the_lead_cites_the_wrong_row_then_fixes_it(make_engine, project, files):
    wrong = "تسعير بند 16: الفئة 72 جنيه للمتر (من شيت «مقايسة»، صف 4)."
    right = "تسعير بند 16: الفئة 72 جنيه للمتر (من شيت «مقايسة»، صف 2)."
    lead = scripted(said(wrong), said(right))
    engine = await started(make_engine(links(lead=lead)))
    events = await finish(engine, await engine.start_brief(project, "فئة السيراميك كام؟"))
    assert lead.calls == 2 and "row 4" in str(lead.seen[1])
    assert not datas(events, "facts")


async def test_a_number_read_from_a_cited_page_is_not_marked(make_engine, project, files):
    reply = "قيمة ضمان العطاء 350,000 دولار أمريكي.\n- الصفحة: 1 (بند 17.1)."
    lead = scripted(said(reply))
    engine = await started(make_engine(links(lead=lead)))
    events = await finish(engine, await engine.start_brief(project, "ضمان العطاء كام؟"))
    marked = [v for e in events if isinstance(e, Unsourced) for v in e.values]
    assert "350,000" not in marked
