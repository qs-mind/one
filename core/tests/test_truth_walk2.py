"""Walk 2 Group H regressions. Synthetic sample records and scripted AI only."""

# ruff: noqa: F811, F401 (imported engine fixtures)
import asyncio
from datetime import date
from pathlib import Path

import pytest

from qsone.deliverables import store as documents
from qsone.engine import truth
from qsone.engine.types import reply_line
from tests.engine_fakes import scripted
from tests.engine_fakes import text as said
from tests.test_engine_runner import (  # noqa: F401
    finish as _finish,
)
from tests.test_engine_runner import (
    links,
    make_engine,
    no_budget_card,
    project,
    registry,
    store_of,
)
from tests.test_engine_runner import (
    started as _started,
)
from tests.test_truth_runner import datas, reply


async def finish(engine, brief):
    return await asyncio.wait_for(_finish(engine, brief), 10)


async def started(engine):
    return await asyncio.wait_for(_started(engine), 5)


@pytest.mark.parametrize(
    "claim", ["تم تجهيز خطاب العطاء", "The letter is ready.", "I wrote the document."]
)
async def test_empty_letter_claim_retries(make_engine, project, registry, claim):
    documents.create(
        registry.get(project),
        kind="document",
        variant="letter",
        title="خطاب العطاء - عينة",
        language="ar",
        actor="t",
        blocks=[{"type": "p", "children": [{"text": " "}]}],
    )
    lead = scripted(said(claim), said("لسه الخطاب فاضي."))
    engine = await started(make_engine(links(lead=lead)))
    events = await finish(engine, await engine.start_brief(project, "اكتب خطاب العطاء"))
    assert lead.calls == 2
    assert "empty" in str(lead.seen[1]).lower()
    assert reply(events) == "لسه الخطاب فاضي."


def test_letter_rejects_invented_total(rec):
    with rec.read() as c:
        wrong = truth.letter_problems(
            c, "إجمالي قيمة الأعمال: 441,850.00 جنيه مصري", day=date(2026, 11, 5), has_total=False
        )
    assert any("441,850.00" in p and "records" in p for p in wrong)


async def test_letter_chat_money_is_sent_back(make_engine, project):
    lead = scripted(
        said("خطاب العطاء: إجمالي قيمة الأعمال 441,850.00 جنيه مصري"),
        said("لسه إجمالي المقايسة مش موجود عندي."),
    )
    engine = await started(make_engine(links(lead=lead)))
    await finish(engine, await engine.start_brief(project, "اكتب خطاب العطاء"))
    assert lead.calls == 2
    assert "441,850.00" in str(lead.seen[1])


@pytest.mark.parametrize(
    "text",
    [
        "هبدأ بتسجيل المصدر… تحب أبدأ؟",
        "هخلص تجهيز المستند ده وهعرضهولك فوراً",
        "سأقوم بالبحث مرة أخرى",
        "I am going to prepare the document now. Would you like me to start?",
    ],
)
async def test_promises_retry_once_then_flag(make_engine, project, text):
    lead = scripted(said(text), said(text))
    engine = await started(make_engine(links(lead=lead)))
    events = await finish(engine, await engine.start_brief(project, "جهز المستند"))
    assert lead.calls == 2
    assert any(
        "مفيش حاجة شغالة" in f["ar"] for d in datas(events, "facts") for f in d.data["flags"]
    )


@pytest.mark.parametrize(
    "answer",
    [
        "لم أجد نصاً، حد المحتجز 5% وغرامة التأخير 0.1% في اليوم.",
        "Bid validity is 90 days (page 16).",
    ],
)
async def test_contract_values_need_this_briefs_search(make_engine, project, answer):
    lead = scripted(said(answer), said("مش لاقي القيمة في الملفات لسه."))
    engine = await started(make_engine(links(lead=lead)))
    await finish(engine, await engine.start_brief(project, "إيه شروط العقد في ملفات المناقصة؟"))
    assert lead.calls == 2
    assert "search" in str(lead.seen[1])


