"""Plan 5, Task 15: every tool wired into the engine. The registry holds every tool with a short
recipe and a runnable example; the Lead QS, the Checking QS and the General chat's Lead get
decision 7's lists; the app builds the tools' services and closes them after the engine; and a
scripted Lead uses the tools in a real Brief, through the toolset and through /mcp.

Scripted models and the fake `claude` only: no test calls a real AI, the web or Prices.
Synthetic «عينة» data only."""

import json
import re
from pathlib import Path

import httpx
from fastapi.testclient import TestClient
from pydantic_ai.messages import ModelRequest, ToolReturnPart

from qsone import copy, keys
from qsone.app import create_app
from qsone.deliverables.tools import OUTPUTS_TOOLS
from qsone.engine import agents, costs, general, roles
from qsone.engine.connectors.claude_code import ID as CLAUDE_CODE
from qsone.engine.connectors.claude_code import ClaudeCodeConnector
from qsone.engine.tools import REGISTRY
from qsone.engine.tools_records import RECORDS_TOOLS
from qsone.engine.types import ModelChoice
from qsone.prices.client import DEV_KEY_USER, HttpPrices
from qsone.records import files
from qsone.tools.services import Services
from qsone.tools.web import WEB_TOOLS
from qsone.web import fetch
from tests.bench.fake import openable
from tests.conftest import AUTH, SECRET
from tests.engine_fakes import FakeSleep, call, fake_claude_command, read_fake_log, scripted
from tests.samples import sample_pdf
from tests.test_engine_routes import message, read_until
from tests.test_engine_runner import links

NEW = (
    "files_list",
    "files_read",
    "boq_preview",
    "boq_import",
    "web_search",
    "web_read",
    "prices_lookup",
    "prices_propose",
    "ask_engineer",
    "note_lesson",
    "sandbox_run",
    "sandbox_rerun",
    "connector_tools",
    "connector_call",
)
EXTENDED = ("search_records", "add_source", "add_item", "record_number", "correct_number")
LEAD = (
    "files_list",
    "files_read",
    "boq_preview",
    "boq_import",
    "ask_engineer",
    "prices_lookup",
    "note_lesson",
    "connector_tools",
)
CHECKER = ("files_list", "files_read", "ledger_numbers", "search_records", "sandbox_rerun")
SPECIALISTS_ONLY = ("web_search", "web_read", "prices_propose", "sandbox_run", "connector_call")
QUESTION = {"id": "q1", "text": "الخرسانة جاهزة ولا خلط في الموقع؟", "options": ["جاهزة", "موقع"]}
SPEC = [["Specification - sample", "Concrete grade C30"], ["Page two - sample"]]


# The registry and the lists -------------------------------------------------------------------


def test_every_tool_is_registered_as_a_short_recipe_with_a_runnable_example():
    for name in (*NEW, *EXTENDED):
        tool = REGISTRY[name]
        words = tool.description.split()
        assert len(words) <= 120, (name, len(words))
        recipe, example = tool.description.rsplit("\nExample:\n", 1)
        assert recipe.strip() and "Example:" not in recipe, name  # one example, at the end
        assert tool.example == json.loads(example), name
        if name != "connector_call":  # its example names a Connector the engineer may not have
            assert tool.args.model_validate(tool.example), name  # it runs as written


def test_the_lead_and_the_checker_get_decision_7s_tools():
    lead, checker = agents.lead_spec().tools, agents.checker_spec().tools
    assert set(LEAD) <= set(lead) and set(RECORDS_TOOLS) <= set(lead)
    assert not set(SPECIALISTS_ONLY) & set(lead)  # web, proposals, the Sandbox: specialists
    assert set(CHECKER) <= set(checker)
    assert {"read_chunk", "find_items"} <= set(checker)
    for name in checker:
        tool = REGISTRY[name]
        assert tool.risk == "read" and tool.risk_for is None, name  # never online or outside


def test_the_general_lead_gets_the_hand_off_tools_and_no_project_tool():
    lead, found = agents.lead_spec().tools, general.lead_spec().tools
    project_only = general.project_only()
    assert set(general.GENERAL_TOOLS) <= set(found)
    assert set(found) == {
        *(t for t in lead if t not in project_only),
        *general.GENERAL_TOOLS,
        *WEB_TOOLS,
    }
    assert not {"note_lesson", "boq_preview", "boq_import", *RECORDS_TOOLS, *OUTPUTS_TOOLS} & set(
        found
    )
    assert {"files_list", "files_read", "ask_engineer", "prices_lookup"} <= set(found)


