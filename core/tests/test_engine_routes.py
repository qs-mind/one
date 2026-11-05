"""The Brief Runner's HTTP routes (Plan 4, Task 8), as the screen (Task 9) uses them.

Scripted models behind fake connectors, and the fake `claude`; no test calls a real AI.
Synthetic «عينة» data only."""

import asyncio
import json
import threading
from uuid import UUID

import httpx
import pytest
from fastapi.testclient import TestClient

from qsone import copy
from qsone.app import create_app
from qsone.engine import costs, roles, team
from qsone.engine.connectors.claude_code import ID as CLAUDE_CODE
from qsone.engine.connectors.claude_code import ClaudeCodeConnector
from qsone.engine.runner import WORK
from qsone.engine.types import ModelChoice
from tests.conftest import AUTH, SECRET, ui_message
from tests.engine_fakes import FakeSleep, call, fake_claude_command, read_fake_log, scripted
from tests.engine_fakes import text as said
from tests.test_engine_runner import PLAN, TAKE_OFF, links

GENERAL = "general"


def message(text: str, chat_id: str = GENERAL) -> dict:
    return ui_message(text) | {"id": chat_id}


def chunks(body: str) -> list[dict]:
    return [json.loads(line[6:]) for line in body.splitlines() if line.startswith("data: {")]


def states(found: list[dict]) -> list[str]:
    return [c["data"]["state"] for c in found if c["type"] == "data-status"]


@pytest.fixture(autouse=True)
def no_budget_card():
    costs.save_caps({"budget_above": "100"})


def app_with(found):
    return create_app(SECRET, connectors=lambda: found, sleep=FakeSleep())


class Waits:
    """A model step that waits until the test releases it (from the test's own thread)."""

    def __init__(self, answer="تم - عينة") -> None:
        self.release = threading.Event()
        self.answer = answer

    async def __call__(self, messages, info):
        while not self.release.is_set():
            await asyncio.sleep(0.01)
        return self.answer


def read_until(lines, kind: str) -> list[dict]:
    seen = []
    for line in lines:
        if line.startswith("data: {"):
            seen.append(json.loads(line[6:]))
            if seen[-1]["type"] == kind:
                return seen
    raise AssertionError(f"no {kind} in {seen}")


# The chat --------------------------------------------------------------------------------------


def test_chat_streams_and_ends_with_done():
    with TestClient(app_with(links(lead=scripted(said("تم - عينة"))))) as client:
        r = client.post("/chat", json=message("سعّر - عينة"), headers=AUTH)
        assert r.status_code == 200
        assert r.headers["x-vercel-ai-ui-message-stream"] == "v1"
        found = chunks(r.text)
        [start] = [c for c in found if c["type"] == "start"]
        [status] = {c["id"] for c in found if c["type"] == "data-status"}
        assert start["messageId"] == f"{status}-reply"  # the stored reply's id
        assert states(found)[-1] == "done" and r.text.rstrip().endswith("data: [DONE]")
        assert "".join(c["delta"] for c in found if c["type"] == "text-delta") == "تم - عينة"
        assert client.get(f"/chat/{GENERAL}/stream", headers=AUTH).status_code == 204


def test_chat_needs_a_message_and_a_known_chat():
    with TestClient(app_with(links(lead=scripted()))) as client:
        empty = ui_message("   ") | {"id": GENERAL}
        assert client.post("/chat", json=empty, headers=AUTH).json() == {"error": copy.CHAT_EMPTY}
        r = client.post("/chat", json=message("عينة", "f" * 32), headers=AUTH)
        assert r.status_code == 404 and r.json() == {"error": copy.PROJECT_NOT_FOUND}


def test_chat_messages_rebuild_the_conversation():
    lead = scripted(said("الأول - عينة"), said("النقل 7,500 جنيه - عينة"))
    with TestClient(app_with(links(lead=lead))) as client:
        client.post("/chat", json=message("سؤال أول - عينة"), headers=AUTH)
        client.post("/chat", json=message("سؤال تاني - عينة"), headers=AUTH)
        found = client.get(f"/chat/{GENERAL}/messages", headers=AUTH).json()["messages"]
    assert [m["role"] for m in found] == ["user", "assistant", "user", "assistant"]
    assert found[0]["parts"] == [{"type": "text", "text": "سؤال أول - عينة"}]
    reply = found[3]
    assert reply["id"].endswith("-reply")
    assert reply["parts"][0] == {"type": "text", "text": "النقل 7,500 جنيه - عينة", "state": "done"}
    kinds = {p["type"]: p for p in reply["parts"]}
    assert kinds["data-unsourced"]["data"] == {"values": ["7,500"]}
    assert kinds["data-status"]["data"]["state"] == "done"


