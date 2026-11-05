"""The "I understood this" card (Plan 8, Task 6): the check that sends a result back with the
exact fix, facts saved with their sources, the engineer's corrections, and the Brief end to end
with a scripted Lead QS (never a real AI). Synthetic «عينة» files only."""

import json
from dataclasses import dataclass, field, replace
from decimal import Decimal
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from qsone import copy, usage
from qsone.app import create_app
from qsone.engine import agents, costs, general
from qsone.engine.connectors.claude_code import AgentOutcome
from qsone.engine.runner import Engine
from qsone.engine.tools import ModelRetry, call
from qsone.engine.types import Data, ModelChoice
from qsone.journey import understand
from qsone.journey.understand import Counted, FileSort, ProjectUnderstood, Sourced
from qsone.projects import Projects
from qsone.records.files import add_file
from qsone.records.ledger import history
from qsone.records.project import RecordsError
from tests.conftest import AUTH, SECRET
from tests.engine_fakes import OPUS, scripted, text
from tests.engine_fakes import call as step
from tests.fakes_tools import tool_ctx
from tests.samples import sample_pdf, sample_xlsx
from tests.test_client_boq import import_boq
from tests.test_engine_runner import FakeLink, links

LETTER = sample_pdf([["Tender letter - sample"], ["Client: Authority - sample", "Due 2026-12-01"]])


@pytest.fixture(autouse=True)
def no_budget_card():
    costs.save_caps({"budget_above": "100"})


@pytest.fixture
def letter(rec) -> str:
    return add_file(rec, "خطاب الدعوة - عينة.pdf", LETTER, actor="engineer", folder="مناقصة").id


@pytest.fixture
def boq_file(rec) -> str:
    data = sample_xlsx({"BOQ": [["03/02", "خرسانة - عينة", "م3", 1]]})
    return add_file(rec, "جدول الكميات - عينة.xlsx", data, actor="engineer").id


def fact_id(rec, name: str) -> str:
    with rec.read() as c:
        (found,) = c.execute(
            "SELECT id FROM items WHERE kind = 'project_fact'"
            " AND json_extract(fields, '$.name') = ?",
            (name,),
        ).fetchone()
    return found


# The check ------------------------------------------------------------------------------------


def test_a_fact_without_its_source_goes_back_with_the_fix(rec, letter):
    bad = ProjectUnderstood(
        client=Sourced(value="هيئة - عينة", file_id="nope", locator={"page": 1})
    )
    assert understand.check(rec, bad) == [copy.FACT_FILE_UNKNOWN["en"].format(file_id="nope")]
    none = ProjectUnderstood(contract_type=Sourced(value="Lump sum - sample"))
    assert understand.check(rec, none) == [
        copy.FACT_NEEDS_SOURCE["en"].format(fact="contract_type")
    ]


def test_a_place_must_be_in_the_file_and_a_date_must_be_real(rec, letter, boq_file):
    wrong_page = Sourced(value="هيئة - عينة", file_id=letter, locator={"page": 9})
    wrong_row = Sourced(value="2026-02-30", file_id=boq_file, locator={"sheet": "BOQ", "row": 7})
    got = understand.check(rec, ProjectUnderstood(client=wrong_page, submission_date=wrong_row))
    assert got == [
        copy.FACT_LOCATOR_UNKNOWN["en"].format(fact="client", file_id=letter),
        copy.FACT_LOCATOR_UNKNOWN["en"].format(fact="submission_date", file_id=boq_file),
        copy.FACT_DATE_BAD["en"].format(fact="submission_date"),
    ]
    good = ProjectUnderstood(
        client=Sourced(value="هيئة - عينة", file_id=f"file:{letter}", locator={"page": 2}),
        submission_date=Sourced(
            value="2026-12-01", file_id=boq_file, locator={"sheet": "BOQ", "row": 1}
        ),
        files=[FileSort(file_id=letter, label="خطاب الدعوة", why="فيه اسم العميل")],
    )
    assert understand.check(rec, good) == []


def test_a_replaced_file_is_not_a_current_file(rec, letter):
    add_file(rec, "خطاب الدعوة - عينة.pdf", sample_pdf([["v2"]]), actor="engineer", folder="مناقصة")
    sort = ProjectUnderstood(files=[FileSort(file_id=letter, label="خطاب", why="عينة")])
    assert understand.check(rec, sort) == [copy.FACT_FILE_UNKNOWN["en"].format(file_id=letter)]


