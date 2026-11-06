"""The pricing specialist reads the build-up (the real walk, Lahun, 6 Nov 2026): ceramic was
given as 27 (the tile alone) instead of 72 (materials + labour + waste), and the plaster's
materials were said to be missing though the materials sheet had them, in a hidden sheet.
Synthetic «عينة» files only; no real AI."""

# ruff: noqa: F811 (the fixtures, imported)

import json

from qsone.engine.runner import SPECIALIST_RULES
from qsone.engine.tools import call
from qsone.records.files import add_file
from tests.samples import sample_xlsx
from tests.test_records_tools import ctx, eng  # noqa: F401 - the tools' fixtures

BOOK = sample_xlsx(
    {
        "مقايسة": [
            ["م", "البيان", "الوحدة", "الكمية", "الفئة"],
            ["16", "توريد وتركيب سيراميك أرضيات - عينة", "م2", 730, ""],
            ["21", "بياض محارة للحوائط - عينة", "م2", 2400, ""],
        ],
        "تحليل الأسعار": [
            ["البند", "الخامات", "المصنعية", "الهالك", "الفئة"],
            ["سيراميك أرضيات - عينة", 27, 40, 5, 72],
        ],
        "أسعار الخامات": [
            ["الخامة", "الوحدة", "السعر"],
            ["أسمنت بياض محارة - عينة", "طن", 4800],
            ["رمل بياض محارة - عينة", "م3", 250],
        ],
    },
    hidden_sheets=("أسعار الخامات",),
)


def hits(out: str) -> list[dict]:
    return json.loads(next(line for line in out.splitlines() if line.startswith("{")))["hits"]


async def test_the_build_up_and_material_sheets_are_read(ctx):
    add_file(ctx.rec, "مقايسة اللاهون - عينة.xlsx", BOOK, actor="engineer")
    found = hits(await call("search_records", {"query": "سيراميك أرضيات", "k": 10}, ctx))
    rows = [await call("read_chunk", {"chunk_id": h["chunk_id"]}, ctx) for h in found]
    assert any("تحليل الأسعار" in r and "72" in r for r in rows)  # the whole rate, with its parts
    found = hits(await call("search_records", {"query": "بياض محارة أسمنت رمل", "k": 10}, ctx))
    rows = [await call("read_chunk", {"chunk_id": h["chunk_id"]}, ctx) for h in found]
    assert any("أسعار الخامات" in r and "4800" in r for r in rows)  # a hidden sheet is read too


def test_the_specialist_builds_a_rate_from_its_build_up():
    assert "materials + labour + waste" in SPECIALIST_RULES
    assert "build-up" in SPECIALIST_RULES and "materials" in SPECIALIST_RULES
