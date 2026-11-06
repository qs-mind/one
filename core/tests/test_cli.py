"""CLI subprocesses against isolated local cores. No provider calls."""

import json
import os
import subprocess
import sys
from pathlib import Path

import httpx
import pytest

CORE = Path(__file__).resolve().parents[1]


def cli(session, *args, ok=0, timeout=90):
    result = subprocess.run(
        [sys.executable, "-m", "qsone.cli", "--session", str(session), "--json", *map(str, args)],
        cwd=CORE,
        capture_output=True,
        text=True,
        timeout=timeout,
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
    # A draft exports too, marked «مسودة — غير معتمد» (DRAFT_EXPORTS); Sign-off makes it a revision.
    cli(session, "deliverable", "export", p, sheet["id"], "--format", "xlsx", "--out", output)
    assert output.read_bytes().startswith(b"PK")
    output.unlink()
    assert cli(session, "deliverable", "check", p, sheet["id"])["checked"]
    cli(session, "deliverable", "signoff", p, sheet["id"])
    assert "changes" in cli(session, "changes", "list", p, sheet["id"])
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
    walk.last = {"reply": "Sample ٣٥٠٬٠٠٠ USD, page 26"}
    walk.prepare_check("cited", {"value": "350,000", "page": 26})
    assert walk.check("cited", {"value": "350,000", "page": 26})
    walk.prepare_check("cited", {"value": "350,000", "row": 54})
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
    walk.prepare_check("quantity_rows", check)
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
    from qsone.cli.texts import CliError

    with pytest.raises(CliError):
        budget("brief")
    assert not budget.hit
    assert book.stopped == ["/briefs/brief/stop"]


@pytest.mark.parametrize(
    "argv,method,route,body",
    [
        (
            ["compare", "p", "old", "new"],
            "POST",
            "/projects/p/files/compare",
            {"old_file_id": "old", "new_file_id": "new"},
        ),
        (["region", "list", "p", "f"], "GET", "/projects/p/files/f/comments", None),
        (
            ["region", "add", "p", "f", "--page", "2", "--box", "0,0,10,20", "Sample comment"],
            "POST",
            "/projects/p/files/f/comments",
            {
                "anchor": {"kind": "file_region", "file_id": "f", "page": 2, "box": [0, 0, 10, 20]},
                "body": "Sample comment",
            },
        ),
        (["deliverable", "signoff", "p", "d"], "POST", "/projects/p/deliverables/d/signoff", None),
        (["changes", "list", "p", "d"], "GET", "/projects/p/deliverables/d/changes", None),
        (["pack", "show", "p", "d"], "GET", "/projects/p/deliverables/d", None),
        (["costs", "--today"], "GET", "/costs", None),
    ],
)
def test_new_route_commands(argv, method, route, body):
    from qsone.cli.__main__ import parser
    from qsone.cli.client import Client
    from qsone.cli.commands import Commands

    seen = []

    def respond(request):
        seen.append(request)
        return httpx.Response(200, json={})

    c = Client({"port": 12345, "secret": "sample"})
    c.http.close()
    c.http = httpx.Client(base_url="http://localhost", transport=httpx.MockTransport(respond))
    try:
        Commands(c, {}, None).run(parser().parse_args(argv))
        request = seen[0]
        assert (request.method, request.url.path) == (method, route)
        if body is not None:
            assert json.loads(request.content) == body
    finally:
        c.close()


@pytest.mark.parametrize(
    "name,expected,reply,passed",
    [
        ("reply_not_contains", ["secret"], "sample", True),
        ("reply_numbers", [14000, 200], "١٤٬٠٠٠ and 200.00", True),
        ("reply_numbers", [200], "1200", False),
        ("no_promise", True, "I will prepare the document.", False),
        ("no_promise", True, "Sample work completed.", True),
    ],
)
def test_added_reply_checks(name, expected, reply, passed):
    from types import SimpleNamespace

    from qsone.cli.walk import Walk

    walk = Walk(SimpleNamespace(client=None))
    walk.last = {"reply": reply}
    assert walk.check(name, expected) is passed


@pytest.mark.parametrize(
    "name,expected,data,passed",
    [
        (
            "deliverable",
            {"kind": "sheet", "variant": "boq", "title_contains": "sample"},
            {"kind": "sheet", "variant": "boq", "title": "Sample BOQ", "rows": [{"kind": "item"}]},
            True,
        ),
        ("deliverable", {"kind": "document"}, {"kind": "document", "blocks": []}, False),
        (
            "deliverable_numbers",
            [12],
            {
                "rows": [{"cells": {"rate": {"value": "12", "source": "s"}}}],
                "sources": {"s": {"file_id": "f", "locator": {"page": 2}}},
            },
            True,
        ),
        (
            "deliverable_numbers",
            [12],
            {"rows": [{"cells": {"rate": {"value": "12", "source": "missing"}}}]},
            False,
        ),
        (
            "boq_total",
            12,
            {"total": {"value": "12.00", "source": "s"}, "sources": {"s": {"kind": "calculation"}}},
            True,
        ),
    ],
)
def test_deliverable_checks(name, expected, data, passed):
    from types import SimpleNamespace

    from qsone.cli.walk import Walk

    walk = Walk(SimpleNamespace(client=None))
    walk.deliverable = data
    assert walk.check(name, expected) is passed


@pytest.mark.parametrize(
    "name,expected,observed,passed",
    [
        ("changes_count", 2, {"changes": [{}, {}]}, True),
        ("pack_pages", 3, {"pages": 3}, True),
        ("compare_pages", [2], {"changed": [{"new": {"page": 2}}]}, True),
        ("compare_pages", [2], {"changed": [{"new": {"page": 1}}]}, False),
        ("export_ok", {"pages": 2}, {"out": "sample.pdf", "bytes": 20, "pages": 2}, True),
        ("export_ok", True, {"out": "empty.pdf", "bytes": 0}, False),
    ],
)
def test_observed_checks(name, expected, observed, passed):
    from types import SimpleNamespace

    from qsone.cli.walk import Walk

    walk = Walk(SimpleNamespace(client=None))
    walk.observed = observed
    assert walk.check(name, expected) is passed


def test_usage_checks_do_not_fetch():
    from types import SimpleNamespace

    from qsone.cli.walk import Walk

    walk = Walk(SimpleNamespace(client=None))
    walk.last = {
        "events": [{"type": "data-worklog", "data": {"steps": [{}, {}]}}],
        "costs": {"brief": "0.01", "tokens": {"brief": {"input": 250}}},
    }
    assert walk.check("max_steps", 2)
    assert not walk.check("max_steps", 1)
    assert walk.check("max_input_tokens", 250)
    assert not walk.check("max_input_tokens", 249)
    assert walk.check("max_usd", ".02")


def test_walk_all_order_cap_and_scripted_only(tmp_path):
    from types import SimpleNamespace

    from qsone.cli.texts import CliError
    from qsone.cli.walk import run_all

    class Book:
        def get(self, route, **params):
            return {"month": "0", "unpriced": {"month": 0}}

    commands = SimpleNamespace(client=Book(), saved={"mode": "scripted"}, guard=None, lang="en")
    for name in ("b", "a"):
        (tmp_path / f"{name}.yaml").write_text(
            "max_usd: 0.1\nscripted:\n- check: {reply_not_contains: impossible}\n"
        )
    report = tmp_path / "report.json"
    result = run_all(commands, tmp_path, report=report, scripted_only=True)
    assert result["status"] == "PASS"
    assert [r["name"] for r in result["walks"]] == ["a", "b"]
    assert result["max_usd"] == "0.2"
    assert json.loads(report.read_text()) == result
    assert report.with_suffix(".txt").read_text()
    result = run_all(commands, tmp_path, max_usd=0)
    assert result["status"] == "CAP"
    assert all(r["status"] == "NOT_RUN" for r in result["walks"])
    commands.saved["mode"] = "real"
    with pytest.raises(CliError):
        run_all(commands, tmp_path, scripted_only=True)


def test_cited_requires_reply_location():
    from types import SimpleNamespace

    from qsone.cli.walk import Walk

    walk = Walk(SimpleNamespace(client=None))
    walk.evidence["cited"] = {"pieces": [{"text": "350,000 USD"}]}
    for reply, expected in [
        ("350,000 USD", False),
        ("350,000 USD, page 25", False),
        ("350,000 USD, page 26", True),
    ]:
        walk.last = {"reply": reply}
        assert walk.check("cited", {"value": "350,000", "page": 26}) is expected


def test_make_revision_changes_only_one_page(tmp_path):
    from pypdf import PdfReader, PdfWriter

    from qsone.cli.walk import make_revision

    source = tmp_path / "source.pdf"
    writer = PdfWriter()
    for _ in range(3):
        writer.add_blank_page(width=200, height=200)
    writer.write(source)
    before = source.read_bytes()
    out = make_revision(source, tmp_path / "scratch", page=2)
    assert source.read_bytes() == before
    old, new = PdfReader(source), PdfReader(out)
    assert len(new.pages) == 3
    assert [
        i + 1 for i in range(3) if old.pages[i].extract_text() != new.pages[i].extract_text()
    ] == [2]


@pytest.mark.parametrize("command,method", [("file", "POST"), ("deliverable", "GET")])
def test_download_preserves_refusals(tmp_path, command, method):
    from qsone.cli.__main__ import parser
    from qsone.cli.client import Client
    from qsone.cli.commands import Commands
    from qsone.cli.texts import CliError

    out = tmp_path / "sample.pdf"
    out.write_bytes(b"keep existing file")

    def respond(request):
        assert request.method == method
        return httpx.Response(409, json={"error": {"en": "Sign off first", "ar": "اعتمد الأول"}})

    c = Client({"port": 12345, "secret": "sample"})
    c.http.close()
    c.http = httpx.Client(base_url="http://localhost", transport=httpx.MockTransport(respond))
    args = [command, "pdf" if command == "file" else "export", "p", "d", "--out", str(out)]
    if command == "deliverable":
        args += ["--format", "pdf"]
    try:
        with pytest.raises(CliError, match="Sign off first"):
            Commands(c, {}, None).run(parser().parse_args(args))
        assert out.read_bytes() == b"keep existing file"
    finally:
        c.close()


def test_walk_source_and_content_checks():
    from types import SimpleNamespace

    from qsone.cli.walk import Walk

    walk = Walk(SimpleNamespace(client=None))
    walk.boq = {
        "sheets": [
            {
                "rows": [
                    {
                        "kind": "item",
                        "cells": {
                            "unit": {"text": "م3"},
                            "quantity": {"value": "1000", "source": "s"},
                        },
                    }
                ],
                "sources": {"s": {"file_id": "f", "locator": {"page": 1, "box": [0, 0, 10, 10]}}},
            }
        ]
    }
    assert walk.check("boq_items", {"min": 1})
    assert walk.check("boq_sources", {"page_box": True, "minimum_number": 1000})
    assert walk.check("boq_units", ["م3"])
    walk.deliverable = {
        "rows": [{"kind": "item", "cells": {"rate": {"value": "2", "source": "s"}}}],
        "sources": {"s": {"file_id": "f", "locator": {"sheet": "تسعير ", "row": 1, "column": "G"}}},
    }
    assert walk.check("rates_cited", {"sheet": "تسعير "})
    walk.deliverable["rows"][0]["cells"] = {}
    assert not walk.check("rates_cited", {"sheet": "تسعير "})


def test_max_steps_uses_latest_snapshot():
    from types import SimpleNamespace

    from qsone.cli.walk import Walk

    walk = Walk(SimpleNamespace(client=None))
    walk.last = {"events": [{"type": "data-worklog", "data": {"steps": [{}]}}] * 20}
    assert walk.check("max_steps", 1)


def test_walk_catalogue_has_bounded_real_and_sample_parts():
    from decimal import Decimal

    import yaml

    names = [
        "lahun",
        "sgh",
        "brissa",
        "pdf_boq",
        "old_office",
        "pack",
        "compare",
        "prices",
        "estimate",
        "conditions",
        "scanned",
    ]
    documents = [yaml.safe_load((CORE / f"tests/walks/{name}.yaml").read_text()) for name in names]
    assert sum(Decimal(str(d["max_usd"])) for d in documents) <= Decimal("1.4")
    for d in documents:
        assert d["real"] and d["scripted"]
        assert any("check" in step for step in d["real"])
        assert "{test_files}" not in yaml.safe_dump(d["scripted"])


def test_walk_file_indices_follow_upload_order():
    from types import SimpleNamespace

    from qsone.cli.walk import Walk

    class Files:
        def get(self, route):
            return {"files": [{"id": "second"}, {"id": "first"}]}

    walk = Walk(
        SimpleNamespace(client=Files(), files_add=lambda p, paths: {}, files_report=lambda p: {})
    )
    walk.step({"files": ["first.pdf", "second.pdf"]})
    assert [f["id"] for f in walk.files] == ["first", "second"]


def test_changes_count_minimum():
    from types import SimpleNamespace

    from qsone.cli.walk import Walk

    walk = Walk(SimpleNamespace(client=None))
    walk.observed = {"changes": [{}]}
    assert walk.check("changes_count", {"min": 1})


def test_check_command_requires_recorded_current_check():
    from qsone.cli.__main__ import parser
    from qsone.cli.commands import Commands

    class Core:
        def get(self, route):
            return {"version": 2} if not route.endswith("closeout") else {"check": {"version_n": 1}}

    commands = Commands(Core(), {}, None)
    commands.ask = lambda p, text: {"state": "done", "reply": "Sample reply"}
    assert (
        commands.run(parser().parse_args(["deliverable", "check", "p", "d"]))["state"] == "failed"
    )


def test_new_commands_started_core(running, tmp_path):
    from qsone.records.office import find_soffice

    session, started = running
    p = cli(session, "project", "new", "Sample route checks")["id"]
    from tests.bench.samples import QUOTE_NAME, SPEC_NAME

    quote = Path(started["samples"]).parent / "workspace" / "quotes" / QUOTE_NAME
    # Sample path comes from the bench fixture writer, never private tender inputs.
    if not quote.exists():
        quote = next(Path(started["samples"]).parent.glob("workspace/**/*.pdf"))
    cli(session, "files", "add", p, quote, Path(started["samples"]) / SPEC_NAME)
    files = cli(session, "files", "list", p)["files"]
    pdf = next(f["id"] for f in files if f["name"].endswith(".pdf"))
    word = next(f["id"] for f in files if f["name"].endswith(".docx"))
    assert cli(session, "compare", p, pdf, pdf)["changed"] == []
    cli(session, "region", "add", p, pdf, "--page", "1", "--box", "10,10,30,30", "Sample region")
    assert cli(session, "region", "list", p, pdf)["comments"]
    out = tmp_path / "converted.pdf"
    result = cli(session, "file", "pdf", p, word, "--out", out, ok=0 if find_soffice() else 1)
    if find_soffice():
        assert result["pages"] > 0 and out.read_bytes().startswith(b"%PDF")
    else:
        assert "LibreOffice" in result["error"]["en"]
        assert not out.exists()
    assert "month" not in cli(session, "costs", "--today")


def test_pack_download_metadata_and_number_sources(tmp_path):
    from io import BytesIO

    from pypdf import PdfWriter

    from qsone.cli.__main__ import parser, plain
    from qsone.cli.client import Client
    from qsone.cli.commands import Commands

    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.add_outline_item("Sample cover", 0)
    buffer = BytesIO()
    writer.write(buffer)
    seen = []

    def respond(request):
        seen.append((request.method, request.url.path, dict(request.url.params)))
        if request.url.path.endswith("/export"):
            return httpx.Response(200, content=buffer.getvalue())
        if request.url.path.endswith("/build"):
            return httpx.Response(200, json={"pages": 1, "image": "sample"})
        if request.url.path.endswith("/explain"):
            return httpx.Response(
                200,
                json={
                    "source": {
                        "file": "sample.xlsx",
                        "locator": {"sheet": "Sheet1", "row": 12, "column": "D"},
                    }
                },
            )
        return httpx.Response(200, json={"kind": "pack", "version": 2})

    c = Client({"port": 12345, "secret": "sample"})
    c.http.close()
    c.http = httpx.Client(base_url="http://localhost", transport=httpx.MockTransport(respond))
    try:
        commands = Commands(c, {}, None)
        out = tmp_path / "pack.pdf"
        result = commands.run(parser().parse_args(["pack", "build", "p", "d", "--out", str(out)]))
        assert result["pages"] == 1
        assert result["bookmarks"] == [{"title": "Sample cover", "page": 1}]
        assert result["bytes"] == out.stat().st_size > 0
        assert seen[1] == ("POST", "/projects/p/deliverables/d/pack/build", {"version": "2"})
        source = commands.run(parser().parse_args(["number", "explain", "p", "n"]))
        for lang in ("en", "ar"):
            shown = plain(source, lang)
            assert all(v in shown for v in ["sample.xlsx", "Sheet1", "12", "D"])
    finally:
        c.close()


def test_new_output_labels_are_bilingual():
    from qsone.cli.__main__ import plain

    assert "الصفحات" in plain({"pages": 2}, "ar")
    assert "Pages" in plain({"pages": 2}, "en")


def test_empty_document_is_not_a_deliverable():
    from types import SimpleNamespace

    from qsone.cli.walk import Walk

    walk = Walk(SimpleNamespace(client=None))
    walk.deliverable = {
        "kind": "document",
        "blocks": [{"node": {"type": "p", "children": [{"text": "   "}]}}],
    }
    assert not walk.check("deliverable", {"kind": "document"})


def test_numeric_citation_does_not_match_substring():
    from types import SimpleNamespace

    from qsone.cli.walk import Walk

    walk = Walk(SimpleNamespace(client=None))
    walk.last = {"reply": "1200, page 2"}
    walk.evidence["cited"] = {"pieces": [{"text": "1200"}]}
    assert not walk.check("cited", {"value": 200, "page": 2})


def test_sheet_citation_checks_requested_column():
    from types import SimpleNamespace

    from qsone.cli.walk import Walk

    walk = Walk(SimpleNamespace(client=None))
    walk.last = {"reply": "200 in sheet Electrical row 8"}
    walk.evidence["cited"] = {
        "sheet": "Electrical",
        "rows": [{"code": "8", "cells": {"M": {"text": "11700"}, "N": {"text": "200"}}}],
    }
    assert walk.check("cited", {"value": 200, "sheet": "Electrical", "row": 8, "column": "N"})
    assert not walk.check("cited", {"value": 200, "sheet": "Electrical", "row": 8, "column": "M"})


def test_capability_branch_and_scan_checks(monkeypatch):
    from types import SimpleNamespace

    from qsone.cli import walk as module

    walk = module.Walk(SimpleNamespace(client=None, saved={}))
    monkeypatch.setattr(module, "capability", lambda commands, name: name == "available")
    yes = {
        "needs": "available",
        "then": [{"check": {"reply_not_contains": "impossible"}}],
        "otherwise": [{"check": {"reply_contains": "impossible"}}],
    }
    no = dict(yes, needs="missing")
    assert walk.step(yes)["checks"][0]["pass"]
    assert not walk.step(no)["checks"][0]["pass"]
    walk.report = {"files": [{"pdf": {"needs_reading": 2}}]}
    assert walk.check("scan_report", True)
    walk.observed = {
        "pieces": [
            {"text": "عينة", "locator": {"page": 1, "read_by": "tesseract", "box": [1, 2, 3, 4]}}
        ]
    }
    assert walk.check("ocr_boxes", True)
    walk.last = {"reply": "Arabic OCR is missing."}
    assert walk.check("reply_contains_any", ["missing", "unavailable"])


@pytest.mark.parametrize("stop_on_fail", [False, True])
def test_walk_failure_does_not_poison_later_walks(tmp_path, stop_on_fail):
    from types import SimpleNamespace

    import yaml

    from qsone.cli.texts import CliError
    from qsone.cli.walk import run_all

    class Core:
        transient = False

        def get(self, route, **params):
            if self.transient:
                self.transient = False
                raise httpx.ReadError("closed connection after failed command")
            return {"month": "0.02", "unpriced": {"month": 0}}

    core = Core()

    def command(args):
        if args.query == "fail":
            core.transient = True
            raise CliError()
        return {"changes": []}

    commands = SimpleNamespace(
        client=core, saved={"mode": "scripted"}, guard=None, lang="en", run=command
    )
    (tmp_path / "a.yaml").write_text(
        yaml.safe_dump(
            {
                "max_usd": 0.6,
                "scripted": [
                    {"command": ["search", "p", "fail"], "stop_on_fail": stop_on_fail},
                    {"check": {"changes_count": 0}},
                    {"command": ["search", "p", "recover"]},
                    {"check": {"changes_count": 0}},
                ],
            }
        )
    )
    (tmp_path / "b.yaml").write_text(
        "max_usd: 0.6\nscripted:\n- check: {reply_not_contains: impossible}\n"
    )
    result = run_all(commands, tmp_path)
    assert result["status"] == "FAIL"
    assert result["walks"][0]["status"] == "FAIL"
    states = [s["status"] for s in result["walks"][0]["steps"]]
    assert states == (
        ["FAIL", "NOT_RUN", "NOT_RUN", "NOT_RUN"]
        if stop_on_fail
        else ["FAIL", "FAIL", "PASS", "PASS"]
    )
    assert result["walks"][1]["status"] == "PASS"
    assert commands.guard is None


def test_cost_read_failure_is_not_a_cap():
    from types import SimpleNamespace

    from qsone.cli.texts import CliError
    from qsone.cli.walk import Budget

    class Core:
        broken = False
        stopped = []

        def get(self, route):
            if self.broken:
                raise httpx.ReadTimeout("temporary failure")
            return {"month": "0.02", "unpriced": {"month": 0}}

        def post(self, route):
            self.stopped.append(route)

    core = Core()
    budget = Budget(SimpleNamespace(client=core, saved={"mode": "real"}), 1.2)
    core.broken = True
    with pytest.raises(CliError):
        budget("active")
    assert not budget.hit
    assert core.stopped == ["/briefs/active/stop"]
    core.broken = False
    assert not budget(None)


@pytest.mark.parametrize(
    "expected,reply,passed",
    [
        ({"value": "SAR", "paragraph": 7}, "Sample offers use SAR (paragraph 7).", True),
        ({"value": "SAR", "paragraph": 7}, "Sample offers use SAR (paragraph 8).", False),
        (
            {"value": "3259.438571429", "sheet": "", "row": 952},
            "Sample rebar 3259.438571429, row 952.",
            True,
        ),
        ({"value": "3259.438571429", "row": 952}, "Sample rebar 3259.438571429, row 952.", True),
        (
            {"value": "3259.438571429", "sheet": "", "row": 952},
            "Sample rebar 3259.438571429, row 953.",
            False,
        ),
    ],
)
def test_paragraph_and_csv_row_citations(expected, reply, passed):
    from types import SimpleNamespace

    from qsone.cli.walk import Walk

    walk = Walk(SimpleNamespace(client=None))
    walk.last = {"reply": reply}
    walk.evidence["cited"] = {
        "pieces": [{"text": "SAR", "locator": {"paragraph": 7}}],
        "sheet": "",
        "rows": [{"code": "952", "cells": {"H": {"text": "3259.438571429"}}}],
    }
    assert walk.check("cited", expected) is passed


def test_select_deliverable_variant_from_full_view():
    from types import SimpleNamespace

    from qsone.cli.walk import Walk

    class Core:
        def get(self, route):
            if route.endswith("/deliverables"):
                return {
                    "deliverables": [{"id": "a", "kind": "sheet"}, {"id": "b", "kind": "sheet"}]
                }
            return {
                "id": route.rsplit("/", 1)[-1],
                "kind": "sheet",
                "variant": "boq" if route.endswith("/b") else "estimate",
            }

    walk = Walk(SimpleNamespace(client=Core()))
    walk.project = "p"
    assert walk.step({"deliverable": {"kind": "sheet", "variant": "boq"}})["id"] == "b"


@pytest.mark.parametrize("text", ["Sample total 1672000.00.", "Sample total ١٬٦٧٢٬٠٠٠.٠٠."])
def test_reply_numbers_sentence_period(text):
    from types import SimpleNamespace

    from qsone.cli.walk import Walk

    walk = Walk(SimpleNamespace(client=None))
    walk.last = {"reply": text}
    assert walk.check("reply_numbers", [1672000])


def test_failed_check_preserves_evidence_for_independent_checks(tmp_path):
    from types import SimpleNamespace

    from qsone.cli.walk import run

    class Core:
        def get(self, route, **params):
            return {"month": "0", "unpriced": {"month": 0}}

    commands = SimpleNamespace(
        client=Core(),
        saved={"mode": "scripted"},
        guard=None,
        lang="en",
        run=lambda args: {"out": "sample.pdf", "bytes": 0, "pages": 2},
    )
    file = tmp_path / "walk.yaml"
    file.write_text(
        "scripted:\n- command: [search,p,sample]\n"
        "- check: {export_ok: true}\n- check: {pack_pages: 2}\n"
    )
    result = run(commands, file)
    assert [s["status"] for s in result["steps"]] == ["PASS", "FAIL", "PASS"]


def test_invalid_walk_command_is_only_a_failed_step(tmp_path):
    from types import SimpleNamespace

    from qsone.cli.walk import run

    class Core:
        def get(self, route, **params):
            return {"month": "0", "unpriced": {"month": 0}}

    commands = SimpleNamespace(client=Core(), saved={"mode": "scripted"}, guard=None, lang="en")
    file = tmp_path / "walk.yaml"
    file.write_text(
        "scripted:\n- command: [invalid-command]\n"
        "- check: {reply_contains: impossible}\n- check: {reply_not_contains: impossible}\n"
    )
    result = run(commands, file)
    assert [s["status"] for s in result["steps"]] == ["FAIL", "FAIL", "FAIL"]


@pytest.mark.parametrize("nested_stop", [False, True])
def test_failure_context_crosses_capability_branches(tmp_path, monkeypatch, nested_stop):
    from types import SimpleNamespace

    import yaml

    from qsone.cli import walk as module
    from qsone.cli.texts import CliError

    class Core:
        def get(self, route, **params):
            return {"month": "0.02", "unpriced": {"month": 0}}

    calls = []

    def command(args):
        calls.append(args.query)
        if args.query == "fail":
            raise CliError()
        return {"pages": 2}

    commands = SimpleNamespace(
        client=Core(), saved={"mode": "scripted"}, guard=None, lang="en", run=command
    )
    monkeypatch.setattr(module, "capability", lambda c, n: True)
    steps = (
        [{"needs": "sample", "then": [{"command": ["search", "p", "fail"], "stop_on_fail": True}]}]
        if nested_stop
        else [
            {"command": ["search", "p", "fail"]},
            {"check": {"reply_not_contains": "impossible"}},
            {"needs": "sample", "then": [{"check": {"reply_not_contains": "impossible"}}]},
        ]
    ) + [{"command": ["search", "p", "recover"]}, {"check": {"pack_pages": 2}}]
    file = tmp_path / "nested.yaml"
    file.write_text(yaml.safe_dump({"scripted": steps}))
    result = module.run(commands, file)
    assert result["status"] == "FAIL"
    assert calls == (["fail"] if nested_stop else ["fail", "recover"])
    assert [s["status"] for s in result["steps"]] == (
        ["FAIL", "NOT_RUN", "NOT_RUN"] if nested_stop else ["FAIL", "FAIL", "FAIL", "PASS", "PASS"]
    )


def test_csv_citation_uses_physical_start_line_after_multiline_fields():
    from types import SimpleNamespace

    from qsone.cli.walk import Walk
    from qsone.records.sheetview import _csv_sheet

    sheet = _csv_sheet(b'Month,Price\n"Sample\nfirst",100\nSample second,3200\n')
    assert sheet.cells[4][2].value == "3200"
    walk = Walk(SimpleNamespace(client=None))
    walk.last = {"reply": "Sample price 3200, row 4."}
    walk.evidence["cited"] = {
        "sheet": "",
        "rows": [
            {
                "code": str(row),
                "cells": {str(column): {"text": cell.value} for column, cell in cells.items()},
            }
            for row, cells in sheet.cells.items()
        ],
    }
    assert walk.check("cited", {"value": 3200, "row": 4})
    assert not walk.check("cited", {"value": 3200, "row": 3})