async def test_count_must_come_from_code(rec):
    typed = ProjectUnderstood(items_count=Counted(value="120", trace_id="made-up"))
    assert understand.check(rec, typed) == [copy.COUNT_NEEDS_TRACE["en"]]
    assert understand.check(rec, ProjectUnderstood(items_count=Counted(value="2"))) == [
        copy.COUNT_NEEDS_TRACE["en"]
    ]
    await import_boq(rec)  # the one BOQ import path: boq_import, as the Lead QS uses it
    with rec.read() as c:
        (import_id,) = c.execute(
            "SELECT row_id FROM audit WHERE table_name = 'boq_imports'"
        ).fetchone()
    lied = ProjectUnderstood(items_count=Counted(value="999", trace_id=import_id))
    assert understand.check(rec, lied) == []
    understand.save(rec, lied, actor="Lead QS")
    count = understand.facts(rec)["facts"]["items_count"]
    assert count["value"] == "2" and count["source"] == {"kind": "count", "trace_id": import_id}


# Saving, reading, correcting -------------------------------------------------------------------


def test_saved_facts_carry_their_source_and_the_engineers_correction(rec, boq_file):
    understand.save(
        rec,
        ProjectUnderstood(
            submission_date=Sourced(
                value="2026-12-01", file_id=boq_file, locator={"sheet": "BOQ", "row": 1}
            ),
            missing=["تقرير التربة"],
            files=[FileSort(file_id=boq_file, label="مقايسة", why="بنود وكميات")],
        ),
        actor="Lead QS",
    )
    first = understand.facts(rec)
    assert first["facts"]["submission_date"]["by"] == "lead_qs"
    assert first["facts"]["submission_date"]["source"] == {
        "kind": "file",
        "file_id": boq_file,
        "locator": {"sheet": "BOQ", "row": 1},
        "file_name": "جدول الكميات - عينة.xlsx",
    }
    assert first["missing"] == ["تقرير التربة"] and first["approved"] is False
    assert [(f["name"], f["label"]) for f in first["files"]] == [
        ("جدول الكميات - عينة.xlsx", "مقايسة")
    ]
    understand.correct(rec, {"submission_date": "2026-12-08"}, approve=True)
    f = understand.facts(rec)
    assert f["facts"]["submission_date"]["value"] == "2026-12-08"
    assert f["facts"]["submission_date"]["by"] == "engineer"
    assert f["facts"]["submission_date"]["source"]["kind"] == "engineer"
    assert f["approved"] is True
    assert [h["action"] for h in history(rec, fact_id(rec, "submission_date"))] == [
        "create",
        "update",
    ]


def test_a_new_result_takes_the_approval_back(rec, boq_file):
    understand.correct(rec, {"client": "هيئة - عينة"}, approve=True)
    assert understand.facts(rec)["approved"] is True
    understand.save(rec, ProjectUnderstood(), actor="Lead QS")
    assert understand.facts(rec)["approved"] is False


def test_the_engineer_gives_a_real_date_or_nothing_is_saved(rec):
    with pytest.raises(RecordsError) as e:
        understand.correct(rec, {"client": "هيئة", "submission_date": "8/12"}, approve=True)
    assert e.value.status == 422 and "ميعاد التقديم" in e.value.text["ar"]
    assert understand.facts(rec)["facts"] == {} and understand.facts(rec)["approved"] is False


async def test_the_tool_refuses_with_the_fix_and_saves_nothing(rec, letter):
    ctx = tool_ctx(rec)
    bad = {"client": {"value": "هيئة - عينة", "file_id": "nope", "locator": {"page": 1}}}
    with pytest.raises(ModelRetry) as e:
        await call("understood", bad, ctx)
    assert "nope" in e.value.message and understand.facts(rec)["facts"] == {}
    good = {"client": {"value": "هيئة - عينة", "file_id": letter, "locator": {"page": 2}}}
    out = json.loads(await call("understood", good, ctx))
    assert out["saved"] is True and out["facts"] == ["client"]
    assert [e.name for e in ctx.host.events if isinstance(e, Data)] == ["understood"]


def test_the_instruction_is_short_and_only_the_project_lead_has_the_tool():
    assert agents.words(understand.INSTRUCTION) <= 120
    assert "understood" in agents.lead_spec().tools
    assert "understood" not in general.lead_spec().tools


# The Brief end to end ----------------------------------------------------------------------------


@pytest.fixture
def registry(data_dir):
    found = Projects(data_dir)
    yield found
    found.close_all()


@pytest.fixture
async def make_engine(data_dir, registry, fake_sleep, fake_clock):
    made: list[Engine] = []

    def make(found) -> Engine:
        engine = Engine(
            projects=registry,
            data_dir=data_dir,
            connectors=lambda: found,
            clock=fake_clock,
            sleep=fake_sleep,
        )
        made.append(engine)
        return engine

    yield make
    for engine in made:
        await engine.shutdown()


