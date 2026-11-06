"""CLI subprocesses against isolated local cores. No provider calls."""

import json
import os
import subprocess
import sys
from pathlib import Path

import httpx
import pytest

CORE = Path(__file__).resolve().parents[1]


def cli(session, *args, ok=0):
    result = subprocess.run(
        [sys.executable, "-m", "qsone.cli", "--session", str(session), "--json", *map(str, args)],
        cwd=CORE,
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == ok, result.stdout + result.stderr
    return json.loads(result.stdout)


@pytest.fixture
def running(tmp_path):
    session = tmp_path / "cli" / "session.json"
    started = cli(session, "start")
    yield session, started
    if session.exists():
        cli(session, "stop")


def test_isolation(running, tmp_path):
    session, started = running
    saved = json.loads(session.read_text())
    assert started["mode"] == "scripted"
    assert saved["port"] not in (1440, 1442)
    assert Path(saved["data_dir"]).is_relative_to(Path("/tmp"))
    assert session.stat().st_mode & 0o777 == 0o600
    assert session.parent.stat().st_mode & 0o777 == 0o700
    for port in (1440, 1442):
        cli(tmp_path / "bad.json", "start", "--port", port, ok=1)
        cli(tmp_path / "bad.json", "attach", "--port", port, "--secret-file", "/missing", ok=1)
    from qsone.cli.session import default_data_dir

    for folder in (default_data_dir(), default_data_dir() / "nested"):
        cli(tmp_path / "bad.json", "start", "--data-dir", folder, ok=1)
    secret = tmp_path / "secret.txt"
    secret.write_text(saved["secret"])
    attached = tmp_path / "attached" / "session.json"
    cli(attached, "attach", "--port", saved["port"], "--secret-file", secret)
    cli(attached, "stop")
    with httpx.Client(trust_env=False) as client:
        assert client.get(
            f"http://127.0.0.1:{saved['port']}/health",
            headers={"Authorization": f"Bearer {saved['secret']}"},
        ).is_success
    cli(session, "stop")
    assert not session.exists()


@pytest.mark.parametrize("provider", ["anthropic", "google"])
def test_key_not_exposed(running, tmp_path, provider):
    session, started = running
    key = "sample-bench-ok-private-marker"
    file = tmp_path / "provider.txt"
    file.write_text(key)
    for json_flag in ([], ["--json"]):
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "qsone.cli",
                "--session",
                str(session),
                *json_flag,
                "setup",
                "ai",
                "--provider",
                provider,
                "--model",
                "sample-model",
                "--key-file",
                str(file),
            ],
            cwd=CORE,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == (0 if provider == "anthropic" else 1)
        assert key not in result.stdout + result.stderr
    saved = json.loads(session.read_text())
    for path in (
        session,
        Path(started["data_dir"]) / "core.log",
        Path(f"/proc/{saved['pid']}/cmdline"),
        Path(f"/proc/{saved['pid']}/environ"),
    ):
        assert key.encode() not in path.read_bytes()


def test_question_and_boq(running):
    session, started = running
    cli(session, "setup", "finish")
    p = cli(session, "project", "new", "Sample CLI project")["id"]
    assert cli(session, "project", "list")["projects"]
    cli(session, "project", "open", p)
    samples = list(Path(started["samples"]).glob("*.xlsx"))
    cli(session, "files", "add", p, samples[0])
    assert cli(session, "files", "list", p)["files"]
    cli(session, "files", "report", p)
    question = cli(session, "ask", p, "bench:question What do you need?")
    card = question["cards"][0]
    assert card["kind"] == "question"
    answers = []
    for q in card["payload"]["questions"]:
        answers.extend(["--answer", f"{q['id']}={(q.get('options') or ['Sample note'])[0]}"])
    done = cli(session, "card", "answer", card["id"], "sent", *answers)
    assert done["state"] == "done"
    boq = cli(session, "ask", p, "bench:boq")
    assert boq["cards"][0]["kind"] == "rows"
    done = cli(session, "card", "answer", boq["cards"][0]["id"], "keep")
    assert done["state"] == "done"
    shown = cli(session, "boq", "show", p)
    assert shown["client_boqs"][0]["items"] == 4
    assert shown["client_boqs"][0]["headings"] == 2
    assert cli(session, "costs")["tokens"]["month"]["input"] > 0


