"""The Subscription Link: the engineer's own Claude Code (Plan 4, Task 5).

Every test runs the stand-in `claude` in `fakes/fake_claude.py`; none runs the real one, and none
calls a real AI. Synthetic «عينة» data only."""

import asyncio
import json
import os
import stat
import subprocess
import sys
import time
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from qsone import copy, settings
from qsone.engine import connectors
from qsone.engine.connectors import claude_code
from qsone.engine.connectors.claude_code import AgentJob, ClaudeCodeConnector, status
from qsone.engine.mcp_server import McpGate, RunScope
from qsone.engine.routes import settings_router
from qsone.engine.types import AgentSpec, Progress, TextDelta
from tests import test_engine_mcp as mcp_tests
from tests import test_engine_tools as tools_tests
from tests.engine_fakes import fake_claude_command, read_fake_log

# The fixtures of the tool and MCP tests.
host = tools_tests.host
ctx = tools_tests.ctx
boq_ctx = tools_tests.boq_ctx
core_server = mcp_tests.core_server

POSIX = os.name == "posix"
SESSION = "6d22c32a-00da-4d6b-86b4-f13482078290"
INSTRUCTIONS = "You are the Lead QS - sample instructions."
LEAD = AgentSpec(
    id="lead", name=copy.ROLE_LEAD, role="lead", instructions=INSTRUCTIONS, tools=(), tier="lead"
)
SPECIALIST = AgentSpec(
    id="spec-1",
    name={"en": "Quantities - sample", "ar": "الكميات - عينة"},
    role="specialist",
    instructions="Find quantities - sample.",
    tools=(),
    tier="specialist",
)


@pytest.fixture
def log(tmp_path):
    return tmp_path / "fake-claude.jsonl"


@pytest.fixture
def work(tmp_path):
    return tmp_path / "data" / "claude-work"


def link(script, log, **options) -> ClaudeCodeConnector:
    command = fake_claude_command(
        script=script,
        log=log,
        drop=options.pop("drop", ()),
        signed_out=options.pop("signed_out", False),
    )
    return ClaudeCodeConnector(None, command_prefix=command, **options)


def job(work, **fields) -> AgentJob:
    values = {
        "run_id": "run-1",
        "brief_id": "brief-1",
        "spec": LEAD,
        "task": "سعّر بند الخرسانة - عينة",
        "model": None,
        "mcp_url": "http://127.0.0.1:9/mcp",
        "mcp_token": "sample-run-token",
        "tools": ("search_records",),
        "cwd": work / fields.get("run_id", "run-1"),
        "resume": None,
    }
    return AgentJob(**(values | fields))


def after(argv: list[str], flag: str) -> str:
    return argv[argv.index(flag) + 1]


async def until(check, timeout: float = 10) -> None:
    deadline = time.monotonic() + timeout
    while not check():
        assert time.monotonic() < deadline, "timed out"
        await asyncio.sleep(0.02)


def started(log, n: int = 0) -> bool:
    """The fake has started run `n` and read its first stdin line."""
    try:
        runs = read_fake_log(log)
    except FileNotFoundError:
        return False
    return len(runs) > n and bool(runs[n]["stdin"])


# status --------------------------------------------------------------------------------------


async def test_status_reads_flags_version_and_sign_in():
    found = await status(None, command_prefix=fake_claude_command())
    assert found.installed and found.compatible and found.signed_in is True
    assert found.version == "2.1.318" and found.code is None
    assert found.models == ("opus", "sonnet", "haiku")

    signed_out = await status(None, command_prefix=fake_claude_command(signed_out=True))
    assert signed_out.compatible and signed_out.signed_in is False
    assert signed_out.code == "CLAUDE_CODE_SIGNED_OUT"


