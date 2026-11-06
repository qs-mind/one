"""The truth checks (engine/truth.py), on the exact words a weak model wrote in the tender-day
walk (gemini-3.1-flash-lite, 5 Nov 2026). Synthetic «عينة» files only."""

import json
from datetime import UTC, date, datetime, timedelta

import pytest
from pydantic_ai import ModelRetry

from qsone.engine import checker, tools_records, truth  # noqa: F401 - registers the record tools
from qsone.engine.tools import REGISTRY, call
from qsone.engine.tools_records import NumberArgs, SourceArgs
from qsone.engine.truth import Brief, Coverage
from qsone.engine.types import CheckPacket, DeliverableDraft, Review
from qsone.records import ledger
from qsone.records.files import add_file
from tests.engine_fakes import OPUS
from tests.fakes_tools import tool_ctx
from tests.samples import sample_pdf

QUOTE = sample_pdf(
    [
        [
            "Quotation No. NB-2026-1147 - SAMPLE DATA",
            "Date: 2 November 2026 Valid for: 15 days",
            "1 Ready-mix concrete C30 incl. pumping m3 3,450",
            "3 Plain concrete C15 m3 2,600",
            "7 Solid cement block 25 cm nr 21",
        ]
    ]
)
EMAIL = (
    "Subject: توضيحات مناقصة - عينة\n"
    "1- الأسعار بالجنيه المصري ولا تشمل ضريبة القيمة المضافة ١٤٪، وتضاف في الملخص فقط.\n"
    "2- مدة سريان العرض ٩٠ يوم من تاريخ التقديم.\n"
    "5- آخر موعد لتقديم العطاءات: ١٨ نوفمبر ٢٠٢٦ الساعة ١٢ ظهراً.\n"
).encode()


def test_today_is_cairos_day():
    late = datetime(2026, 11, 5, 22, 30, tzinfo=UTC)  # 00:30 on 6 Nov in Cairo
    assert truth.today(late) == date(2026, 11, 6)
    assert "2026-11-05" in truth.today_line(datetime(2026, 11, 5, 8, tzinfo=UTC))


def test_bracketed_blanks_are_found_and_links_are_not():
    table = "| البند | الكمية | القيمة |\n| خرسانة | [الكمية] | [القيمة] |"
    assert truth.placeholders(table) == ["[الكمية]", "[القيمة]"]
    assert truth.placeholders("الإجمالي: [مبلغ إجمالي المقايسة]") == ["[مبلغ إجمالي المقايسة]"]
    assert truth.placeholders("Dear [Client name], total {{total}}") == [
        "[Client name]",
        "{{total}}",
    ]
    assert truth.placeholders("see [the quote](https://x.example) and note [1], [x]") == []
    blocks = [{"type": "p", "children": [{"text": "بقيمة [مبلغ إجمالي المقايسة] جنيه"}]}]
    assert truth.placeholders_in(blocks) == ["[مبلغ إجمالي المقايسة]"]


def test_a_reply_that_ends_on_a_promise():
    assert truth.promise("بدأت التسعير. جاري التنفيذ…")
    assert truth.promise("ثواني وهتكون القيم كاملة قدامك")
    assert truth.promise("هبدأ بتنظيف الأرقام القديمة")
    assert truth.promise("I'll finish the rest shortly.")
    assert truth.promise("اتسعّر 8 بنود. لو عايز أكمّل الباقي قولي.") is None
    assert truth.promise("Priced 8 items. Shall I go on with the rest?") is None
    assert truth.promise("اتسعّر 8 بنود من 325، والباقي لسه.") is None


def test_the_claim_that_all_325_items_are_priced():
    cov = Coverage(items=325, priced=8, deliverables=0)
    said = "تم الانتهاء من تسعير كافة بنود المقايسة (325) والمخرج جاهز للمراجعة."
    found = {p.kind: p for p in truth.overclaim(said, cov, Brief())}
    assert set(found) == {"priced", "deliverable"}
    assert "8 of 325" in found["priced"].fix
    assert "8" in found["priced"].flag["ar"] and "325" in found["priced"].flag["ar"]
    # a section's items, or the true count, are no overclaim
    assert truth.overclaim("سعّرت كل بنود الحفر.", cov, Brief()) == []
    assert truth.overclaim("اتسعّر 8 بنود من المقايسة.", cov, Brief()) == []
    done = Coverage(items=325, priced=325, deliverables=1)
    assert truth.overclaim(said, done, Brief(deliverables=1)) == []