def test_walk(running, tmp_path):
    session, _ = running
    report = tmp_path / "report.json"
    result = cli(session, "walk", CORE / "tests/walks/bench.yaml", "--report", report)
    assert result["status"] == "PASS"
    assert json.loads(report.read_text()) == result
    failing = tmp_path / "fail.yaml"
    failing.write_text("name: failure\nscripted:\n  - check: {reply_contains: impossible}\n")
    assert cli(session, "walk", failing, ok=1)["status"] == "FAIL"
    cap = cli(session, "walk", CORE / "tests/walks/bench.yaml", "--max-usd", "0.001", ok=1)
    assert cap["status"] == "CAP"
    assert any(s["status"] == "NOT_RUN" for s in cap["steps"])


@pytest.mark.parametrize("name", ["lahun", "sgh", "brissa"])
def test_missing_walk(running, tmp_path, name):
    import yaml

    session, _ = running
    walk = yaml.safe_load((CORE / f"tests/walks/{name}.yaml").read_text())
    walk["needs"] = [str(tmp_path / "missing.xlsx")]
    path = tmp_path / "missing.yaml"
    path.write_text(yaml.safe_dump(walk))
    assert cli(session, "walk", path)["status"] == "SKIPPED"


def test_stop_refuses_changed_identity(running):
    session, _ = running
    original = session.read_text()
    saved = json.loads(original)
    saved["birth"] = "different-process"
    session.write_text(json.dumps(saved))
    try:
        assert "error" in cli(session, "stop", ok=1)
        assert session.exists()
        os.kill(saved["pid"], 0)
    finally:
        session.write_text(original)


def test_follow_idle_and_busy_controls(running):
    session, _ = running
    p = cli(session, "project", "new", "Sample controls")["id"]
    assert cli(session, "follow", p)["state"] == "idle"
    asked = cli(session, "ask", p, "bench:question What do you need?")
    busy = cli(session, "ask", p, "bench:chat Hello", ok=1)
    assert busy["detail"]["brief_id"] == asked["brief_id"]
    cli(session, "steer", asked["brief_id"], "Sample steering")
    assert cli(session, "stop", asked["brief_id"])["state"] == "stopped"
    assert session.exists()


def test_walk_explicit_card_step(running, tmp_path):
    session, _ = running
    file = tmp_path / "cards.yaml"
    file.write_text("""name: separate cards
scripted:
  - project: Sample separate cards
  - ask: 'bench:question What do you need?'
  - card:
      kind: question
      choice: sent
      answers: {q1: Ready-mix, q2: Sample note}
  - check: {reply_contains: 'bench reply'}
""")
    assert cli(session, "walk", file)["status"] == "PASS"


def test_real_launcher_is_not_bench():
    from qsone.cli.session import command

    argv = command("real", 12345, "/tmp/sample", "/tmp/sample/samples")
    assert argv[1].endswith("/scripts/realapp/realcore.py")
    assert "tests.bench" not in argv
    assert argv[-2:] == ["--data-dir", "/tmp/sample"]


def test_budget_unpriced_stops_and_keeps_baseline():
    from types import SimpleNamespace

    from qsone.cli.walk import Budget

    class Book:
        month = "10"
        unpriced = 2
        stopped = []

        def get(self, route):
            return {"month": self.month, "unpriced": {"month": self.unpriced}}

        def post(self, route):
            self.stopped.append(route)

    book = Book()
    budget = Budget(SimpleNamespace(client=book, saved={"mode": "real"}), "3")
    assert not budget("brief")
    book.month = "12.99"
    assert not budget("brief")
    book.unpriced = 3
    assert budget("brief")
    assert book.stopped == ["/briefs/brief/stop"]