async def test_missing_flag_is_too_old():
    for drop in [("--strict-mcp-config",), ("--system-prompt-file", "--append-system-prompt-file")]:
        found = await status(None, command_prefix=fake_claude_command(drop=drop))
        assert found.installed and not found.compatible and found.code == "CLAUDE_CODE_TOO_OLD"
    either = await status(None, command_prefix=fake_claude_command(drop=("--system-prompt-file",)))
    assert either.compatible  # --append-system-prompt-file is the fallback


async def test_cmd_shim_is_refused(tmp_path):
    for name in ("claude.cmd", "claude.CMD", "claude.bat", "claude.ps1"):
        shim = tmp_path / name
        shim.write_text("@echo off\n", encoding="utf-8")
        found = await status(str(shim))
        assert not found.installed and found.code == "CLAUDE_CODE_SHIM"
    assert copy.CLAUDE_CODE_SHIM["en"] and copy.CLAUDE_CODE_SHIM["ar"]


def test_the_npm_shim_on_the_windows_path_is_refused(tmp_path, monkeypatch):
    (tmp_path / "claude.cmd").write_text("@echo off\n", encoding="utf-8")
    monkeypatch.setattr(claude_code, "WINDOWS", True)
    monkeypatch.setenv("PATH", str(tmp_path))
    assert claude_code.executable(None) == (None, "CLAUDE_CODE_SHIM")


async def test_missing_claude_says_where_to_get_it(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path))
    for picked in (None, "claude", str(tmp_path / "nowhere" / "claude")):
        found = await status(picked)
        assert not found.installed and found.code == "CLAUDE_CODE_MISSING"
    assert "https://code.claude.com/docs/en/setup" in copy.CLAUDE_CODE_MISSING["ar"]


@pytest.mark.skipif(not POSIX, reason="an executable file on PATH is a POSIX mode bit")
def test_claude_is_found_on_path(tmp_path, monkeypatch):
    found = tmp_path / "claude"
    found.write_text("#!/bin/sh\n", encoding="utf-8")
    found.chmod(0o755)
    monkeypatch.setenv("PATH", f"relative/bin{os.pathsep}{tmp_path}")
    assert claude_code.executable(None) == (found, None)


async def test_check_is_auth_status_only(log):
    assert await connectors.check("claude-code", among=[link([], log)]) is None
    assert await link([], log, signed_out=True).check() == copy.CLAUDE_CODE_SIGNED_OUT
    too_old = link([], log, drop=("--tools",))
    assert await too_old.check() == copy.CLAUDE_CODE_TOO_OLD
    assert not log.exists()  # nothing ran with -p: no model was asked anything


async def test_a_claude_that_will_not_answer_is_plain():
    broken = ClaudeCodeConnector(None, command_prefix=[sys.executable, "-c", "raise SystemExit(1)"])
    found = await status(None, command_prefix=broken._prefix)
    assert found.installed and not found.compatible and found.code == "AI_FAILED"
    assert await broken.check() == copy.fill(copy.AI_FAILED, provider="Claude Code")
    assert await broken.cards() == []


# run -----------------------------------------------------------------------------------------


