"""Synthetic CLI regressions; no provider calls."""

import json
from pathlib import Path

import httpx
import pytest

from qsone.cli.__main__ import parser
from qsone.cli.client import Client
from qsone.cli.commands import Commands


@pytest.fixture
def adapter(tmp_path):
    seen = []
    replies = []

    def respond(request):
        seen.append(request)
        return httpx.Response(200, json=replies.pop(0) if replies else {})

    c = Client({"port": 12345, "secret": "sample"})
    c.http.close()
    c.http = httpx.Client(base_url="http://localhost", transport=httpx.MockTransport(respond))
    yield Commands(c, {"cards": {}}, tmp_path / "private" / "session.json"), seen, replies
    c.close()


@pytest.mark.parametrize(
    "argv,route,body",
    [
        (["map", "p", "--group", "A", "--cursor", "c"], "/projects/p/map", None),
        (["map", "p", "--file", "f"], "/projects/p/map/files/f", None),
        (["facts", "p"], "/projects/p/map/facts", None),
        (["links", "p"], "/projects/p/map/links", None),
        (["fact", "confirm", "p", "f"], "/projects/p/map/facts/f", {"confirm": True}),
        (["fact", "correct", "p", "f", "SAR"], "/projects/p/map/facts/f", {"value": "SAR"}),
    ],
)
def test_map_routes(adapter, argv, route, body):
    commands, seen, replies = adapter
    replies.append({"sample": True})
    assert commands.run(parser().parse_args(argv)) == {"sample": True}
    assert seen[0].url.path == route
    if body:
        assert json.loads(seen[0].content) == body
    if "--group" in argv:
        assert dict(seen[0].url.params) == {"parent": "A", "cursor": "c"}


def test_directory_preserves_folders(adapter, tmp_path):
    commands, seen, replies = adapter
    root = tmp_path / "عينة"
    for folder in ["01 المستلم", "02 الفني/النسخة العربية Rev000", ".hidden"]:
        directory = root / folder
        directory.mkdir(parents=True)
        (directory / "sample.txt").write_text("sample " + folder)
    (root / "Thumbs.db").write_text("system")
    commands.files_add("p", [root])
    assert len(seen) == 2
    assert {r.url.params["folder"] for r in seen} == {
        "عينة/01 المستلم",
        "عينة/02 الفني/النسخة العربية Rev000",
    }


def test_human_reply_only_final_worklog():
    from qsone.cli.__main__ import human_result, plain

    step = {"agent": "lead", "text": {"en": "Read sample", "ar": "قرا العينة"}, "at": "sample"}
    result = {
        "reply": "Sample reply",
        "cards": [],
        "state": "done",
        "costs": {},
        "events": [
            {"type": "data-worklog", "data": {"steps": [step]}},
            {"type": "data-worklog", "data": {"steps": [step, step]}},
            {"type": "data-progress", "data": "noisy"},
        ],
    }
    shown = plain(human_result(result), "en")
    assert shown.count("Read sample") == 1
    assert "1." in shown and "noisy" not in shown and "events" not in shown


def test_stop_already_exited_zombie(adapter, monkeypatch):
    from qsone.cli import session

    commands, _, _ = adapter
    saved = dict(
        owned=True,
        pid=987654,
        birth="123",
        port=12345,
        mode="scripted",
        data_dir="/tmp/sample",
        samples="/tmp/sample/samples",
    )
    session.save(commands.path, saved)
    original = Path.read_text

    def read(path, *a, **kw):
        if str(path) == "/proc/987654/stat":
            return "987654 (python) Z " + " ".join(["0"] * 18 + ["123"])
        return original(path, *a, **kw)

    monkeypatch.setattr(Path, "read_text", read)
    monkeypatch.setattr(Path, "read_bytes", lambda path: b"")
    monkeypatch.setattr(session.os, "kill", lambda *a: pytest.fail("must not signal zombie"))
    assert session.stop(commands.path)["state"] == "stopped"


def test_map_wait_waits_for_ai_and_caches_cost_card(adapter):
    commands, seen, replies = adapter
    replies.extend(
        [
            {
                "status": {"waiting": 0, "reading": 0},
                "files": [{"file_id": "f", "ai_state": "waiting", "local_state": "done"}],
            },
            {
                "messages": [
                    {
                        "parts": [
                            {
                                "type": "data-card",
                                "id": "cost1",
                                "data": {
                                    "kind": "cost",
                                    "status": "pending",
                                    "options": ["yes", "no"],
                                },
                            }
                        ]
                    }
                ]
            },
        ]
    )
    result = commands.run(parser().parse_args(["map", "p", "--wait", "1"]))
    assert result["state"] == "waiting_engineer"
    assert result["cards"][0]["id"] == "cost1"
    assert json.loads(commands.path.read_text())["cards"]["cost1"]["chat"] == "p"


