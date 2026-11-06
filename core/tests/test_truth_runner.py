"""The truth checks in the Brief Runner: a weak Lead's reply goes back once when it says what
ONE's records do not show, and the core puts the facts from its records beside the reply.

Scripted models make exactly the mistakes gemini-3.1-flash-lite made on the tender day (5 Nov
2026). Synthetic «عينة» data only; no real AI."""

# ruff: noqa: F811 (the engine fixtures, imported)

import asyncio

from qsone.engine.runner import _stored_events
from qsone.engine.types import Data, Progress, TextDelta
from qsone.records import ledger
from tests.engine_fakes import call, scripted
from tests.engine_fakes import text as said
from tests.test_engine_runner import (  # noqa: F401 - the runner's fixtures
    finish,
    links,
    make_engine,
    no_budget_card,
    project,
    registry,
    started,
    store_of,
    team_steps,
)


def boq(rec, n: int = 5) -> list[str]:
    """`n` client BOQ items «بند - عينة», none priced."""
    with rec.write("t") as c:
        at = rec.clock()
        return [
            ledger.write_item(
                c,
                at=at,
                actor="t",
                kind="boq_item",
                code=f"01-01-{i:03}",
                fields={"description": f"مباني طوب أسمنتي 25 سم - عينة {i}", "unit": "m3"},
            )  # fmt: skip
            for i in range(1, n + 1)
        ]


def datas(events, name: str) -> list[Data]:
    return [e for e in events if isinstance(e, Data) and e.name == name]


def reply(events) -> str:
    """The reply as the screen shows it: the text, with each `data-redo` range dropped."""
    out = ""
    for e in events:
        if isinstance(e, TextDelta):
            out += e.text
        elif isinstance(e, Data) and e.name == "redo":
            cut = e.data
            raw = out.encode("utf-16-le")
            out = (raw[: 2 * cut["from"]] + raw[2 * cut["to"] :]).decode("utf-16-le")
    return out


async def test_a_change_never_made_goes_back_once(make_engine, project):
    # «استنى، استخدم أسعار المورد بس» got «تم تثبيت الأسعار عند سعر المورد فقط» with no write
    lead = scripted(
        said("تم تثبيت الأسعار عند سعر المورد فقط."),
        said("لسه ماغيرتش حاجة؛ قولي البنود اللي عايزها بسعر المورد وأسجّلها."),
    )
    engine = await started(make_engine(links(lead=lead)))
    brief = await engine.start_brief(project, "استنى، استخدم أسعار المورد بس")
    events = await finish(engine, brief)
    assert lead.calls == 2
    assert "nothing was recorded or changed in this Brief" in str(lead.seen[1])
    [redo] = datas(events, "redo")
    assert reply(events) == "لسه ماغيرتش حاجة؛ قولي البنود اللي عايزها بسعر المورد وأسجّلها."
    assert not datas(events, "facts")
    store = store_of(engine, project)  # the chat read back has only the fixed answer
    replayed = _stored_events(store, store.brief(brief), engine)
    assert "تم تثبيت" not in "".join(e.text for e in replayed if isinstance(e, TextDelta))


async def test_an_overclaim_that_stays_is_flagged_beside_the_reply(make_engine, project, registry):
    # «تم الانتهاء من تسعير كافة بنود المقايسة (325)» over 8 priced items: once back, then flagged
    rec = registry.get(project)
    boq(rec, 5)
    claim = "تم الانتهاء من تسعير كافة بنود المقايسة والمخرج جاهز. جاري التنفيذ…"
    lead = scripted(said(claim), said(claim))
    engine = await started(make_engine(links(lead=lead)))
    brief = await engine.start_brief(project, "سعّر المقايسة كلها")
    events = await finish(engine, brief)
    assert lead.calls == 2  # sent back once, never twice
    fix = str(lead.seen[1])
    assert "0 of 5 items with a rate" in fix and "ends on a promise" in fix
    [facts] = datas(events, "facts")
    assert facts.data["text"]["ar"] == "من سجلات ONE: 5 بنود · ONE سعّر 0 · مفيش مخرج لسه"
    flags = [f["ar"] for f in facts.data["flags"]]
    assert any("والسجلات فيها 0 بس من 5" in f for f in flags)
    assert any("مفيش مخرج لسه" in f for f in flags)
    assert any("مفيش حاجة شغالة" in f for f in flags)
    # the chat read back shows the same facts
    store = store_of(engine, project)
    replayed = _stored_events(store, store.brief(brief), engine)
    assert datas(replayed, "facts")[0].data == facts.data