def test_a_change_that_was_never_made():
    said = "تم تثبيت الأسعار عند سعر المورد فقط."
    [found] = truth.overclaim(said, None, Brief(writes=0))
    assert found.kind == "changed" and found.flag["ar"]
    assert truth.overclaim(said, None, Brief(writes=2)) == []


def test_labour_claimed_on_a_supply_only_quote():
    said = "الفئة 21.00 شاملاً المواد والمصنعية كما ورد في العرض."
    [found] = truth.overclaim(said, None, Brief(writes=1, supply_only=("04 عرض أسعار المورد",)))
    assert found.kind == "labour"


def test_reply_problems_for_the_retry():
    did = Brief(specialists=("Estimator", "مهندس التسعير"), tool_names=frozenset({"web_search"}))
    kinds = lambda text, **kw: {  # noqa: E731
        p.kind for p in truth.reply_problems(text, cov=None, did=did, engineer_text="سعّر", **kw)
    }
    assert kinds("استمر يا بشمهندس، كمل تسعير… أنا متابع معاك.") >= {"audience"}
    assert kinds("مقدرتش أستخدم web_search دلوقتي.") == {"tool"}
    assert kinds("قمت بإنشاء مستند (Deliverable) للمراجعة.") == {"english"}
    table = "| البند | القيمة |\n|---|---|\n| خرسانة | 1,250,000 |\n| حديد | 980,000 |"
    assert kinds(table) == {"table"}
    assert kinds("فهمت الملفات، البطاقة قدامك راجعها.", understand_brief=True) == {"card"}
    assert kinds("اتسعّر 8 بنود من 325؛ الباقي لسه.") == set()


def test_facts_say_what_the_records_hold():
    line = truth.facts(Coverage(325, 8, 0), [])
    assert line["text"]["ar"] == "من سجلات ONE: 325 بند · ONE سعّر 8 · مفيش مخرج لسه"
    assert (
        line["text"]["en"] == "From ONE's records: 325 items · 8 priced by ONE · no Deliverable yet"
    )
    assert truth.facts(Coverage(0, 0, 0), []) is None
    # the client's own rates are not ONE's pricing (real walk: «اتسعّر 54 من 54 بند» read as ONE's)
    client = truth.facts(Coverage(54, 54, 0, client=54), [])["text"]
    assert client["ar"] == "من سجلات ONE: 54 بند، فيهم 54 بسعر العميل · ONE سعّر 0 · مفيش مخرج لسه"
    assert client["en"] == (
        "From ONE's records: 54 items, 54 with the client's rates · 0 priced by ONE"
        " · no Deliverable yet"
    )


def test_coverage_counts_items_rates_and_deliverables(rec):
    source = ledger.add_source(rec, kind="sample", title="عينة", actor="t", dated="2026-11-05")
    with rec.write("t") as c:
        at = rec.clock()
        a = ledger.write_item(c, at=at, actor="t", kind="boq_item", code="01-01", fields={})
        ledger.write_item(c, at=at, actor="t", kind="boq_item", code="01-02", fields={})
        ledger.write_number(
            c, at=at, actor="t", item_id=a, name="rate", value="100", source_id=source,
            dated="2026-11-05", unit="m3", currency="EGP",
        )  # fmt: skip
    assert truth.coverage(rec) == Coverage(items=2, priced=1, deliverables=0, client=0)
    boq = ledger.add_source(rec, kind="boq", title="مقايسة العميل", actor="t", dated="2026-11-05")
    with rec.write("t") as c:
        at = rec.clock()
        b = ledger.write_item(c, at=at, actor="t", kind="boq_item", code="01-03", fields={})
        ledger.write_number(
            c, at=at, actor="t", item_id=b, name="rate", value="50", source_id=boq,
            dated="2026-11-05", unit="m3", currency="EGP",
        )  # fmt: skip
    assert truth.coverage(rec) == Coverage(items=3, priced=2, deliverables=0, client=1)


def _source(rec, file_id: str, locator: dict) -> str:
    with rec.write("t") as c:
        return ledger.write_source(
            c, at=rec.clock(), actor="t", kind="quote", title="عرض - عينة", file_id=file_id,
            locator=locator, dated="2026-11-02",
        )  # fmt: skip