def test_human_summary_and_fact_states():
    from qsone.cli.__main__ import human_result, plain

    result = human_result(
        {"uploads": [{"status": "read"}, {"status": "partly_read"}, {"status": "failed"}]}
    )
    assert result == {"count": 3, "read": 1, "partly_read": 1, "failed": 1}
    for state, en, ar in [
        ("found", "read by ONE, not checked", "قراه ONE، لسه متراجعش"),
        ("blank", "Blank", "فاضي"),
        ("conflict", "Conflict", "تعارض"),
    ]:
        fact = {"facts": [{"state": state, "file_id": "f", "locator": {"page": 3}}]}
        assert en in plain(fact, "en")
        assert ar in plain(fact, "ar")


def test_drawings_map_includes_sheets(adapter):
    commands, _, replies = adapter
    replies.extend(
        [
            {"files": [{"file_id": "f", "kind": "dxf"}]},
            {"sheets": [{"number": "A1", "title": "Sample"}]},
        ]
    )
    result = commands.run(parser().parse_args(["map", "p"]))
    assert result["files"][0]["sheets"][0]["number"] == "A1"


def test_stop_retains_session_on_slow_shutdown(adapter, monkeypatch):
    from qsone.cli import session
    from qsone.cli.texts import CliError

    commands, _, _ = adapter
    saved = dict(
        owned=True,
        pid=987654,
        birth="123",
        port=12345,
        mode="scripted",
        data_dir="/tmp/sample",
        samples="/tmp/sample/samples",
    )
    session.save(commands.path, saved)
    original = Path.read_text
    monkeypatch.setattr(
        Path,
        "read_text",
        lambda path, *a, **kw: (
            "987654 (python) S " + " ".join(["0"] * 18 + ["123"])
            if str(path) == "/proc/987654/stat"
            else original(path, *a, **kw)
        ),
    )
    expected = session.command("scripted", 12345, saved["data_dir"], saved["samples"])
    monkeypatch.setattr(Path, "read_bytes", lambda path: ("\0".join(expected) + "\0").encode())
    killed = []
    monkeypatch.setattr(session.os, "kill", lambda *a: killed.append(a))
    times = iter([0, 11])
    monkeypatch.setattr(session.time, "monotonic", lambda: next(times))
    with pytest.raises(CliError, match="still shutting down"):
        session.stop(commands.path)
    assert commands.path.exists() and len(killed) == 1


def test_stop_refuses_reused_pid_even_if_zombie(adapter, monkeypatch):
    from qsone.cli import session
    from qsone.cli.texts import CliError

    commands, _, _ = adapter
    session.save(
        commands.path,
        dict(
            owned=True,
            pid=987654,
            birth="old",
            port=12345,
            mode="scripted",
            data_dir="/tmp/sample",
            samples="/tmp/sample/samples",
        ),
    )
    original = Path.read_text
    monkeypatch.setattr(
        Path,
        "read_text",
        lambda path, *a, **kw: (
            "987654 (python) Z " + " ".join(["0"] * 18 + ["new"])
            if str(path) == "/proc/987654/stat"
            else original(path, *a, **kw)
        ),
    )
    monkeypatch.setattr(session.os, "kill", lambda *a: pytest.fail("unowned process"))
    with pytest.raises(CliError, match="identity changed"):
        session.stop(commands.path)
    assert commands.path.exists()


def test_zip_summary_counts_members():
    from qsone.cli.__main__ import human_result

    result = human_result(
        {
            "uploads": [
                {
                    "zip": True,
                    "files": [{"status": "read"}, {"status": "partly_read"}],
                    "skipped": [{"error": {"en": "Sample", "ar": "عينة"}}],
                }
            ]
        }
    )
    assert result == {"count": 3, "read": 1, "partly_read": 1, "failed": 1}


def test_stop_live_wrong_launcher_is_not_signalled(adapter, monkeypatch):
    from qsone.cli import session
    from qsone.cli.texts import CliError

    commands, _, _ = adapter
    session.save(
        commands.path,
        dict(
            owned=True,
            pid=987654,
            birth="123",
            port=12345,
            mode="scripted",
            data_dir="/tmp/sample",
            samples="/tmp/sample/samples",
        ),
    )
    original = Path.read_text
    monkeypatch.setattr(
        Path,
        "read_text",
        lambda path, *a, **kw: (
            "987654 (python) S " + " ".join(["0"] * 18 + ["123"])
            if str(path) == "/proc/987654/stat"
            else original(path, *a, **kw)
        ),
    )
    monkeypatch.setattr(Path, "read_bytes", lambda path: b"other-process\0")
    monkeypatch.setattr(session.os, "kill", lambda *a: pytest.fail("wrong launcher"))
    with pytest.raises(CliError, match="identity changed"):
        session.stop(commands.path)
    assert commands.path.exists()


def test_map_wait_checks_later_pages(adapter):
    commands, _, replies = adapter
    replies.extend(
        [
            {
                "status": {"waiting": 0, "reading": 0},
                "files": [{"file_id": "a", "ai_state": "done"}],
                "next_cursor": "page2",
            },
            {"files": [{"file_id": "b", "ai_state": "waiting"}], "next_cursor": None},
            {"messages": []},
        ]
    )
    result = commands.run(parser().parse_args(["map", "p", "--wait", "0"]))
    assert result["state"] == "timeout"
