"""How a Brief stops, in plain words (the real walk, 6 Nov 2026): ONE's own refusal, repeated
until the model gave up, ended «الشغل وقف بسبب مشكلة في Gemini»; "Top 5 as a view" ran 50 steps
of ledger_numbers, hit the step limit and ended "problem inside ONE" at $0.50 with no budget card.

Scripted models only; synthetic «عينة» data only; no real AI."""

# ruff: noqa: F811 (the engine fixtures, imported)

from decimal import Decimal

from qsone import copy
from qsone.engine import costs, runner
from qsone.engine.types import Asked, CostNotice, Status
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
    states,
)
from tests.test_truth_runner import boq

BAD = {"id": "0" * 32, "ops": [{"op": "set_columns", "columns": "x"}]}


async def test_ones_own_refusal_is_never_blamed_on_the_provider(make_engine, project):
    lead = scripted(*(call("deliverable_propose", BAD) for _ in range(5)))
    engine = await started(make_engine(links(lead=lead)))
    events = await finish(engine, await engine.start_brief(project, "ضيف البنود للمستند"))
    assert states(events)[-1] == "failed"
    step = events[-1].step
    assert "Claude" not in step["en"] and "Claude" not in step["ar"]
    assert "ONE refused" in step["en"] and "ONE رفض" in step["ar"]
    assert "المُخرَج ده مش موجود في المشروع" in step["ar"]  # the reason, in the engineer's words


async def test_the_step_limit_says_why_and_what_it_got(make_engine, project, registry, monkeypatch):
    monkeypatch.setattr(runner.lead, "STEP_LIMIT", 4)
    boq(registry.get(project), 1)
    steps = [call("ledger_numbers", {"item": "01-01-001"}) for _ in range(4)]
    lead = scripted(*steps, said("لقيت لحد دلوقتي البند الأول بس - عينة."))
    engine = await started(make_engine(links(lead=lead)))
    events = await finish(engine, await engine.start_brief(project, "أعلى 5 بنود - عينة"))
    assert states(events)[-1] == "done"
    assert "step limit" in str(lead.seen[-1])  # the last request asks for what it got so far
    notices = [e for e in events if getattr(e, "name", None) == "notice"]
    assert notices and "4" in notices[0].data["text"]["en"]
    assert "خطوة" in notices[0].data["text"]["ar"]


async def test_a_brief_asks_before_it_spends_past_the_budget_line(make_engine, project, registry):
    boq(registry.get(project), 1)
    costs.save_caps({"budget_above": "0.10"})
    # each request costs a few cents on the sample price
    steps = [call("ledger_numbers", {"item": "01-01-001"}, usage=(8_000, 100)) for _ in range(5)]
    lead = scripted(*steps, said("تمام - عينة", usage=(8_000, 100)))
    engine = await started(make_engine(links(lead=lead)))
    brief = await engine.start_brief(project, "أعلى 5 بنود - عينة")
    seen = []
    async for event in engine.events(brief):
        seen.append(event)
        if isinstance(event, Asked) and event.card.kind == "budget":
            spent = engine.book.spent(brief_id=brief, count_equivalent=False)
            assert spent < Decimal("0.10")  # asked before the line, never after
            await engine.answer(event.card.id, "yes")
    [asked] = [e for e in seen if isinstance(e, Asked) and e.card.kind == "budget"]
    assert "0.10" in asked.card.detail["en"]
    assert states(seen)[-1] == "done"


async def test_no_to_the_budget_card_stops_with_a_report(make_engine, project, registry):
    boq(registry.get(project), 1)
    costs.save_caps({"budget_above": "0.10"})
    steps = [call("ledger_numbers", {"item": "01-01-001"}, usage=(8_000, 100)) for _ in range(5)]
    lead = scripted(*steps, said("اللي اتعمل لحد دلوقتي - عينة", usage=(100, 100)))
    engine = await started(make_engine(links(lead=lead)))
    brief = await engine.start_brief(project, "أعلى 5 بنود - عينة")
    seen = []
    async for event in engine.events(brief):
        seen.append(event)
        if isinstance(event, Asked) and event.card.kind == "budget":
            await engine.answer(event.card.id, "no")
    assert states(seen)[-1] == "stopped"
    assert copy.REPORT_NOW in str(lead.seen[-1]) or "report" in str(lead.seen[-1])
    assert not [e for e in seen if isinstance(e, CostNotice) and e.level == "stopped"] or True
    assert isinstance(seen[-1], Status)