def test_a_number_must_be_where_its_source_points(rec):
    quote = add_file(rec, "04 عرض أسعار المورد - عينة.pdf", QUOTE, actor="engineer").id
    source = _source(rec, quote, {"page": 1})
    with rec.read() as c:
        ok, where, seen = truth.value_at(c, source, "2600")
        assert ok and "page 1" in where and "2600" in seen
        assert truth.value_at(c, source, "2600.00")[0]
        assert not truth.value_at(c, source, "2500")[0]  # blinding cited to a page without it
        assert not truth.value_at(c, source, "3795")[0]  # 3,450 × 1.1, a calculation
        assert not truth.value_at(c, source, "2625")[0]  # a "market average" never in the quote


def test_quotes_and_items_say_what_they_cover():
    assert not truth.covers_labour("Solid cement block 25 cm nr 21")
    assert truth.covers_labour("توريد وتركيب بلاط بورسلين")
    assert truth.supply_only_item("توريد أسمنت مقاوم للكبريتات")
    assert not truth.supply_only_item("مباني طوب أسمنتي مصمت 25 سم")


def test_a_letter_against_the_files_and_today(rec):
    add_file(rec, "05 إيميل العميل - عينة.txt", EMAIL, actor="engineer")
    add_file(rec, "04 عرض أسعار المورد - عينة.pdf", QUOTE, actor="engineer")
    source = ledger.add_source(rec, kind="sample", title="عينة", actor="t", dated="2026-11-05")
    with rec.write("t") as c:
        item = ledger.write_item(c, at=rec.clock(), actor="t", kind="bill", fields={})
        for name, value in (
            ("total", "1426948.50"),
            ("vat", "199772.79"),
            ("with_vat", "1626721.29"),
        ):
            ledger.write_number(
                c,
                at=rec.clock(),
                actor="t",
                item_id=item,
                name=name,
                value=value,
                currency="EGP",
                source_id=source,
                dated="2026-11-05",
            )
    day = date(2026, 11, 5)
    bad = (
        "القاهرة في 6 نوفمبر 2026\n"
        "نتقدم بعرضنا بإجمالي 1,426,948.50 جنيه، ومدة صلاحية العرض 60 يوماً."
    )
    good = (
        "القاهرة في 5 نوفمبر 2026\n"
        "نتقدم بعرضنا بإجمالي 1,426,948.50 جنيه غير شامل ضريبة القيمة المضافة 14%، "
        "ومدة سريان العرض 90 يوم، وآخر موعد للتقديم 18 نوفمبر 2026.\n"
        "قيمة الضريبة 199,772.79 جنيه، والإجمالي شامل الضريبة 1,626,721.29 جنيه.\n"
        "مقدم العطاء: [يملأه المهندس]، رقم المناقصة: [يملأه المهندس]، التوقيع: [يملأه المهندس]"
    )
    with rec.read() as c:
        wrong = truth.letter_problems(c, bad, day=day, has_total=True)
        assert any("6 نوفمبر 2026" in w for w in wrong)
        assert any("validity 60" in w and "90" in w for w in wrong)
        assert any("VAT" in w and "14" in w for w in wrong)
        assert truth.letter_problems(c, good, day=day, has_total=True) == []


# The record tools: a number must be where its source says, and say what it covers ----------


@pytest.fixture
def ctx(rec):
    return tool_ctx(rec)


async def _quote(ctx) -> dict:
    quote = add_file(ctx.rec, "04 عرض أسعار المورد - عينة.pdf", QUOTE, actor="engineer").id
    args = {"kind": "quote", "file_id": quote, "locator": {"page": 1}, "dated": "2026-11-02"}
    return json.loads(await call("add_source", args, ctx)) | {"file_id": quote}


async def _item(ctx, code: str, description: str, unit: str) -> None:
    ctx.brief_id = ctx.store.new_brief(ctx.rec.id, f"Record the sample rate for item {code}")
    fields = {"description": description, "unit": unit}
    await call("add_item", {"kind": "boq_item", "code": code, "fields": fields}, ctx)


async def test_a_quote_that_says_nothing_of_labour_is_supply_only(ctx):
    found = await _quote(ctx)
    assert found["covers"] == "supply" and "Supply only" in found["note"]
    args = {"kind": "quote", "file_id": found["file_id"], "locator": {"page": 1}}
    with pytest.raises(ModelRetry, match="says nothing of installation"):
        await call("add_source", args | {"covers": "supply_and_install"}, ctx)