async def test_run_passes_only_safe_flags_and_env(log, work, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-never-passed")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://never.example")
    events = []
    out = await link(["init", {"text": "تمام - عينة"}, "result"], log).run(job(work), events.append)
    [run] = read_fake_log(log)
    argv = run["argv"]
    assert after(argv, "--tools") == ""
    assert "--strict-mcp-config" in argv and after(argv, "--permission-mode") == "dontAsk"
    assert after(argv, "--allowedTools") == "mcp__one__search_records"
    assert "Bash" in after(argv, "--disallowedTools").split(",")
    assert after(argv, "--setting-sources") == ""
    assert json.loads(after(argv, "--settings")) == {"disableAllHooks": True}
    assert ["-p", "--input-format", "stream-json", "--output-format", "stream-json"] == argv[:5]
    assert "--verbose" in argv and "--include-partial-messages" in argv
    assert "--model" not in argv and "--resume" not in argv and "--bare" not in argv
    assert "--no-session-persistence" not in argv  # Claude Code keeps its copy (the default)
    assert not any(name.startswith("ANTHROPIC") for name in run["env_names"])
    assert "MCP_TOOL_TIMEOUT" in run["env_names"]
    assert set(run["env_names"]) <= set(claude_code.ENV_NAMES) | {"MCP_TOOL_TIMEOUT"}
    assert run["files"]["--system-prompt-file"] == INSTRUCTIONS
    mcp = json.loads(run["files"]["--mcp-config"])
    assert mcp == {
        "mcpServers": {
            "one": {
                "type": "http",
                "url": "http://127.0.0.1:9/mcp",
                "headers": {"Authorization": "Bearer sample-run-token"},
            }
        }
    }
    [line] = run["stdin"]
    assert line["type"] == "user" and line["message"]["role"] == "user"
    assert line["message"]["content"] == [{"type": "text", "text": "سعّر بند الخرسانة - عينة"}]
    assert out.ended == "done" and out.text == "تمام - عينة"


async def test_model_and_prompt_fallback_flags(log, work):
    connector = link(["init", "result"], log, drop=("--system-prompt-file",))
    await connector.run(job(work, model="sonnet"), lambda e: None)
    [run] = read_fake_log(log)
    assert after(run["argv"], "--model") == "sonnet"
    assert run["files"]["--append-system-prompt-file"] == INSTRUCTIONS


async def test_unsafe_model_or_session_is_refused(log, work):
    for fields in ({"model": "--dangerously-skip-permissions"}, {"resume": "not-a-session"}):
        out = await link(["init", "result"], log).run(job(work, **fields), lambda e: None)
        assert out.ended == "failed"
    assert not log.exists()


async def test_stream_becomes_events_and_usage(log, work):
    script = [
        {"init": {"session_id": SESSION, "model": "claude-sonnet-5-5"}},
        {"text": ["سعر المتر", " - عينة"], "id": "msg_a", "usage": [1200, 80]},
        {"text": "تم", "id": "msg_b", "usage": [1300, 20]},
        {"result": {"cost": "0.0123"}},
    ]
    events = []
    out = await link(script, log).run(job(work), events.append)
    assert [e.text for e in events if isinstance(e, TextDelta)] == ["سعر المتر", " - عينة", "تم"]
    assert all(e.brief_id == "brief-1" for e in events)
    assert out.usage == (("msg_a", 1200, 80), ("msg_b", 1300, 20))
    assert out.session_id == SESSION and out.reported_usd == Decimal("0.0123")
    assert out.ended == "done" and out.text == "تم"


async def test_a_specialists_text_goes_to_the_progress_line(log, work):
    events = []
    script = ["init", {"text": "لقيت كمية البند - عينة"}, "result"]
    await link(script, log).run(job(work, spec=SPECIALIST), events.append)
    assert not [e for e in events if isinstance(e, TextDelta)]
    [progress] = [e for e in events if isinstance(e, Progress)]
    assert progress.run_id == "run-1" and progress.agent == SPECIALIST.name
    assert progress.text["ar"] == "لقيت كمية البند - عينة"


async def test_mcp_round_trip_through_the_gate(core_server, boq_ctx, log, work):
    token = core_server.gate.issue(RunScope(boq_ctx, ("search_records",)))
    script = [
        "init",
        {"mcp_call": {"tool": "search_records", "args": {"query": "عزل"}}},
        {"text": "لقيت البند - عينة"},
        "result",
    ]
    events = []
    out = await link(script, log).run(
        job(work, mcp_url=core_server.url, mcp_token=token, brief_id=boq_ctx.brief_id),
        events.append,
    )
    assert out.ended == "done"
    assert boq_ctx.store.brief(boq_ctx.brief_id)["read_untrusted"] == 1  # the data fence ran
    tools_used = [e.text for e in events if isinstance(e, Progress)]
    assert tools_used == [copy.fill(copy.TOOL_SEARCH_RECORDS, query="عزل")]


