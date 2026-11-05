"""Close project never says nothing is open while a card waits for the engineer (C2): the running
Briefs' cards and an "I understood this" card not yet approved count as waiting.

Scripted models only, behind fake connectors; no test calls a real AI. Synthetic «عينة» data
only."""

# ruff: noqa: F811 (the engine fixtures, imported)

from qsone.journey import closing, understand
from qsone.journey.understand import FileSort, ProjectUnderstood
from qsone.records.files import add_file
from tests.engine_fakes import call, scripted
from tests.samples import sample_pdf
from tests.team_samples import BRIEF
from tests.test_briefs_left import QUESTION
from tests.test_engine_runner import (  # noqa: F401
    links,
    make_engine,
    no_budget_card,
    project,
    registry,
    started,
    store_of,
    until,
)


async def test_a_card_waiting_in_the_project_chat_counts(make_engine, project):
    engine = await started(make_engine(links(lead=scripted(call("ask_engineer", QUESTION)))))
    brief = await engine.start_brief(project, BRIEF)
    await until(lambda: store_of(engine, project).pending(brief))
    rec = engine.projects.get(project)
    assert closing.waiting(rec, engine.waiting(project)) == 1


async def test_an_understood_card_not_yet_approved_counts_until_it_is(make_engine, project):
    engine = await started(make_engine(links(lead=scripted())))
    rec = engine.projects.get(project)
    assert closing.waiting(rec, 0) == 0  # nothing understood yet: nothing to approve
    letter = add_file(
        rec, "خطاب - عينة.pdf", sample_pdf([["عينة"]]), actor="engineer", folder="مناقصة"
    ).id
    sort = ProjectUnderstood(files=[FileSort(file_id=letter, label="خطاب الدعوة", why="عينة")])
    understand.save(rec, sort, actor="lead_qs")
    assert closing.waiting(rec, 0) == 1
    understand.correct(rec, {}, approve=True)
    assert closing.waiting(rec, 0) == 0