async def test_a_number_not_at_its_cited_place_is_refused(ctx):
    quote = (await _quote(ctx))["source_id"]
    await _item(ctx, "03-01", "توريد خرسانة عادية C15 - عينة", "m3")
    rate = {"item": "03-01", "name": "rate", "unit": "m3", "currency": "EGP", "source_id": quote}
    for wrong in ("2500", "3795", "2625"):  # cited to a page without it, a calc, an average
        with pytest.raises(ModelRetry, match="not at the place its source cites") as refused:
            await call("record_number", rate | {"value": wrong}, ctx)
        assert "2600" in str(refused.value) and "calculate" in str(refused.value)
    with ctx.rec.read() as c:
        assert c.execute("SELECT count(*) FROM numbers").fetchone() == (0,)  # nothing kept
    assert json.loads(await call("record_number", rate | {"value": "2600"}, ctx))["number_id"]


async def test_a_blocks_price_is_not_a_walls_rate(ctx):
    # masonry was priced at the block's price per «عدد», «شامل العمالة كما ورد في العرض»
    quote = (await _quote(ctx))["source_id"]
    await _item(ctx, "04-01", "مباني طوب أسمنتي مصمت 25 سم بالمونة - عينة", "m2")
    rate = {"item": "04-01", "name": "rate", "value": "21", "currency": "EGP", "source_id": quote}
    with pytest.raises(ModelRetry, match="measured in m2"):
        await call("record_number", rate | {"unit": "nr"}, ctx)
    with pytest.raises(ModelRetry, match="supply-only quote"):
        await call("record_number", rate | {"unit": "m2"}, ctx)
    # a supply-only item takes a supply quote's price
    await _item(ctx, "04-02", "توريد طوب أسمنتي مصمت 25 سم - عينة", "nr")
    supply = rate | {"item": "04-02", "unit": "nr"}
    assert json.loads(await call("record_number", supply, ctx))["number_id"]


def test_the_work_log_says_rate_and_names_the_source():
    # «بيسجّل rate البند 707d81e9…» and «بيضيف المصدر «None»»
    number = NumberArgs(item="01-01-001", name="rate", value="21", source_id="s")
    assert REGISTRY["record_number"].activity(number)["ar"] == "بيسجّل الفئة للبند 01-01-001 بمصدره"
    source = REGISTRY["add_source"].activity(SourceArgs(kind="quote", file_id="f" * 32))
    assert "None" not in source["ar"] and "f" * 32 in source["ar"]  # the runner names the file


# Deliverables and letters --------------------------------------------------------------------


def _letter(*lines: str) -> dict:
    blocks = [{"type": "p", "children": [{"text": line}]} for line in lines]
    return {"kind": "document", "variant": "letter", "title": "خطاب العطاء - عينة",
            "language": "ar", "blocks": blocks}  # fmt: skip


async def test_a_deliverable_with_a_blank_for_a_value_is_refused(ctx):
    letter = _letter("نتقدم بعرضنا بقيمة [مبلغ إجمالي المقايسة] جنيه - عينة")
    with pytest.raises(ModelRetry, match=r"blanks left for values: \[مبلغ إجمالي المقايسة\]"):
        await call("deliverable_create", letter, ctx)
    with ctx.rec.read() as c:
        assert c.execute("SELECT count(*) FROM deliverables").fetchone() == (0,)


_AR_MONTHS = ("يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو",
              "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر")  # fmt: skip


def _arabic_date(d: date) -> str:
    return f"{d.day} {_AR_MONTHS[d.month - 1]} {d.year}"


async def test_a_letter_takes_its_date_and_terms_from_the_files(ctx):
    add_file(ctx.rec, "05 إيميل العميل - عينة.txt", EMAIL, actor="engineer")
    # today in Cairo by the project's clock, as the tool reads it; the wrong day is never today
    # and never the date the email states (18 Nov 2026)
    today = truth.today(datetime.fromisoformat(ctx.rec.clock()))
    other = next(d for d in (today + timedelta(days=n) for n in (1, 2)) if d != date(2026, 11, 18))
    wrong = _letter(f"القاهرة في {_arabic_date(other)}", "مدة صلاحية العرض 60 يوماً - عينة")
    with pytest.raises(ModelRetry) as refused:
        await call("deliverable_create", wrong, ctx)
    said = str(refused.value)
    assert _arabic_date(other) in said and "validity 60" in said and "Nothing was saved" in said
    right = _letter(
        f"القاهرة في {_arabic_date(today)}",
        "مدة سريان العرض 90 يوم، والأسعار غير شاملة ضريبة القيمة المضافة 14% - عينة",
    )
    assert json.loads(await call("deliverable_create", right, ctx))["version"] == 1