def test_card_follow_recovers_if_already_finished(tmp_path):
    from qsone.cli.client import Client
    from qsone.cli.follow import follow

    saved = {"port": 12345, "secret": "sample", "cards": {}}

    def respond(request):
        if request.url.path.endswith("/stream"):
            return httpx.Response(204)
        if request.url.path.endswith("/messages"):
            return httpx.Response(
                200,
                json={
                    "messages": [
                        {
                            "role": "assistant",
                            "parts": [
                                {"type": "text", "text": "Sample completed reply"},
                                {"type": "data-status", "id": "brief", "data": {"state": "done"}},
                            ],
                        }
                    ]
                },
            )
        return httpx.Response(200, json={"brief": "0.1"})

    c = Client(saved)
    c.http.close()
    c.http = httpx.Client(base_url="http://localhost", transport=httpx.MockTransport(respond))
    try:
        result = follow(c, saved, tmp_path / "session.json", "project", recover=True)
        assert result["state"] == "done"
        assert result["reply"] == "Sample completed reply"
        assert result["costs"]["brief"] == "0.1"
    finally:
        c.close()


def test_files_search_deliverables_and_numbers(running, tmp_path):
    session, started = running
    p = cli(session, "project", "new", "Sample documents")["id"]
    cli(session, "files", "add", p, *Path(started["samples"]).iterdir())
    files = cli(session, "files", "list", p)["files"]
    spreadsheet = next(f for f in files if f["name"].endswith(".xlsx"))
    sheet = cli(session, "file", "show", p, spreadsheet["id"], "--sheet")
    assert sheet["rows"]
    assert "results" in cli(session, "search", p, "concrete", "--words")
    asked = cli(session, "ask", p, "bench:deliverable Make the priced BOQ")
    for _ in range(12):
        if not asked["cards"]:
            break
        card = asked["cards"][0]
        if card["kind"] == "rows":
            asked = cli(session, "card", "answer", card["id"], "keep")
        elif card["kind"] == "question":
            answers = []
            for q in card["payload"]["questions"]:
                answers += ["--answer", f"{q['id']}={(q.get('options') or ['Sample note'])[0]}"]
            asked = cli(session, "card", "answer", card["id"], "sent", *answers)
        else:
            asked = cli(session, "card", "approve", card["id"])
    assert asked["state"] == "done"
    entries = cli(session, "deliverable", "list", p)["deliverables"]
    sheet = next(d for d in entries if d["kind"] == "sheet")
    view = cli(session, "deliverable", "show", p, sheet["id"])
    number = next(
        cell["number_id"]
        for row in view["rows"]
        for cell in row["cells"].values()
        if "number_id" in cell
    )
    assert cli(session, "number", "explain", p, number)
    output = tmp_path / "sample.xlsx"
    cli(session, "deliverable", "export", p, sheet["id"], "--format", "xlsx", "--out", output)
    assert output.read_bytes().startswith(b"PK")
    # Accept reports stale IDs; reject refuses them, matching the core's different contracts.
    assert cli(session, "changes", "accept", p, sheet["id"], "--ids", "missing")["stale"] == [
        "missing"
    ]
    assert "error" in cli(session, "changes", "reject", p, sheet["id"], "--ids", "missing", ok=1)
    saved = json.loads(session.read_text())
    row = next(r for r in view["rows"] if "rate" in r["cells"])
    route = f"/projects/{p}/deliverables/{sheet['id']}/changes"
    with httpx.Client(
        base_url=f"http://127.0.0.1:{saved['port']}",
        trust_env=False,
        headers={"Authorization": f"Bearer {saved['secret']}"},
    ) as client:
        for action in ("accept", "reject"):
            proposed = client.post(
                route,
                json={
                    "ops": [
                        {"op": "set_number", "row": row["id"], "name": "rate", "value": "123.45"}
                    ]
                },
            )
            assert proposed.status_code == 201
            change = proposed.json()["changes"][0]["id"]
            changed = cli(session, "changes", action, p, sheet["id"])
            assert change in changed["accepted" if action == "accept" else "rejected"]
            assert cli(session, "undo", changed["undo"]) == {}
            if action == "accept":
                restored = cli(session, "deliverable", "show", p, sheet["id"])
                restored_row = next(r for r in restored["rows"] if r["id"] == row["id"])
                assert restored_row["cells"]["rate"]["value"] == row["cells"]["rate"]["value"]
            else:
                pending = client.get(route, params={"status": "pending"}).json()["changes"]
                assert change in [entry["id"] for entry in pending]
    assert "error" in cli(session, "undo", "missing", ok=1)