def test_the_general_lead_searches_the_web_itself():
    """No project's context to keep small in the General chat: a question about market news or
    prices is the Lead's own, so it has the web tools and its instructions say so (a project's
    Lead still gives web work to a specialist, decision 7)."""
    spec = general.lead_spec()
    assert set(WEB_TOOLS) <= set(spec.tools)
    assert "web_search" in spec.instructions and "web_read" in spec.instructions
    assert not set(WEB_TOOLS) & set(agents.lead_spec().tools)


# The app's services ---------------------------------------------------------------------------


def test_the_app_builds_the_services_and_closes_them_after_the_engine():
    keys.set_key(DEV_KEY_USER, "prices-key-sample")
    app = create_app(SECRET, sleep=FakeSleep())
    with TestClient(app):
        services = app.state.engine.services
        assert isinstance(services, Services) and isinstance(services.prices, HttpPrices)
        assert services.connectors is app.state.connectors
        assert services.engineer() is app.state.engine.engineer_records()
        pool = services.http._transport._pool
        assert isinstance(pool._network_backend, fetch.GuardedBackend)
    assert services.http.is_closed and app.state.engine.services is None


def test_without_a_prices_key_there_is_no_prices_client():
    app = create_app(SECRET, sleep=FakeSleep())
    with TestClient(app):
        assert app.state.engine.services.prices is None


def test_the_engines_own_services_are_kept():
    app = create_app(SECRET, sleep=FakeSleep())
    given = object()
    app.state.engine.services = given
    with TestClient(app):
        assert app.state.engine.services is given
    assert app.state.engine.services is given  # a test's own fakes are not closed by the app


# A scripted Lead in a real Brief --------------------------------------------------------------


def app_for(found):
    costs.save_caps({"budget_above": "100"})
    return create_app(SECRET, connectors=lambda: found, sleep=FakeSleep())


def new_project(client: httpx.Client, url: str) -> str:
    return client.post(f"{url}/projects", json={"name": "مدرسة - عينة"}).json()["id"]


def add_spec(app, project_id: str) -> str:
    rec = app.state.projects.get(project_id)
    return files.add_file(rec, "مواصفات - عينة.pdf", sample_pdf(SPEC), actor="engineer").id


def results(messages) -> dict[str, str]:
    """Each tool's last result in a model request's history, by tool name."""
    return {
        p.tool_name: p.content
        for m in messages
        if isinstance(m, ModelRequest)
        for p in m.parts
        if isinstance(p, ToolReturnPart)
    }


def answer_the_question(client: httpx.Client, url: str, lines) -> tuple[list[dict], list[dict]]:
    """Reads the stream to the question card, answers it, and reads on to the end."""
    before = read_until(lines, "data-card")
    card = before[-1]
    assert card["data"]["kind"] == "question" and card["data"]["payload"]["questions"] == [QUESTION]
    r = client.post(
        f"{url}/cards/{card['id']}", json={"choice": "sent", "answers": {"q1": "جاهزة"}}
    )
    assert r.status_code == 204
    return before, read_until(lines, "finish")


def said(chunks: list[dict]) -> str:
    return "".join(c["delta"] for c in chunks if c["type"] == "text-delta")


def test_a_scripted_lead_reads_a_file_then_asks_the_engineer(serve_app):
    holder: dict = {}

    def read_it(messages, info):
        return call("files_read", {"file_id": holder["file"], "pages": "1"})

    def done(messages, info):
        seen = results(messages)
        holder["seen"] = seen
        return "الدرجة C30 والخرسانة جاهزة - عينة" if "جاهزة" in seen["ask_engineer"] else "؟"

    lead = scripted(read_it, call("ask_engineer", {"questions": [QUESTION]}), done)
    app = app_for(links(lead=lead))
    url = serve_app(app)
    with httpx.Client(timeout=15, headers=AUTH) as client:
        pid = new_project(client, url)
        holder["file"] = add_spec(app, pid)
        with client.stream("POST", f"{url}/chat", json=message("درجة الخرسانة كام؟", pid)) as r:
            before, after = answer_the_question(client, url, r.iter_lines())
    progress = [c["data"]["text"] for c in before if c["type"] == "data-progress"]
    assert (
        copy.fill(
            copy.DOING_FILES_READ_PAGE_OF,
            name=copy.file_name("مواصفات - عينة.pdf"),
            page="1",
            total="2",
        )
        in progress
    )
    all_chunks = before + after
    card_at = next(i for i, c in enumerate(all_chunks) if c["type"] == "data-card")
    wait_at = next(
        i
        for i, c in enumerate(all_chunks)
        if c["type"] == "data-progress" and c["data"]["text"] == copy.DOING_ASK
    )
    assert card_at < wait_at
    assert said(after).endswith("الدرجة C30 والخرسانة جاهزة - عينة")  # the results reached it
    read, asked = holder["seen"]["files_read"], holder["seen"]["ask_engineer"]
    assert "Concrete grade C30" in read and f"file:{holder['file']}#page=1" in read
    assert '"q1": "جاهزة"' in asked and "card:" in asked