def test_every_route_needs_the_secret():
    with TestClient(app_with(links(lead=scripted()))) as client:
        for method, path in (
            ("POST", "/chat"),
            ("GET", f"/chat/{GENERAL}/stream"),
            ("GET", f"/chat/{GENERAL}/messages"),
            ("POST", "/briefs/b1/stop"),
            ("POST", "/briefs/b1/steer"),
            ("GET", "/briefs/unfinished"),
            ("POST", "/briefs/b1/continue"),
            ("POST", "/cards/c1"),
            ("GET", f"/projects/{GENERAL}/team"),
            ("GET", f"/projects/{GENERAL}/activity"),
        ):
            assert client.request(method, path).status_code == 401, path


def test_briefs_routes_when_nothing_runs():
    with TestClient(app_with(links(lead=scripted()))) as client:
        assert client.get("/briefs/unfinished", headers=AUTH).json() == {"briefs": []}
        r = client.post("/briefs/nope/continue", headers=AUTH)
        assert r.status_code == 404 and r.json() == {"error": copy.BRIEF_NOT_FOUND}
        r = client.post("/briefs/nope/stop", headers=AUTH)
        assert r.status_code == 409 and r.json() == {"error": copy.BRIEF_NOT_RUNNING}
        r = client.post("/briefs/nope/steer", json={"text": "عينة"}, headers=AUTH)
        assert r.status_code == 409
        r = client.post("/cards/nope", json={"choice": "yes"}, headers=AUTH)
        assert r.status_code == 404 and r.json() == {"error": copy.CARD_GONE}
        assert client.get(f"/projects/{GENERAL}/team", headers=AUTH).json()["agents"] == []


# While a Brief runs (a real server, so streams and requests overlap) ----------------------------


def test_second_message_while_busy_gets_409_with_the_brief(serve_app):
    waits = Waits()
    lead = scripted(waits, said("وصلت رسالتك - عينة"))
    url = serve_app(app_with(links(lead=lead)))
    with httpx.Client(timeout=10, headers=AUTH) as client:
        with client.stream("POST", f"{url}/chat", json=message("أول - عينة")) as r:
            lines = r.iter_lines()
            brief = read_until(lines, "data-status")[-1]["id"]
            busy = client.post(f"{url}/chat", json=message("تاني - عينة"))
            assert busy.status_code == 409 and busy.json() == {"brief_id": brief}
            steer = client.post(f"{url}/briefs/{brief}/steer", json={"text": "ركّز - عينة"})
            assert steer.status_code == 202
            waits.release.set()
            rest = read_until(lines, "finish")
        assert states(rest)[-1] == "done"
    assert "ركّز - عينة" in str(lead.seen[-1])


def test_dropped_stream_keeps_the_brief_and_reattaches(serve_app):
    waits = Waits("رد كامل - عينة")
    url = serve_app(
        app_with(links(lead=scripted(call("search_records", {"query": "خرسانة"}), waits)))
    )
    with httpx.Client(timeout=10, headers=AUTH) as client:
        with client.stream("POST", f"{url}/chat", json=message("سؤال - عينة")) as r:
            first = read_until(r.iter_lines(), "data-progress")
        start = first[0]
        waits.release.set()
        with client.stream("GET", f"{url}/chat/{GENERAL}/stream") as again:
            assert again.status_code == 200
            replay = read_until(again.iter_lines(), "finish")
    assert replay[0] == start  # the same reply message, replayed from its start
    assert [c for c in replay if c["type"] == "data-progress"] == [first[-1]]
    assert "".join(c["delta"] for c in replay if c["type"] == "text-delta") == "رد كامل - عينة"
    assert states(replay)[-1] == "done"


def test_cards_route_checks_the_choice(serve_app):
    costs.save_caps({"budget_above": "0"})  # plan_brief asks for the budget
    lead = scripted(call("plan_brief", PLAN), said("الخطة جاهزة - عينة"))
    url = serve_app(app_with(links(lead=lead)))
    with httpx.Client(timeout=10, headers=AUTH) as client:
        with client.stream("POST", f"{url}/chat", json=message("خطة - عينة")) as r:
            lines = r.iter_lines()
            card = read_until(lines, "data-card")[-1]
            assert card["data"]["status"] == "pending" and card["data"]["kind"] == "budget"
            bad = client.post(f"{url}/cards/{card['id']}", json={"choice": "maybe"})
            assert bad.status_code == 422
            assert bad.json() == {"error": copy.CARD_CHOICE, "options": ["yes", "no"]}
            ok = client.post(f"{url}/cards/{card['id']}", json={"choice": "yes"})
            assert ok.status_code == 204
            rest = read_until(lines, "finish")
        settled = [c for c in rest if c["type"] == "data-card" and c["id"] == card["id"]]
        assert settled[-1]["data"] | {} == card["data"] | {"status": "settled", "choice": "yes"}
        assert states(rest)[-1] == "done"
        gone = client.post(f"{url}/cards/{card['id']}", json={"choice": "yes"})
        assert gone.status_code == 404