@pytest.mark.parametrize(
    "text",
    [
        "[Show]",
        "The reply left blanks for values: [Show]",
        "file ID ``",
        "ملف رقم )",
        "Ledger",
        "Source Ledger",
        "أداة العرض (show)",
        "سجل النظام",
    ],
)
def test_cleaner_removes_walk_internal_words(text):
    cleaned = truth.clean_reply(text, shown=False)
    assert text.lower() not in cleaned.lower()
    assert cleaned == truth.clean_reply(cleaned, shown=False)


def test_reply_addresses_you():
    text = "you may want to ask the engineer if they have received alternative offers"
    problems = truth.reply_problems(
        text, cov=None, did=truth.Brief(), engineer_text="Compare quotes"
    )
    assert any(p.kind == "audience" for p in problems)
    assert "ask the engineer" not in truth.clean_reply(text, shown=False)


async def test_arabic_voice_instruction_is_explicit(make_engine, project):
    lead = scripted(said("مش لاقي عروض بديلة في الملفات."))
    engine = await started(make_engine(links(lead=lead)))
    await finish(engine, await engine.start_brief(project, "قارن العروض"))
    assert "Egyptian Arabic" in str(lead.seen[0])
    instructions = (Path(__file__).parents[1] / "qsone/engine/instructions/lead_qs.txt").read_text()
    assert "[يملأه المهندس:" in instructions
    assert "project name" in instructions and "client" in instructions


async def test_stop_old_id_stops_running_successor_only(make_engine, project):
    entered = asyncio.Event()

    async def block(messages, info):
        entered.set()
        await asyncio.Event().wait()

    lead = scripted(said("خلصت المراجعة - عينة."), block)
    engine = await started(make_engine(links(lead=lead)))
    old = await engine.start_brief(project, "راجع - عينة")
    await finish(engine, old)
    new = await engine.start_brief(project, "كمّل - عينة")
    await asyncio.wait_for(entered.wait(), 5)
    try:
        await engine.stop(old)
        assert store_of(engine, project).brief(new)["status"] == "stopped"
        assert engine.active(project) is None
    finally:
        if engine.active(project):
            await engine.stop(new)


def test_promise_followed_by_start_question():
    assert truth.promise("هبدأ بتسجيل المصدر… تحب أبدأ؟", truth.Brief())
    assert truth.promise("هخلص تجهيز المستند ده وهعرضهولك فوراً", truth.Brief(writes=1))


def test_contract_values_without_read_are_flagged():
    problems = truth.reply_problems(
        "المحتجز 5% وغرامة التأخير 0.1% في اليوم",
        cov=truth.Coverage(0, 0, 0),
        did=truth.Brief(),
        engineer_text="شروط العقد؟",
    )
    assert any(p.kind == "contract_unread" for p in problems)


def test_voice_and_letter_instructions():
    instructions = (Path(__file__).parents[1] / "qsone/engine/instructions/lead_qs.txt").read_text()
    assert "Egyptian Arabic" in reply_line("قارن العروض")
    assert "Egyptian Arabic" not in reply_line("Compare the quotes")
    assert "[يملأه المهندس:" in instructions


def test_empty_document_content_cannot_be_claimed_ready(rec):
    doc = documents.create(
        rec,
        kind="document",
        variant="letter",
        title="خطاب العطاء - عينة",
        language="ar",
        actor="t",
        blocks=[{"type": "p", "children": [{"text": " "}]}],
    )
    with rec.read() as c:
        assert truth.document_claims(c, "تم تجهيز خطاب العطاء", [doc])


async def test_stop_successor_before_task_starts(make_engine, project):
    lead = scripted(said("خلصت - عينة"))
    engine = await started(make_engine(links(lead=lead)))
    old = await engine.start_brief(project, "راجع - عينة")
    await finish(engine, old)
    new = await engine.start_brief(project, "كمّل - عينة")
    await engine.stop(old)
    assert store_of(engine, project).brief(new)["status"] == "stopped"
    assert engine.active(project) is None
    assert lead.calls == 1


def test_cleaner_removes_tool_identifiers():
    assert "search_records" not in truth.clean_reply("استخدمت search_records.", shown=False)