def lists_files(seen: list):
    def step(messages, info):
        # the tools it can use: those sent, and those of the groups it can open
        seen.append({t.name for t in info.function_tools} | openable(info))
        return call("files_list")

    return step


def test_a_project_brief_gets_its_records_and_the_general_chat_engineer_records(serve_app):
    seen_tools: list = []
    answers: list = []

    def done(messages, info):
        answers.append(results(messages)["files_list"])
        return "تمام - عينة"

    lead = scripted(lists_files(seen_tools), done, lists_files(seen_tools), done)
    app = app_for(links(lead=lead))
    url = serve_app(app)
    with httpx.Client(timeout=15, headers=AUTH) as client:
        pid = new_project(client, url)
        in_project = add_spec(app, pid)
        eng = app.state.engine.engineer_records()
        own = files.add_file(eng, "أسعاري - عينة.txt", "أسمنت 3950".encode(), actor="engineer").id
        client.post(f"{url}/chat", json=message("إيه الملفات؟ - عينة", pid))
        client.post(f"{url}/chat", json=message("إيه الملفات؟ - عينة"))  # the General chat
    project_list, general_list = answers
    assert f"file:{in_project}" in project_list and f"file:{own}" not in project_list
    assert f"file:{own}" in general_list and f"file:{in_project}" not in general_list
    project_tools, general_tools = seen_tools
    assert {"boq_import", "note_lesson", "add_source"} <= project_tools
    assert not {"boq_import", "note_lesson", "add_source"} & general_tools
    assert set(general.GENERAL_TOOLS) <= general_tools


# The same calls through /mcp (the Subscription Link) --------------------------------------------


_STAMP = re.compile(r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(?::\d{2})?(?: UTC)?")


def same(text: str) -> str:
    """A result without what differs between two runs: its fence id and the times read."""
    return _STAMP.sub("<time>", re.sub(r"<<(/?)data id=\w+", r"<<\1data id=<fence>", text))


def test_the_same_calls_through_mcp_give_the_same_results(serve_app, tmp_path):
    holder: dict = {}

    def read_it(messages, info):
        return call("files_read", {"file_id": holder["file"], "pages": "1"})

    def done(messages, info):
        holder["seen"] = results(messages)
        return "تم - عينة"

    lead = scripted(read_it, call("ask_engineer", {"questions": [QUESTION]}), done)
    script_file, log = tmp_path / "script.json", tmp_path / "claude.log"
    claude = ClaudeCodeConnector(
        None, command_prefix=fake_claude_command(script=script_file, log=log)
    )
    app = app_for([*links(lead=lead, only_anthropic=True), claude])
    url = serve_app(app)
    with httpx.Client(timeout=30, headers=AUTH) as client:
        pid = new_project(client, url)
        holder["file"] = add_spec(app, pid)
        with client.stream("POST", f"{url}/chat", json=message("درجة الخرسانة كام؟", pid)) as r:
            answer_the_question(client, url, r.iter_lines())
        script = [
            "init",
            {"mcp_call": {"tool": "files_read", "args": {"file_id": holder["file"], "pages": "1"}}},
            {"mcp_call": {"tool": "ask_engineer", "args": {"questions": [QUESTION]}}},
            {"text": "تم - عينة"},
            "result",
        ]
        Path(script_file).write_text(json.dumps(script, ensure_ascii=False), encoding="utf-8")
        roles.choose("lead", ModelChoice(CLAUDE_CODE, "sonnet"))
        with client.stream("POST", f"{url}/chat", json=message("درجة الخرسانة كام؟", pid)) as r:
            answer_the_question(client, url, r.iter_lines())
    [run] = read_fake_log(log)
    assert run["ended"] == "done"
    by_mcp = {c["tool"]: c for c in run["mcp"]}
    assert not by_mcp["files_read"]["is_error"] and not by_mcp["ask_engineer"]["is_error"]
    assert "Concrete grade C30" in by_mcp["files_read"]["text"]
    assert '"q1": "جاهزة"' in by_mcp["ask_engineer"]["text"]
    assert same(by_mcp["files_read"]["text"]) == same(holder["seen"]["files_read"])
    card_id = re.compile(r"[0-9a-f]{32}")  # each run's own card
    assert card_id.sub("<card>", same(by_mcp["ask_engineer"]["text"])) == card_id.sub(
        "<card>", same(holder["seen"]["ask_engineer"])
    )
