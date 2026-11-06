"""The General chat (Plan 7, Task 3): the Lead QS outside every project, with three tools only. It
lists the projects that are not Confidential, hands a request to one, or offers a new one. The
screen shows the last two as cards; nothing moves or is created until the engineer clicks.

Scripted models behind fake connectors; no test calls a real AI. Synthetic «عينة» data only."""

import json

import pytest
from fastapi.testclient import TestClient
from pydantic_ai.messages import ModelRequest, RetryPromptPart, ToolReturnPart

from qsone import copy
from qsone.app import create_app
from qsone.deliverables.tools import OUTPUTS_TOOLS
from qsone.engine import costs, general, tool_groups
from qsone.engine.team import TEAM_TOOLS
from qsone.engine.tools_records import RECORDS_TOOLS
from tests.conftest import AUTH, SECRET, ui_message
from tests.engine_fakes import FakeSleep, call, scripted
from tests.engine_fakes import text as said
from tests.test_engine_runner import links

GENERAL = "general"


@pytest.fixture(autouse=True)
def no_budget_card():
    costs.save_caps({"budget_above": "100"})


def chunks(body: str) -> list[dict]:
    return [json.loads(line[6:]) for line in body.splitlines() if line.startswith("data: {")]


def app_for(*steps):
    model = scripted(*steps)
    return create_app(SECRET, connectors=lambda: links(lead=model), sleep=FakeSleep())


def new_project(client, name: str, *, confidential: bool = False) -> str:
    pid = client.post("/projects", json={"name": name}, headers=AUTH).json()["id"]
    if confidential:
        rec = client.app.state.projects.get(pid)
        with rec.write("engineer") as conn:
            rec.set_meta(conn, "confidential", "1")
    return pid


def ask(client, text: str):
    return client.post("/chat", json=ui_message(text) | {"id": GENERAL}, headers=AUTH)


def last_tool_answer(messages) -> str:
    """What the last tool call gave the model: its result, or its retry text."""
    part = next(
        p
        for m in reversed(messages)
        if isinstance(m, ModelRequest)
        for p in m.parts
        if isinstance(p, ToolReturnPart | RetryPromptPart)
    )
    return part.content if isinstance(part.content, str) else json.dumps(part.content)


class Seen:
    def __init__(self) -> None:
        self.answers: list[str] = []
        self.tools: list[set[str]] = []

    def answer(self, reply: str = "تمام - عينة"):
        def step(messages, info):
            self.answers.append(last_tool_answer(messages))
            return reply

        return step

    def tools_then(self, step):
        def seen(messages, info):
            self.tools.append({t.name for t in info.function_tools})
            return step

        return seen


def test_projects_tool_hides_confidential():
    seen = Seen()
    with TestClient(app_for(call("projects"), seen.answer())) as client:
        open_one = new_project(client, "مدرسة - عينة")
        secret = new_project(client, "برج سري - عينة", confidential=True)
        listed = {p["id"]: p for p in client.get("/projects", headers=AUTH).json()["projects"]}
        assert listed[secret]["confidential"] is True and listed[open_one]["confidential"] is False
        assert ask(client, "إيه المشاريع؟ - عينة").status_code == 200
    [answer] = seen.answers
    assert json.loads(answer) == [{"id": open_one, "name": "مدرسة - عينة"}]
    assert "برج سري" not in answer


def test_hand_off_names_the_project():
    holder: dict = {}

    def hand(messages, info):
        return call("hand_to_project", {"project_id": holder["pid"], "request": "سعّر - عينة"})

    with TestClient(app_for(hand, said("حوّلتها - عينة"))) as client:
        holder["pid"] = pid = new_project(client, "مدرسة - عينة")
        found = chunks(ask(client, "سعّر المدرسة - عينة").text)
        messages = client.get(f"/chat/{GENERAL}/messages", headers=AUTH).json()["messages"]
    [card] = [c for c in found if c["type"] == "data-hand-off"]
    expected = {"kind": "project", "project_id": pid, "name": "مدرسة - عينة"}
    assert card["data"] == expected | {"request": "سعّر - عينة"}
    stored = [p for p in messages[1]["parts"] if p["type"] == "data-hand-off"]
    assert stored == [{"type": "data-hand-off", "id": card["id"], "data": card["data"]}]


