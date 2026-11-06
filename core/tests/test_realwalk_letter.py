"""The tender letter (the real walk, 6 Nov 2026): «5 أرقام من غير مصدر» although the total is
the BOQ's; no VAT amount and no total with VAT; and the bid fields (bidder, tender number,
signature) left out, or at risk of being invented. Synthetic «عينة» data only; no real AI."""

# ruff: noqa: F811 (the fixtures, imported)

import json
from datetime import date, datetime

import pytest
from pydantic_ai import ModelRetry

from qsone.engine import truth
from qsone.engine.tools import call
from qsone.records import ledger
from qsone.records.files import add_file
from tests.test_truth import EMAIL, _arabic_date, _letter, ctx  # noqa: F401

DAY = date(2026, 11, 5)
TOTAL = "نتقدم بعرضنا بإجمالي 1,426,948.50 جنيه غير شامل ضريبة القيمة المضافة 14%."
VAT = "قيمة ضريبة القيمة المضافة 14%: 199,772.79 جنيه، والإجمالي شامل الضريبة 1,626,721.29 جنيه."
FIELDS = (
    "مقدم العطاء: [يملأه المهندس: اسم مقدم العطاء]\n"
    "رقم المناقصة: [يملأه المهندس: رقم المناقصة]\n"
    "التوقيع: [يملأه المهندس: التوقيع والختم]"
)


def problems(rec, text: str) -> list[str]:
    with rec.read() as c:
        return truth.letter_problems(c, text, day=DAY, has_total=True)


@pytest.fixture
def priced_letter(rec):
    """Sample ledger amounts: the letter tests check VAT and bid fields against known totals."""
    with rec.write("engineer") as c:
        at = rec.clock()
        item = ledger.write_item(c, at=at, actor="engineer", kind="total", code="BOQ")
        source = ledger.write_source(
            c, at=at, actor="engineer", kind="boq", title="Priced BOQ - sample"
        )
        for name, value in (
            ("total", "1426948.50"),
            ("vat", "199772.79"),
            ("with_vat", "1626721.29"),
        ):
            ledger.write_number(
                c,
                at=at,
                actor="engineer",
                item_id=item,
                name=name,
                value=value,
                source_id=source,
                dated="2026-11-01",
                currency="EGP",
            )
    return rec


def test_a_priced_letter_gives_the_vat_and_the_total_with_it(priced_letter):
    rec = priced_letter
    add_file(rec, "05 إيميل العميل - عينة.txt", EMAIL, actor="engineer")
    wrong = problems(rec, f"القاهرة في 5 نوفمبر 2026\n{TOTAL}\n{FIELDS}")
    assert any("VAT amount" in w and "with VAT" in w for w in wrong)
    assert problems(rec, f"القاهرة في 5 نوفمبر 2026\n{TOTAL}\n{VAT}\n{FIELDS}") == []


def test_a_priced_letter_has_the_bid_fields_for_the_engineer(priced_letter):
    rec = priced_letter
    add_file(rec, "05 إيميل العميل - عينة.txt", EMAIL, actor="engineer")
    [wrong] = problems(rec, f"القاهرة في 5 نوفمبر 2026\n{TOTAL}\n{VAT}")
    assert "bidder" in wrong and "tender number" in wrong and "signature" in wrong
    assert "never" in wrong and "يملأه المهندس" in wrong


def test_a_field_marked_for_the_engineer_is_no_blank():
    assert truth.placeholders(FIELDS) == []
    assert truth.placeholders("مقدم العطاء: [اسم الشركة]") == ["[اسم الشركة]"]


async def test_a_typed_total_that_is_a_ledger_number_goes_in_as_that_number(ctx):
    with ctx.rec.write("engineer") as c:
        at = ctx.rec.clock()
        item = ledger.write_item(c, at=at, actor="engineer", kind="total", code="BOQ")
        source = ledger.write_source(c, at=at, actor="engineer", kind="boq", title="مقايسة - عينة")
        number = ledger.write_number(
            c,
            at=at,
            actor="engineer",
            item_id=item,
            name="amount",
            value="1426948.50",
            source_id=source,
            dated="2026-11-01",
            currency="EGP",
        )
    today = truth.today(datetime.fromisoformat(ctx.rec.clock()))
    letter = _letter(f"القاهرة في {_arabic_date(today)}", "نتقدم بعرضنا بإجمالي 1,426,948.50 جنيه.")
    with pytest.raises(ModelRetry) as refused:
        await call("deliverable_create", letter, ctx)
    said = str(refused.value)
    assert "1,426,948.50" in said and number in said and '"type": "num"' in said
    with ctx.rec.read() as c:
        assert c.execute("SELECT count(*) FROM deliverables").fetchone() == (0,)
    blocks = letter["blocks"][:1] + [
        {
            "type": "p",
            "children": [
                {"text": "نتقدم بعرضنا بإجمالي "},
                {"type": "num", "number": number, "children": [{"text": ""}]},
                {"text": " جنيه."},
            ],
        },
        *({"type": "p", "children": [{"text": line}]} for line in FIELDS.split("\n")),
    ]
    assert json.loads(await call("deliverable_create", letter | {"blocks": blocks}, ctx))["id"]


def test_a_priced_letter_still_refuses_amounts_missing_from_the_ledger(rec):
    add_file(rec, "05 إيميل العميل - عينة.txt", EMAIL, actor="engineer")
    wrong = problems(rec, f"القاهرة في 5 نوفمبر 2026\n{TOTAL}\n{VAT}\n{FIELDS}")
    assert len(wrong) == 3
    assert all("not in the project records" in problem for problem in wrong)
