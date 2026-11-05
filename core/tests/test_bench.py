"""The test bench's fake AI drives the real engine end to end: every scenario runs its tools and
cards and ends, so the browser walks (ui/bench) have something real to walk."""

import json
import threading

import httpx
import pytest

from qsone import copy
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


def test_the_lead_shows_a_view_of_sourced_numbers(bench):
    """bench:view: the first imported item's numbers as a view (decision 16.1), each one a
    reference resolved to its value and source, and the same view after a reload."""
    client, project = bench
    _, reply, events = run(client, project, "bench:view اعرض أول بند")
    assert "رفضت" not in reply
    [view] = [e for e in events if e["type"] == "data-view"]
    data = view["data"]
    assert [b["kind"] for b in data["blocks"]] == ["heading", "figures", "table", "group"]
    figures = [i["value"] for i in data["blocks"][1]["items"]]
    assert figures and all(f["number_id"] and f["source"] in data["sources"] for f in figures)
    assert data["sample"] is True and data["unsourced"] == []
    messages = client.get(f"/chat/{project}/messages").json()["messages"]
    stored = [p for p in messages[-1]["parts"] if p["type"] == "data-view"]
    assert stored == [{"type": "data-view", "id": view["id"], "data": data}]


def test_the_tender_folder_is_understood(bench, tmp_path):
    """The Brief a tender folder's import starts: the BOQ comes in, then the card, every fact with
    its place in a file and the count from the import."""
    client, _ = bench
    project = client.post("/projects", json={"name": samples.TENDER_NAME}).json()["id"]
    folder = samples.write_tender(tmp_path / "tender")
    for path in sorted(p for p in folder.rglob("*") if p.is_file()):
        inside = path.parent.relative_to(folder.parent).as_posix()  # files_list names the folder
        params = {"name": path.name, "folder": inside}
        client.post(f"/projects/{project}/files", params=params, content=path.read_bytes())
    kinds, reply, events = run(client, project, copy.UNDERSTAND_BRIEF["ar"])
    assert kinds == ["rows"] and "رفضت" not in reply
    assert any(e["type"] == "data-understood" for e in events)
    facts = client.get(f"/projects/{project}/facts").json()
    assert facts["facts"]["client"]["source"]["file_name"] == samples.BOQ_NAME
    assert facts["facts"]["items_count"]["value"] == "4"
    assert facts["facts"]["items_count"]["source"]["kind"] == "count"
    assert len(facts["files"]) == 4 and facts["approved"] is False  # the zip's file, the RAR too
    assert f"{samples.TENDER_NAME}/02 جداول" in {f["folder"] for f in facts["files"]}


def test_closing_proposes_a_lesson(bench):
    client, project = bench
    _, reply, _ = run(client, project, copy.LESSONS_BRIEF["en"])
    assert "Refused" not in reply
    [lesson] = client.get(f"/projects/{project}/closing").json()["lessons"]
    assert lesson["kind"] == "method" and lesson["carried"] is False


def test_the_sample_tender_folder(tmp_path):
    folder = samples.write_tender(tmp_path)
    names = sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file())
    assert names == sorted(
        [
            f"02 جداول/{samples.BOQ_NAME}",
            samples.SPEC_NAME,
            f"نسخة/{samples.SPEC_NAME}",
            "رسومات - عينة.zip",
            "رسومات - عينة.rar",
        ]
    )


def test_the_bench_checks_a_claude_key_itself(data_dir, monkeypatch):
    """The live key check of the first launch and AI settings, on the bench: never Anthropic."""
    from fastapi.testclient import TestClient

    from qsone.engine import connectors
    from qsone.journey import setup_state
    from tests.bench import __main__ as bench_main

    monkeypatch.setattr(connectors, "check", connectors.check)  # put back after the test
    monkeypatch.setattr("asyncio.sleep", _no_wait)
    bench_main.check_keys()
    setup_state.give_consent(setup_state.CONSENT_VERSION)
    app = create_app(SECRET, connectors=fake.connectors, data_dir=data_dir)
    bench_main.forget_claude_key(app)
    with TestClient(app) as client:

        def check(key: str):
            client.put(
                "/settings/ai-key", json={"provider": "anthropic", "value": key}, headers=AUTH
            )
            return client.post("/settings/ai/check", json={"via": "api_key"}, headers=AUTH)

        works = check(f"sk-ant{bench_main.BENCH_KEY}sample-not-a-real-key-000000000000")
        assert works.status_code == 200 and works.json() == {"ok": True}
        refused = check("sk-ant-sample-not-a-real-key-0000000000000000")
        assert refused.status_code == 409
        assert refused.json() == {"error": copy.KEY_REFUSED, "fix": "ai"}

        client.post("/bench/forget-claude-key", headers=AUTH)
        assert client.get("/settings/ai-key", headers=AUTH).json() == {"set": False}


async def _no_wait(_seconds: float) -> None:
    return None
