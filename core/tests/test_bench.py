"""The test bench's fake AI drives the real engine end to end: every scenario runs its tools and
cards and ends, so the browser walks (ui/bench) have something real to walk."""

import json
import threading

import httpx
import pytest

from qsone.app import create_app
from qsone.engine import roles
from tests.bench import fake, samples
from tests.conftest import AUTH, SECRET


@pytest.fixture
def bench(data_dir, serve_app, tmp_path):
    for role, choice in fake.ROLES.items():
        roles.choose(role, choice)
    url = serve_app(create_app(SECRET, connectors=fake.connectors, data_dir=data_dir))
    with httpx.Client(base_url=url, headers=AUTH, timeout=60) as client:
        project = client.post("/projects", json={"name": "مشروع - عينة الاختبار"}).json()["id"]
        for path in samples.write(tmp_path / "samples"):
            client.post(
                f"/projects/{project}/files", params={"name": path.name}, content=path.read_bytes()
            )
        yield client, project


def _answer(client: httpx.Client, card_id: str, card: dict) -> None:
    payload = card.get("payload") or {}
    if card["kind"] == "rows":
        body = {"choice": "keep", "rows_ok": list(range(len(payload["rows"])))}
    elif card["kind"] == "question":
        answers = {
            q["id"]: (q.get("options") or ["إجابة تجريبية"])[0] for q in payload["questions"]
        }
        body = {"choice": card["options"][0], "answers": answers}
    else:
        body = {"choice": "yes"}
    assert client.post(f"/cards/{card_id}", json=body).status_code == 204


def run(client: httpx.Client, chat: str, text: str) -> tuple[list[str], str, list[dict]]:
    """Sends a Brief and answers each card; gives the card kinds, the reply text and the events."""
    body = {
        "trigger": "submit-message",
        "id": chat,
        "messages": [{"id": "m-1", "role": "user", "parts": [{"type": "text", "text": text}]}],
    }
    kinds, reply, events, answering = [], [], [], []
    with client.stream("POST", "/chat", json=body) as response:
        for line in response.iter_lines():
            if not line.startswith("data: ") or line == "data: [DONE]":
                continue
            event = json.loads(line[6:])
            events.append(event)
            if event["type"] == "text-delta":
                reply.append(event["delta"])
            elif event["type"] == "data-card" and event["data"].get("status") == "pending":
                kinds.append(event["data"]["kind"])
                worker = threading.Thread(target=_answer, args=(client, event["id"], event["data"]))
                worker.start()
                answering.append(worker)
    for worker in answering:
        worker.join()
    return kinds, "".join(reply), events


def test_the_full_walk_through(bench):
    client, project = bench
    kinds, reply, events = run(client, project, "سعّر جدول الكميات المرفق")
    assert kinds == ["rows", "question", "budget", "rows"]
    assert "رد تجريبي" in reply and "رفضت" not in reply  # no tool refused a step
    reviews = [e["data"] for e in events if e["type"] == "data-review"]
    assert [r["code"] for r in reviews] == ["A"] and reviews[0]["same_provider"] is False
    status = [e["data"]["state"] for e in events if e["type"] == "data-status"]
    assert status[-1] == "done"
    made = client.get(f"/projects/{project}/deliverables").json()["deliverables"]
    assert sorted(d["kind"] for d in made) == ["document", "sheet"]


@pytest.mark.parametrize(
    ("text", "cards"),
    [
        ("bench:chat Hello", []),
        ("bench:question What do you need?", ["question"]),
        ("bench:boq استورد المقايسة", ["rows"]),
        ("bench:team Price it", ["budget", "rows"]),
    ],
)
def test_each_scenario_ends(bench, text, cards):
    client, project = bench
    kinds, reply, _ = run(client, project, text)
    assert kinds == cards
    assert ("bench reply" in reply) or ("رد تجريبي" in reply)
    assert "Refused" not in reply and "رفضت" not in reply


def test_the_general_chat(bench):
    client, _ = bench
    kinds, reply, _ = run(client, "general", "bench:chat أهلا")
    assert kinds == [] and "رد تجريبي" in reply


def test_the_imported_boq_is_on_the_canvas(bench):
    client, project = bench
    run(client, project, "bench:boq Import the BOQ")
    [boq] = client.get(f"/projects/{project}/canvas").json()["client_boqs"]
    assert boq["name"] == samples.BOQ_NAME and boq["items"] == 4 and boq["headings"] == 2
    rows = client.get(f"/projects/{project}/client-boq/{boq['file_id']}").json()["rows"]
    assert [r["kind"] for r in rows] == ["section", "item", "item", "section", "item", "item"]


def test_the_extra_priced_row_is_flagged_for_the_engineer(bench):
    client, project = bench
    _, reply, events = run(client, project, "bench:deliverable Make the priced BOQ")
    assert "Refused" not in reply
    assert [e["data"]["code"] for e in events if e["type"] == "data-review"] == ["B"]
    made = client.get(f"/projects/{project}/deliverables").json()["deliverables"]
    sheet = next(d for d in made if d["kind"] == "sheet")
    threads = client.get(f"/projects/{project}/deliverables/{sheet['id']}/comments").json()
    flags = [t for t in threads["comments"] if t["anchor"]["type"] == "row"]
    assert [t["body"].split(":")[0] for t in flags] == ["Not in the client's BOQ"]
    assert fake.EXTRA_CODE in flags[0]["body"] and flags[0]["status"] == "open"