async def test_the_brief_end_to_end_with_a_function_model(make_engine, registry, monkeypatch):
    project = registry.create("مناقصة - عينة", "engineer")["id"]
    rec = registry.get(project)
    letter = add_file(rec, "خطاب الدعوة - عينة.pdf", LETTER, actor="engineer", folder="مناقصة").id
    tracked = []
    monkeypatch.setattr(usage, "track", lambda name, **data: tracked.append((name, data)))
    bad = {"client": {"value": "هيئة - عينة", "file_id": "nope", "locator": {"page": 1}}}
    good = {
        "client": {"value": "هيئة - عينة", "file_id": letter, "locator": {"page": 2}},
        "files": [{"file_id": letter, "label": "خطاب الدعوة", "why": "فيه العميل والميعاد"}],
    }
    lead = scripted(
        step("files_list", {}),
        step("understood", bad),
        step("understood", good),
        text("فهمت المناقصة - عينة: العميل والميعاد في البطاقة."),
    )
    engine = make_engine(links(lead=lead))
    await engine.start()
    brief = await understand.start(rec, engine)
    events = [e async for e in engine.events(brief)]
    await engine.result(brief)
    assert understand.INSTRUCTION in str(lead.seen[0])
    assert "nope" in str(lead.seen[2])  # the fix went back
    f = understand.facts(rec)
    assert f["facts"]["client"]["source"]["file_id"] == letter
    assert f["files"][0]["folder"] == "مناقصة"
    assert any(isinstance(e, Data) and e.name == "understood" for e in events)
    replayed = engine.chat_messages(project)[-1]["parts"]
    assert any(p["type"] == "data-understood" for p in replayed)
    assert ("project_new", {"files": 1, "zips": 0, "from_folder": True}) in tracked
    understand.project_new_once(rec)  # a second understanding sends nothing more
    assert sum(1 for name, _ in tracked if name == "project_new") == 1


@dataclass
class FakeClaudeCode:
    """An agent connector standing in for Claude Code: records each job's instructions."""

    id: str = "claude-code"
    name: str = "Claude Code"
    provider: str = "anthropic"
    kind: str = "agent"
    on_device: bool = False
    jobs: list = field(default_factory=list)

    async def cards(self):
        return [replace(OPUS, choice=ModelChoice("claude-code", "sonnet"))]

    async def run(self, job, emit):
        self.jobs.append(job)
        return AgentOutcome("تم - عينة", None, "done", (), Decimal("0"))


async def test_claude_code_gets_the_briefs_instruction(make_engine, registry):
    project = registry.create("مناقصة - عينة", "engineer")["id"]
    claude = FakeClaudeCode()
    engine = make_engine([claude])
    engine.base_url = "http://127.0.0.1:9/"
    await engine.start()
    brief = await understand.start(registry.get(project), engine)
    await engine.result(brief)
    assert understand.INSTRUCTION in claude.jobs[0].spec.instructions
    assert "understood" in claude.jobs[0].tools


# The routes ----------------------------------------------------------------------------------


def test_routes(monkeypatch):
    def lead_steps(messages, info):
        return text("لسه - عينة")

    model = scripted(lead_steps)
    found = [FakeLink("anthropic", "Claude", "anthropic", {OPUS.choice.model: model}, [OPUS])]
    with TestClient(create_app(SECRET, connectors=lambda: found)) as client:
        project = client.post("/projects", json={"name": "مناقصة - عينة"}, headers=AUTH).json()
        pid = project["id"]
        assert client.get(f"/projects/{pid}/facts", headers=AUTH).json() == {
            "facts": {},
            "missing": [],
            "files": [],
            "approved": False,
        }
        r = client.post(f"/projects/{pid}/understand", headers=AUTH)
        assert r.status_code == 202 and set(r.json()) == {"brief_id"}
        busy = client.post(f"/projects/{pid}/understand", headers=AUTH)
        assert busy.status_code in (202, 409)
        body = {"facts": {"client": {"value": "هيئة - عينة"}}, "approve": True}
        answer = client.put(f"/projects/{pid}/facts", json=body, headers=AUTH).json()
        assert answer["facts"]["client"]["by"] == "engineer" and answer["approved"] is True
        unknown = {"facts": {"anything": {"value": "x"}}}
        assert client.put(f"/projects/{pid}/facts", json=unknown, headers=AUTH).status_code == 422
        bad_date = {"facts": {"submission_date": {"value": "غدًا"}}}
        r = client.put(f"/projects/{pid}/facts", json=bad_date, headers=AUTH)
        assert r.status_code == 422 and r.json()["error"]["en"].startswith("The submission date")
        assert client.get("/projects/" + "0" * 32 + "/facts", headers=AUTH).status_code == 404
        name = quote("خطاب - عينة.pdf")
        r = client.post(f"/projects/{pid}/files?name={name}&folder=x", content=LETTER, headers=AUTH)
        assert r.status_code == 201


def test_without_ai_understand_says_why():
    with TestClient(create_app(SECRET, connectors=lambda: [])) as client:
        pid = client.post("/projects", json={"name": "مناقصة - عينة"}, headers=AUTH).json()["id"]
        r = client.post(f"/projects/{pid}/understand", headers=AUTH)
        assert r.status_code == 409 and r.json()["error"]["en"]