# The numbers guard: a size in an item's own words is not a price -----------------------------


def test_a_size_from_an_items_description_is_not_marked():
    from qsone.engine import numbers_guard as guard

    reply = "بند مباني طوب 25 سم لسه مالوش فئة، والطوب بـ 25 جنيه في السوق."
    marked = guard.unsourced(reply, set())
    assert marked == ["25"]
    items = ["مباني طوب أسمنتي مصمت 25 سم بالمونة - عينة"]
    assert guard.described(reply, marked, items) == ["25"]  # «25 جنيه» is still a price
    only_size = "بند مباني طوب 25 سم لسه مالوش فئة."
    assert guard.described(only_size, guard.unsourced(only_size, set()), items) == []
    assert guard.numbers_in("مدة صلاحية العرض 60 يوماً") == ["60"]


# The Checking QS under ONE's own checks -------------------------------------------------------


def _review(code: str) -> Review:
    return Review(code, (), OPUS.choice, False, 1, checked=("sources",))


def _packet(rows: tuple, **found) -> CheckPacket:
    draft = DeliverableDraft(id="d", kind="table", title="مقايسة - عينة", body="", rows=rows)
    return CheckPacket("سعّر - عينة", draft, (), (), (), (), (), **found)


def test_no_code_a_over_four_rows_of_ninety(rec):
    # «كود A: معتمد» on a 4-row Deliverable covering about 4 of 90 items
    with rec.write("t") as c:
        for i in range(1, 91):
            ledger.write_item(c, at=rec.clock(), actor="t", kind="boq_item", code=f"04-{i:02}",
                              fields={})  # fmt: skip
        rows = tuple({"code": f"04-{i:02}"} for i in range(1, 5))
        cov = checker._coverage(c, _packet(rows).deliverable)
    assert cov == {"client_items": 90, "in_deliverable": 4, "missing": [f"04-{i:02}" for i in
                   range(5, 15)]}  # fmt: skip
    capped = checker.capped(_packet(rows, coverage=cov), _review("A"))
    assert capped.code == "B" and "4 of the client's 90 items" in capped.comments[-1]["text"]
    full = {"client_items": 4, "in_deliverable": 4, "missing": []}
    assert checker.capped(_packet(rows, coverage=full), _review("A")).code == "A"


def test_a_number_not_at_its_place_is_code_c():
    wrong = {"number_id": "n", "value": "2500", "where": "عرض.pdf, page 1", "found": False,
             "there": ["2600", "3450"]}  # fmt: skip
    capped = checker.capped(_packet((), citations=(wrong,)), _review("A"))
    assert capped.code == "C" and "2500 is not at عرض.pdf, page 1" in capped.comments[0]["text"]
    assert "checked" in checker.ReviewOut.model_json_schema()["required"]


def test_citing_a_page_range_requires_every_page_returned():
    returns = [
        (
            "files_read",
            'file_id: sample | file: sample.pdf\n{"page": 1}\nSample 350000 USD\nsources:',
        )
    ]
    assert truth.unread_citations("Security 350000 USD, pages 1, 2.", returns)
    assert not truth.unread_citations("Security 350000 USD, page 1.", returns)


def test_wrong_file_cannot_satisfy_a_page_read():
    returns = [
        (
            "files_read",
            'file_id: sample | file: other.pdf\n{"page": 26}\nSample 350000 USD\nsources:',
        )
    ]
    assert truth.unread_citations("Security 350000 USD, contract.pdf, page 26.", returns)


def test_citation_cannot_use_numbers_outside_the_returned_page_part():
    returns = [
        ("files_read", 'file_id: sample | file: sample.pdf\n{"page": 26}\nOnly 180 days\nsources:')
    ]
    assert truth.unread_citations("Security 350000 USD, page 26.", returns)


def test_csv_row_citations_require_the_returned_physical_line():
    returns = [
        (
            "files_read",
            'file_id: sample | file: sample.csv\n{"line": 1902} 3259.438571429\nsources:',
        )
    ]
    assert not truth.unread_citations("Price 3259.438571429, row 1902.", returns)
    assert truth.unread_citations("Price 3259.438571429, row 952.", returns)