def test_hand_off_moves_nothing_by_itself():
    holder: dict = {}

    def hand(messages, info):
        return call("hand_to_project", {"project_id": holder["pid"], "request": "سعّر - عينة"})

    with TestClient(app_for(hand, said("حوّلتها - عينة"))) as client:
        holder["pid"] = pid = new_project(client, "مدرسة - عينة")
        ask(client, "سعّر المدرسة - عينة")
        assert client.get(f"/chat/{pid}/messages", headers=AUTH).json() == {"messages": []}


def test_hand_off_to_confidential_is_refused_in_plain_words():
    holder: dict = {}
    seen = Seen()

    def hand(messages, info):
        return call("hand_to_project", {"project_id": holder["pid"], "request": "سعّر - عينة"})

    with TestClient(app_for(hand, seen.answer())) as client:
        holder["pid"] = new_project(client, "برج سري - عينة", confidential=True)
        found = chunks(ask(client, "سعّر البرج - عينة").text)
    assert copy.PROJECT_IS_CONFIDENTIAL["en"] in seen.answers[0]
    assert "برج سري" not in seen.answers[0]
    assert not [c for c in found if c["type"] == "data-hand-off"]


def test_hand_off_to_an_unknown_project_is_refused():
    seen = Seen()
    hand = call("hand_to_project", {"project_id": "0" * 32, "request": "سعّر - عينة"})
    with TestClient(app_for(hand, seen.answer())) as client:
        ask(client, "سعّر - عينة")
    assert copy.PROJECT_NOT_FOUND["en"] in seen.answers[0]


def test_offer_a_new_project():
    offer = call("offer_new_project", {"name": "فيلا التجمع - عينة", "request": "احصر - عينة"})
    with TestClient(app_for(offer, said("ممكن نعمله - عينة"))) as client:
        found = chunks(ask(client, "احصر الفيلا - عينة").text)
        assert client.get("/projects", headers=AUTH).json() == {"projects": []}  # not created
    [card] = [c for c in found if c["type"] == "data-hand-off"]
    assert card["data"] == {
        "kind": "new_project",
        "name": "فيلا التجمع - عينة",
        "request": "احصر - عينة",
    }


def test_general_chat_has_no_project_tools():
    seen = Seen()
    every_group = call(tool_groups.OPEN, {"open": list(tool_groups.GROUPS)})
    with TestClient(
        app_for(seen.tools_then(every_group), seen.tools_then(said("أهلاً - عينة")))
    ) as client:
        ask(client, "أهلاً - عينة")
    first, tools = seen.tools  # before and after the Lead opened every group of its tools
    assert first - {tool_groups.OPEN} < tools  # nothing left to open: open_tools goes
    assert set(general.GENERAL_TOOLS) == {"projects", "hand_to_project", "offer_new_project"}
    assert set(general.GENERAL_TOOLS) <= first
    assert not tools & {*RECORDS_TOOLS, *OUTPUTS_TOOLS, "note_lesson"}
    assert set(TEAM_TOOLS) <= tools  # Plans 4 and 5: specialists work for the General chat too
    assert {"web_search", "web_read"} <= first  # market news and prices: the Lead searches itself


def test_a_project_chat_has_no_general_tools():
    seen = Seen()
    with TestClient(app_for(seen.tools_then(said("أهلاً - عينة")))) as client:
        pid = new_project(client, "مدرسة - عينة")
        client.post("/chat", json=ui_message("أهلاً - عينة") | {"id": pid}, headers=AUTH)
    [tools] = seen.tools
    assert "search_records" in tools and not tools & set(general.GENERAL_TOOLS)


def test_a_closed_confidential_project_stays_hidden():
    seen = Seen()
    with TestClient(app_for(call("projects"), seen.answer())) as client:
        secret = new_project(client, "برج سري - عينة", confidential=True)
        client.post(f"/projects/{secret}/close", headers=AUTH)
        ask(client, "إيه المشاريع؟ - عينة")
    assert json.loads(seen.answers[0]) == []