def test_money_guard_does_not_confuse_days_with_totals(rec):
    from qsone.records import ledger

    source = ledger.add_source(rec, kind="sample", title="عينة", actor="t", dated="2026-11-05")
    with rec.write("t") as c:
        item = ledger.write_item(c, at=rec.clock(), actor="t", kind="bill", fields={})
        ledger.write_number(
            c,
            at=rec.clock(),
            actor="t",
            item_id=item,
            name="amount",
            value="2500",
            currency="EGP",
            source_id=source,
            dated="2026-11-05",
        )
    with rec.read() as c:
        assert (
            truth.letter_problems(
                c, "Total 2500 EGP, validity 90 days.", day=date(2026, 11, 5), has_total=False
            )
            == []
        )


def test_empty_letter_does_not_invalidate_ready_sheet(rec):
    documents.create(
        rec,
        kind="document",
        variant="letter",
        title="خطاب - عينة",
        language="ar",
        actor="t",
        blocks=[],
    )
    with rec.read() as c:
        assert truth.document_claims(c, "The priced BOQ is ready.", []) == []


def test_arabic_percent_contract_needs_search():
    problems = truth.reply_problems(
        "المحتجز ٥٪", cov=truth.Coverage(0, 0, 0), did=truth.Brief(), engineer_text="المحتجز كام؟"
    )
    assert any(p.kind == "contract_unread" for p in problems)


def test_read_contract_and_nonempty_letter_are_not_flagged(rec):
    doc = documents.create(
        rec,
        kind="document",
        variant="letter",
        title="خطاب - عينة",
        language="ar",
        actor="t",
        blocks=[{"type": "p", "children": [{"text": "خطاب عينة مكتوب"}]}],
    )
    with rec.read() as c:
        assert truth.document_claims(c, "الخطاب جاهز.", [doc]) == []
    problems = truth.reply_problems(
        "Bid validity is 180 days.",
        cov=truth.Coverage(0, 0, 0),
        did=truth.Brief(done={"files_read"}),
        engineer_text="Bid validity?",
    )
    assert not any(p.kind == "contract_unread" for p in problems)


async def test_stop_does_not_cross_chats(make_engine, project, registry):
    other = registry.create("مشروع تاني - عينة", "engineer")["id"]
    entered = asyncio.Event()

    async def block(messages, info):
        entered.set()
        await asyncio.Event().wait()

    lead = scripted(said("خلصت - عينة"), block)
    engine = await started(make_engine(links(lead=lead)))
    old = await engine.start_brief(project, "راجع")
    await finish(engine, old)
    running = await engine.start_brief(other, "راجع")
    await asyncio.wait_for(entered.wait(), 5)
    with pytest.raises(LookupError):
        await engine.stop(old)
    assert engine.active(other) == running
    await engine.stop(running)


async def test_letter_marked_numbers_are_fixed_before_ending(make_engine, project, registry):
    from qsone.records import ledger

    rec = registry.get(project)
    source = ledger.add_source(rec, kind="sample", title="عينة", actor="t", dated="2026-11-05")
    with rec.write("t") as c:
        item = ledger.write_item(c, at=rec.clock(), actor="t", kind="bill", fields={})
        ledger.write_number(
            c,
            at=rec.clock(),
            actor="t",
            item_id=item,
            name="amount",
            value="2500",
            currency="EGP",
            source_id=source,
            dated="2026-11-05",
        )
    lead = scripted(said("Bid letter: total 2500 EGP."), said("I have not read the total yet."))
    engine = await started(make_engine(links(lead=lead)))
    await finish(engine, await engine.start_brief(project, "Write a bid letter"))
    assert lead.calls == 2
    assert "no source" in str(lead.seen[1])


def test_letter_claim_checks_letter_not_newer_report(rec):
    documents.create(
        rec,
        kind="document",
        variant="letter",
        title="خطاب - عينة",
        language="ar",
        actor="t",
        blocks=[],
    )
    documents.create(
        rec,
        kind="document",
        variant="report",
        title="تقرير - عينة",
        language="ar",
        actor="t",
        blocks=[{"type": "p", "children": [{"text": "تقرير عينة"}]}],
    )
    with rec.read() as c:
        assert truth.document_claims(c, "تم تجهيز خطاب العطاء", [])


def test_placeholder_diagnostic_is_not_repeated_to_engineer():
    cleaned = truth.clean_reply("The reply left blanks for values: [Show]", shown=False)
    assert "left blanks" not in cleaned
    assert cleaned == "not found"