async def test_an_unknown_tool_ends_the_run(log, work):
    script = ["init", {"tool_use": {"name": "Bash", "input": {"command": "ls"}}}, {"sleep": 30}]
    began = time.monotonic()
    out = await link(script, log).run(job(work), lambda e: None)
    assert out.ended == "failed" and time.monotonic() - began < 10
    [run] = read_fake_log(log)
    assert run["ended"] in ("interrupted", "terminated")


async def test_config_is_private_and_removed(ctx, log, work):
    gate = McpGate()
    token = gate.issue(RunScope(ctx, ("find_items",)))
    connector = link(["init", {"sleep": 1}, "result"], log, gate=gate)
    the_job = job(work, mcp_token=token, tools=("find_items",))
    task = asyncio.create_task(connector.run(the_job, lambda e: None))
    config = the_job.cwd / claude_code.MCP_FILE
    await until(config.exists)
    if POSIX:
        assert stat.S_IMODE(config.stat().st_mode) == 0o600
        assert stat.S_IMODE((the_job.cwd / claude_code.INSTRUCTIONS_FILE).stat().st_mode) == 0o600
        assert stat.S_IMODE(the_job.cwd.stat().st_mode) == 0o700
    out = await task
    assert out.ended == "done"
    assert the_job.cwd.is_dir() and list(the_job.cwd.iterdir()) == []  # kept for --resume
    assert gate.scope(token) is None  # revoked when the run ended


@pytest.mark.skipif(not POSIX, reason="symlinks need extra rights on Windows")
async def test_a_symlinked_or_used_folder_is_refused(log, work, tmp_path):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    work.mkdir(parents=True)
    (work / "run-1").symlink_to(elsewhere)
    out = await link(["init", "result"], log).run(job(work), lambda e: None)
    assert out.ended == "failed" and list(elsewhere.iterdir()) == []
    (work / "run-2").mkdir()
    (work / "run-2" / "CLAUDE.md").write_text("sample", encoding="utf-8")
    out = await link(["init", "result"], log).run(job(work, run_id="run-2"), lambda e: None)
    assert out.ended == "failed" and not log.exists()


async def test_resume_uses_the_session_and_the_same_folder(log, work):
    script = {"runs": [[{"init": {"session_id": SESSION}}, {"text": "أول - عينة"}, "result"]]}
    connector = link(script, log)
    first = await connector.run(job(work), lambda e: None)
    again = await connector.run(job(work, resume=first.session_id, task="كمّل"), lambda e: None)
    one, two = read_fake_log(log)
    assert first.session_id == SESSION and again.session_id == SESSION
    assert "--resume" not in one["argv"] and after(two["argv"], "--resume") == SESSION
    assert one["cwd"] == two["cwd"]


async def test_without_the_copy_nothing_is_resumed(log, work):
    out = await link(["init", "result"], log, keep_copy=False).run(
        job(work, resume=SESSION), lambda e: None
    )
    [run] = read_fake_log(log)
    assert "--no-session-persistence" in run["argv"] and "--resume" not in run["argv"]
    assert out.ended == "done"


async def test_cut_off_answer_continues_once(log, work):
    cut = {"text": "الجزء الأول", "id": "msg_1", "usage": [500, 4000], "stop_reason": "max_tokens"}
    script = {
        "runs": [
            [{"init": {"session_id": SESSION}}, cut, "result"],
            [{"init": {"session_id": SESSION}}, cut, {"text": " والتاني", "id": "msg_2"}, "result"],
        ]
    }
    events = []
    out = await link(script, log).run(job(work), events.append)
    one, two = read_fake_log(log)
    assert after(two["argv"], "--resume") == SESSION
    assert two["stdin"][0]["message"]["content"][0]["text"] == claude_code.CONTINUE
    assert out.ended == "done" and out.text == "الجزء الأول والتاني"
    assert [e.text for e in events if isinstance(e, TextDelta)] == ["الجزء الأول", " والتاني"]
    assert out.usage == (("msg_1", 500, 4000), ("msg_2", 100, 10))  # the replay counted once