async def test_every_agent_gets_todays_date_in_cairo(make_engine, project):
    # the letter was dated 6 Nov on 5 Nov: the date now comes from the core's clock
    lead = scripted(said("تمام - عينة"))
    engine = await started(make_engine(links(lead=lead)))
    await finish(engine, await engine.start_brief(project, "اكتب خطاب العطاء"))
    assert "Today is 2026-11-05 (Thursday), Cairo time" in str(lead.seen[0])


async def test_a_projects_no_search_reply_carries_the_fix(make_engine, project):
    # the General chat's no-search answer had «Set up web search»; the project chat's had none
    lead = scripted(said("مقدرتش أدوّر على الإنترنت دلوقتي، ومفيش سعر النهارده عندي."))
    engine = await started(make_engine(links(lead=lead)))
    brief = await engine.start_brief(project, "إيه سعر الحديد النهارده؟")
    events = await finish(engine, brief)
    [notice] = datas(events, "notice")
    assert notice.data["fix"] == "search"
    store = store_of(engine, project)
    replayed = _stored_events(store, store.brief(brief), engine)
    assert datas(replayed, "notice")[0].data["fix"] == "search"


async def test_every_specialist_gets_ones_principles(make_engine, project):
    # whatever the Lead writes for a specialist, ONE adds what a rate includes and today's date
    specialist = scripted(said("تم - عينة"), said("تم - عينة"))
    lead = scripted(*team_steps(), said("الحصر والتسعير خلصوا - عينة"))
    engine = await started(make_engine(links(lead=lead, specialist=specialist)))
    await finish(engine, await engine.start_brief(project, "سعّر البنود - عينة"))
    seen = str(specialist.seen[0])
    assert "A supply-only quote never covers labour" in seen
    assert "goes through calculate with its inputs and formula" in seen
    assert "Today is 2026-11-05" in seen


async def test_the_work_log_names_an_item_by_its_code(make_engine, project, registry):
    # «بيسجّل rate البند 707d81e9…» and «بيضيف المصدر «None»» in the work log
    rec = registry.get(project)
    [item] = boq(rec, 1)
    lead = scripted(
        call("ledger_numbers", {"item": item}),
        said("البند 01-01-001 لسه مالوش فئة."),
    )
    engine = await started(make_engine(links(lead=lead)))
    events = await finish(engine, await engine.start_brief(project, "البند الأول متسعّر؟"))
    [step] = [e for e in events if isinstance(e, Progress) and e.tool]
    assert "01-01-001" in step.text["ar"] and item not in step.text["ar"]


async def test_unread_citation_cannot_be_laundered_by_project_text(make_engine, project, registry):
    from qsone.records.files import add_file
    from tests.samples import sample_pdf

    rec = registry.get(project)
    file = add_file(
        rec,
        "sample-contract.pdf",
        sample_pdf([["Sample terms"], ["Security 350000 USD"]]),
        actor="t",
    )
    lead = scripted(
        call("files_read", {"file_id": file.id, "pages": "1"}),
        said("Security is 350,000 USD, page 2."),
        said("Security is 350,000 USD, page 2."),
    )
    engine = await started(make_engine(links(lead=lead)))
    events = await asyncio.wait_for(
        finish(engine, await engine.start_brief(project, "What is the security?")), 10
    )
    assert "not read in this Brief" in str(lead.seen[-1])
    assert "350,000" not in reply(events)


async def test_import_offer_is_routed_back_to_rows_card(make_engine, project):
    lead = scripted(
        said("I am ready to import the BOQ. Please confirm if I should proceed."),
        said("I could not find the BOQ file."),
    )
    engine = await started(make_engine(links(lead=lead)))
    await asyncio.wait_for(finish(engine, await engine.start_brief(project, "Import the BOQ.")), 10)
    assert "boq_import" in str(lead.seen[1])
    assert "rows card" in str(lead.seen[1])