def test_team_and_activity_routes(serve_app):
    waits = Waits()
    url = serve_app(app_with(links(lead=scripted(waits))))
    got: list[dict] = []
    with httpx.Client(timeout=10, headers=AUTH) as client:
        with client.stream("GET", f"{url}/projects/{GENERAL}/activity") as activity:
            assert activity.status_code == 200

            def start():
                with httpx.Client(timeout=10, headers=AUTH) as other:
                    other.post(f"{url}/chat", json=message("سؤال - عينة"))

            threading.Thread(target=start, daemon=True).start()
            lines = activity.iter_lines()
            for line in lines:
                if line.startswith("data: "):
                    got.append(json.loads(line[6:]))
                    if got[-1]["type"] == "agent":
                        break
            team_now = client.get(f"{url}/projects/{GENERAL}/team").json()
            waits.release.set()
            for line in lines:
                if line.startswith("data: "):
                    got.append(json.loads(line[6:]))
                    if got[-1]["type"] == "agent-gone":
                        break
    [agent] = team_now["agents"]
    assert agent["role"] == copy.ROLE_LEAD and agent["state"] in ("thinking", "working")
    assert agent["kind"] == "lead" and got[0]["agent"]["kind"] == "lead"
    assert got[0]["agent"]["id"] == agent["id"] and got[-1] == {
        "type": "agent-gone",
        "id": agent["id"],
    }


# The Subscription Link -------------------------------------------------------------------------


def test_lead_on_the_subscription_link_end_to_end(serve_app, data_dir, tmp_path, monkeypatch):
    made = iter(range(1, 1000))
    monkeypatch.setattr(team, "uuid4", lambda: UUID(int=next(made)))
    specialist_id = UUID(int=1).hex  # the first id the team tools make
    one_step = {"steps": [{"specialist": "Take-off QS", "task": "Quantities", "requests": 2}]}
    script = [
        "init",
        {"mcp_call": {"tool": "plan_brief", "args": one_step}},
        {"mcp_call": {"tool": "build_specialist", "args": TAKE_OFF}},
        {"mcp_call": {"tool": "delegate", "args": {"specialist_id": specialist_id, "task": "حصر"}}},
        {"text": "الحصر خلص - عينة", "usage": [100, 20]},
        "result",
    ]
    log = tmp_path / "claude.log"
    claude = ClaudeCodeConnector(None, command_prefix=fake_claude_command(script=script, log=log))
    specialist = scripted(said("120 م3 - عينة"))
    found = [*links(specialist=specialist, only_anthropic=True), claude]
    roles.choose("lead", ModelChoice(CLAUDE_CODE, "sonnet"))
    url = serve_app(app_with(found))
    with httpx.Client(timeout=30, headers=AUTH) as client:
        r = client.post(f"{url}/chat", json=message("احصر - عينة"))
    got = chunks(r.text)
    assert states(got)[-1] == "done", got
    assert "".join(c["delta"] for c in got if c["type"] == "text-delta").endswith(
        "الحصر خلص - عينة"
    )
    assert specialist.calls == 1 and "حصر" in str(specialist.seen[0])
    [run] = read_fake_log(log)
    assert run["ended"] == "done"
    assert not (data_dir / WORK).exists() or not any((data_dir / WORK).iterdir())


# A quiet Brief keeps its stream alive (founder's run, 5 Nov: a card never reached the window) ----


async def test_a_quiet_brief_stream_sends_heartbeats_and_still_every_part(monkeypatch):
    from qsone.engine import stream as ui
    from qsone.engine.types import Asked, Card, Progress

    monkeypatch.setattr(ui, "HEARTBEAT_S", 0.01)
    words = {"en": "Import?", "ar": "أستورد؟"}
    card = Card("c1", "rows", words, words, ("keep", "no"))

    async def events():
        yield Progress("b1", "r1", copy.ROLE_LEAD, {"en": "Look", "ar": "يبص"})
        await asyncio.sleep(0.05)  # a long quiet step
        yield Asked("b1", card)

    lines = [line async for line in ui.ui_stream(events(), message_id="a1")]
    assert ui.HEARTBEAT in lines
    kinds = [json.loads(line[6:])["type"] for line in lines if line.startswith("data: {")]
    assert kinds.index("data-progress") < kinds.index("data-card")
    assert lines[-1] == "data: [DONE]\n\n"