async def test_cut_off_twice_stops_after_one_more(log, work):
    cut = {"text": "مقطوع", "stop_reason": "max_tokens"}
    out = await link(["init", cut, "result"], log).run(job(work), lambda e: None)
    assert out.ended == "max_tokens" and len(read_fake_log(log)) == 2


async def test_dropped_stream_reports_dropped(log, work):
    script = [{"init": {"session_id": SESSION}}, {"text": "نص - عينة"}, "drop"]
    out = await link(script, log).run(job(work), lambda e: None)
    assert out.ended == "dropped" and out.session_id == SESSION


@pytest.mark.parametrize(
    "error, ended", [("rate_limit", "limit"), ("authentication_failed", "signed_out")]
)
async def test_limit_and_signed_out_are_plain(log, work, error, ended):
    began = time.monotonic()
    script = ["init", {"error": error}, {"sleep": 30}, "result"]
    out = await link(script, log).run(job(work), lambda e: None)
    assert out.ended == ended and time.monotonic() - began < 10


async def test_stop_ends_the_process_on_every_system(log, work):
    connector = link(["init", {"sleep": 60}, "result"], log)
    task = asyncio.create_task(connector.run(job(work), lambda e: None))
    await until(lambda: started(log))
    began = time.monotonic()
    await connector.stop("run-1")
    out = await task
    assert out.ended == "stopped" and time.monotonic() - began < 10
    [run] = read_fake_log(log)
    assert run["ended"] == "interrupted"
    assert run["stdin"][-1]["type"] == "control_request"
    assert run["stdin"][-1]["request"] == {"subtype": "interrupt"}


async def test_cancelling_the_run_ends_the_process(log, work):
    connector = link(["init", {"sleep": 60}, "result"], log)
    task = asyncio.create_task(connector.run(job(work), lambda e: None))
    await until(lambda: started(log))
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    [run] = read_fake_log(log)
    assert run["ended"] in ("interrupted", "terminated")


async def test_steer_writes_one_more_user_line(log, work):
    connector = link(["init", {"sleep": 0.5}, "result"], log)
    task = asyncio.create_task(connector.run(job(work), lambda e: None))
    await until(lambda: started(log))
    await connector.steer("run-1", "خلّي السعر بالجنيه - عينة")
    await task
    [run] = read_fake_log(log)
    users = [line for line in run["stdin"] if line["type"] == "user"]
    assert len(users) == 2
    assert users[1]["message"]["content"] == [{"type": "text", "text": "خلّي السعر بالجنيه - عينة"}]
    with pytest.raises(LookupError):
        await connector.steer("run-1", "no run - sample")


def test_two_runs_started_at_once_get_their_own_numbers(log):
    """The fake numbers its runs with a counter, not by counting the log, so two processes
    started together each play their own run of the script."""
    script = {"runs": [[{"text": f"run {n}"}, "result"] for n in range(3)]}
    argv = [*fake_claude_command(script=script, log=log), "-p", "--verbose"]
    argv += ["--input-format", "stream-json", "--output-format", "stream-json"]
    line = json.dumps({"type": "user", "message": {"role": "user", "content": "عينة"}}) + "\n"
    started_together = [
        subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        for _ in range(3)
    ]
    answers = []
    for process in started_together:
        out, _ = process.communicate(line, timeout=30)
        [result] = [v for v in map(json.loads, out.splitlines()) if v["type"] == "result"]
        answers.append(result["result"])
    assert sorted(answers) == ["run 0", "run 1", "run 2"]
    runs = read_fake_log(log)
    assert [run["n"] for run in runs] == [0, 1, 2]
    assert [run["ended"] for run in runs] == ["done", "done", "done"]
    assert all(len(run["stdin"]) == 1 for run in runs)