def test_native_model_selection(running, tmp_path):
    from qsone.cli.client import Client

    session, _ = running
    key = tmp_path / "native.txt"
    key.write_text("sample-bench-ok-value")
    cli(
        session,
        "setup",
        "ai",
        "--provider",
        "anthropic",
        "--model",
        "sample-model",
        "--key-file",
        key,
    )
    c = Client(json.loads(session.read_text()))
    try:
        assert c.get("/settings/model")["id"] == "sample-model"
    finally:
        c.close()


def test_cap_before_first_stream_event_stops_active_brief(tmp_path):
    from qsone.cli.client import Client
    from qsone.cli.follow import follow

    saved = {"port": 12345, "secret": "sample", "cards": {}}
    seen = []

    def respond(request):
        if request.url.path.endswith("/stream"):
            return httpx.Response(200, text="data: [DONE]\n\n")
        if request.url.path == "/briefs/activity":
            return httpx.Response(
                200,
                json={"chats": [{"chat_id": "project", "brief_id": "active", "state": "working"}]},
            )
        return httpx.Response(200, json={})

    def guard(brief):
        seen.append(brief)
        return True

    c = Client(saved)
    c.http.close()
    c.http = httpx.Client(base_url="http://localhost", transport=httpx.MockTransport(respond))
    try:
        assert follow(c, saved, tmp_path / "s.json", "project", guard=guard)["state"] == "money_cap"
        assert "active" in seen
    finally:
        c.close()


def test_invalid_cap_is_a_clean_error(running):
    session, _ = running
    assert "error" in cli(
        session, "walk", CORE / "tests/walks/bench.yaml", "--max-usd", "oops", ok=1
    )


def test_walk_quantity_and_citation_checks():
    from types import SimpleNamespace

    from qsone.cli.walk import Walk

    class Files:
        def get(self, route, **params):
            if route.endswith("/text"):
                return {"pieces": [{"text": "Sample value 350,000 USD"}]}
            return {
                "sheet": "Sample",
                "rows": [
                    {"code": "54", "cells": {"D": {"text": "5.00"}}},
                    {"code": "55", "cells": {"D": {"text": "6"}}},
                ],
            }

    walk = Walk(SimpleNamespace(client=Files()))
    walk.project, walk.files = "project", [{"id": "file"}]
    walk.last = {"reply": "Sample ٣٥٠٬٠٠٠ USD"}
    assert walk.check("cited", {"value": "350,000", "page": 26})
    assert not walk.check("cited", {"value": "350,000", "row": 54})
    assert walk.check("no_raw", True)
    walk.last = {"reply": "sample " + "a" * 32}
    assert not walk.check("no_raw", True)
    walk.boq = {
        "sheets": [
            {
                "file_id": "file",
                "rows": [
                    {"cells": {"quantity": {"value": "5", "source": "s54"}}},
                    {"cells": {"quantity": {"value": "6", "source": "s55"}}},
                ],
                "sources": {
                    "s54": {"locator": {"row": 54, "column": "D", "sheet": "Sample"}},
                    "s55": {"locator": {"row": 55, "column": "D", "sheet": "Sample"}},
                },
            }
        ]
    }
    check = {"first": 54, "last": 55, "column": "D"}
    assert walk.check("quantity_rows", check)
    walk.boq["sheets"][0]["rows"][1]["cells"] = {}
    assert not walk.check("quantity_rows", check)


def test_budget_fails_closed_if_costs_unavailable():
    from types import SimpleNamespace

    from qsone.cli.walk import Budget

    class Book:
        broken = False
        stopped = []

        def get(self, route):
            if self.broken:
                raise httpx.ReadTimeout("sample timeout")
            return {"month": "0", "unpriced": {"month": 0}}

        def post(self, route):
            self.stopped.append(route)

    book = Book()
    budget = Budget(SimpleNamespace(client=book, saved={"mode": "real"}), 3)
    book.broken = True
    assert budget("brief")
    assert book.stopped == ["/briefs/brief/stop"]