async def test_cards_are_the_aliases_on_the_subscription(log):
    found = await link([], log).cards()
    assert [c.choice.model for c in found] == ["opus", "sonnet", "haiku"]
    opus = found[0]
    assert (
        opus.choice.connector == "claude-code"
        and opus.subscription
        and opus.provider == "anthropic"
    )
    assert opus.price_in > 0 and opus.price_out > 0
    assert opus.price_source.startswith("genai-prices ") and "claude-opus-" in opus.price_source


# routes --------------------------------------------------------------------------------------


def client(command: list[str] | None = None) -> TestClient:
    app = FastAPI()
    app.include_router(settings_router(claude_command=command or ()))
    return TestClient(app)


def test_the_check_route_answers_the_screens_shape():
    answer = client(fake_claude_command()).get("/settings/ai/claude-code").json()
    assert answer == {
        "installed": True,
        "compatible": True,
        "signed_in": True,
        "version": "2.1.318",
        "code": None,
        "models": ["opus", "sonnet", "haiku"],
    }


def test_switching_claude_code_on_and_off():
    http = client(fake_claude_command())
    assert not [c for c in http.get("/settings/ai").json()["connectors"] if c["kind"] == "agent"]

    on = http.put("/settings/ai/claude-code", json={"path": None, "on": True})
    assert on.status_code == 200 and on.json()["notice"] == copy.CLAUDE_CODE_COPY
    assert settings.ai()["claude_code"] == {"path": None, "on": True, "keep_copy": True}
    listed = http.get("/settings/ai").json()
    [agent] = [c for c in listed["connectors"] if c["id"] == "claude-code"]
    assert agent["kind"] == "agent" and agent["name"] == "Claude Code"
    subscription = [c for c in listed["sheet"] if c["connector"] == "claude-code"]
    assert [c["model"] for c in subscription] == ["opus", "sonnet", "haiku"]
    assert all(c["subscription"] and c["price_in"] for c in subscription)

    off = http.put("/settings/ai/claude-code", json={"path": None, "on": False})
    assert off.json()["notice"] is None
    assert not [c for c in http.get("/settings/ai").json()["connectors"] if c["kind"] == "agent"]


def test_the_picked_file_is_checked(tmp_path):
    shim = tmp_path / "claude.cmd"
    shim.write_text("@echo off\n", encoding="utf-8")
    http = client()
    assert http.put("/settings/ai/claude-code", json={"path": f" {shim} ", "on": False}).is_success
    assert settings.ai()["claude_code"]["path"] == str(shim)
    answer = http.get("/settings/ai/claude-code").json()
    assert answer["installed"] is False and answer["code"] == "CLAUDE_CODE_SHIM"


def test_keeping_the_copy_is_one_setting():
    http = client(fake_claude_command())
    put = http.put("/settings/ai/claude-code", json={"path": None, "on": True, "keep_copy": False})
    assert put.json()["notice"] is None and settings.ai()["claude_code"]["keep_copy"] is False
    [found] = [c for c in connectors.connectors() if c.id == "claude-code"]
    assert found.keep_copy is False


def test_bad_claude_code_bodies_are_refused():
    http = client()
    for body in ({"path": None}, {"on": "yes"}, {"path": None, "on": True, "extra": 1}):
        assert http.put("/settings/ai/claude-code", json=body).status_code == 422


def test_claude_code_routes_need_the_secret(data_dir):
    from qsone.app import create_app

    app = TestClient(create_app("s3cret", data_dir=data_dir))
    assert app.get("/settings/ai/claude-code").status_code == 401
    assert app.put("/settings/ai/claude-code", json={"path": None, "on": True}).status_code == 401


def test_the_fake_is_never_the_real_claude():
    assert fake_claude_command()[0] == sys.executable
