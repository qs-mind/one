"""Task 1 of the agent engine: libraries, shared types, texts and test fakes."""

import asyncio
import json
import os
import re
import socket
import string
import subprocess
import sys
import time
from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest
from pydantic_ai import Agent

from qsone import copy
from qsone.engine import types
from qsone.engine.types import Card, ModelChoice, Progress, TeamHost, TeamMessage
from tests.engine_fakes import (
    SAMPLE_SHEET,
    FakeHost,
    call,
    calls,
    fake_claude_command,
    read_fake_log,
    scripted,
    text,
)

ENGINE_TEXTS = [
    "NO_AI",
    "AI_KEY_REFUSED",
    "AI_NO_CONNECTION",
    "AI_BUSY",
    "AI_FAILED",
    "FALLBACK_MOVED",
    "FALLBACK_COSTLIER",
    "WAITING_INTERNET",
    "CAP_PAUSED",
    "CAP_STOPPED",
    "SCOPE_BRIEF",
    "SCOPE_DAY",
    "SCOPE_MONTH",
    "EQUIVALENT_COST",
    "PRICE_UNKNOWN",
    "BUDGET_ASK",
    "BASIS_MEASURED",
    "BASIS_ASSUMED",
    "ASK_OUTSIDE",
    "ASK_ONLINE",
    "CONTINUE_BRIEF",
    "STOPPED",
    "STOPPED_NOTHING",
    "STOPPED_CHANGED",
    "DESK_SAVE",
    "DISAGREEMENT",
    "SAME_PROVIDER",
    "NO_SOURCE",
    "CLAUDE_CODE_MISSING",
    "CLAUDE_CODE_TOO_OLD",
    "CLAUDE_CODE_SHIM",
    "CLAUDE_CODE_SIGNED_OUT",
    "CLAUDE_CODE_LIMIT",
    "CLAUDE_CODE_COPY",
    "ROLE_LEAD",
    "ROLE_CHECKER",
    "ROLE_SPECIALIST",
    "ROLE_QUICK",
]


# Libraries ----------------------------------------------------------------------------------


def test_new_libraries_import():
    import genai_prices  # noqa: F401
    import mcp  # noqa: F401
    import openai  # noqa: F401
    from pydantic_ai.models.openai import OpenAIChatModel  # noqa: F401


def test_live_tests_are_off_by_default(pytestconfig):
    assert "not live" in pytestconfig.getini("addopts")
    assert any(m.startswith("live:") for m in pytestconfig.getini("markers"))


# The network guard --------------------------------------------------------------------------


def test_no_test_reaches_the_internet():
    with pytest.raises(OSError):
        socket.create_connection(("api.anthropic.com", 443), timeout=1)


def test_no_test_reaches_an_internet_address():
    with socket.socket() as s, pytest.raises(OSError):
        s.connect(("1.1.1.1", 443))


async def test_the_event_loop_cannot_reach_the_internet_either():
    with pytest.raises(OSError):
        await asyncio.open_connection("1.1.1.1", 443)


def test_loopback_still_works():
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        server.listen()
        with socket.create_connection(server.getsockname(), timeout=1):
            pass


# Texts --------------------------------------------------------------------------------------


def test_fill_puts_values_in_both_languages():
    t = copy.fill(copy.CAP_PAUSED, scope_name=copy.SCOPE_BRIEF, spent="2.41", cap="3.00")
    assert "2.41" in t["en"] and "3.00" in t["ar"] and "{" not in t["en"] + t["ar"]
    assert copy.SCOPE_BRIEF["en"] in t["en"] and copy.SCOPE_BRIEF["ar"] in t["ar"]


def test_every_engine_text_has_both_languages():
    for name in ENGINE_TEXTS:
        text_ = getattr(copy, name)
        assert set(text_) == {"en", "ar"}, name
        assert text_["en"].strip() and text_["ar"].strip(), name


def test_both_languages_need_the_same_values():
    for name in ENGINE_TEXTS:
        en, ar = (getattr(copy, name)[lang] for lang in ("en", "ar"))
        names = {f[1] for f in string.Formatter().parse(en) if f[1]}
        assert names == {f[1] for f in string.Formatter().parse(ar) if f[1]}, name
        filled = copy.fill(getattr(copy, name), **{n: "7" for n in names})
        assert "{" not in filled["en"] + filled["ar"], name


def test_engine_texts_use_the_glossary_words():
    assert "Spending Cap" in copy.CAP_PAUSED["en"] and "سقف الصرف" in copy.CAP_PAUSED["ar"]
    assert copy.ROLE_LEAD == {"en": "Lead QS", "ar": "كبير مهندسي الكميات"}
    assert copy.ROLE_CHECKER == {"en": "Checking QS", "ar": "مهندس المراجعة"}
    assert "Draft Desk" in copy.DESK_SAVE["en"] and "قسم مسودة" in copy.DESK_SAVE["ar"]


# Shared types -------------------------------------------------------------------------------


def test_types_do_not_import_pydantic_ai():
    source = open(types.__file__, encoding="utf-8").read()
    assert "pydantic_ai" not in source


def test_types_are_frozen():
    choice = ModelChoice("anthropic", "claude-opus-5-5")
    with pytest.raises(FrozenInstanceError):
        choice.model = "other"  # type: ignore[misc]
    assert {choice, ModelChoice("anthropic", "claude-opus-5-5")} == {choice}


def test_every_event_has_a_brief_id():
    for event in types.Event.__args__:
        assert "brief_id" in event.__dataclass_fields__, event


def test_fake_host_is_a_team_host():
    assert isinstance(FakeHost(), TeamHost)


# Sample Model Data Sheet ---------------------------------------------------------------------


def test_sample_sheet_is_labelled_sample():
    assert {c.provider for c in SAMPLE_SHEET} == {"anthropic", "deepseek"}
    for card in SAMPLE_SHEET:
        assert "sample" in card.name and "sample" in card.price_source
        assert isinstance(card.price_in, Decimal) and isinstance(card.price_out, Decimal)


# Scripted models ----------------------------------------------------------------------------


async def test_scripted_model_plays_its_steps_and_records_them():
    model = scripted(call("add", {"a": "1", "b": "2"}), text("تمام، الناتج 3 - عينة"))
    agent = Agent(model)

    @agent.tool_plain
    def add(a: str, b: str) -> str:
        return str(int(a) + int(b))

    result = await agent.run("اجمع - عينة")
    assert result.output == "تمام، الناتج 3 - عينة"
    assert model.calls == 2 and len(model.seen) == 2
    assert "اجمع - عينة" in json.dumps(model.seen[0], ensure_ascii=False, default=str)
    assert "'3'" in repr(model.seen[1]) or '"3"' in repr(model.seen[1])


async def test_scripted_model_streams_and_keeps_its_usage():
    model = scripted(text("مرحبا", usage=(1200, 80)))
    async with Agent(model).run_stream("hello") as run:
        out = await run.get_output()
        usage = run.usage
    assert out == "مرحبا" and model.calls == 1
    assert (usage.input_tokens, usage.output_tokens) == (1200, 80)
    result = await Agent(scripted(text("مرحبا", usage=(1200, 80)))).run("hello")
    assert (result.usage.input_tokens, result.usage.output_tokens) == (1200, 80)


async def test_scripted_model_makes_several_calls_in_one_response():
    model = scripted(calls(call("ping", {"n": 1}), call("ping", {"n": 2})), text("done"))
    agent = Agent(model)
    seen: list[int] = []

    @agent.tool_plain
    def ping(n: int) -> str:
        seen.append(n)
        return "pong"

    assert (await agent.run("go")).output == "done"
    assert sorted(seen) == [1, 2]


async def test_scripted_model_marks_cancelled():
    entered = asyncio.Event()

    async def wait_forever(messages, info):
        entered.set()
        await asyncio.sleep(60)

    model = scripted(wait_forever)
    task = asyncio.create_task(Agent(model).run("go"))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert model.cancelled


async def test_scripted_model_says_when_it_runs_out():
    with pytest.raises(AssertionError, match="no step"):
        await Agent(scripted()).run("go")


# FakeHost -----------------------------------------------------------------------------------


async def test_fake_host_records_events_and_answers_cards():
    host = FakeHost(answers={"cap": "continue"})
    host.emit(Progress(host.brief_id, "r1", copy.ROLE_LEAD, {"en": "reading", "ar": "بيقرا"}))
    card = Card("c1", "cap", copy.SCOPE_BRIEF, copy.STOPPED, ("continue", "raise", "report"))
    assert await host.ask(card) == "continue"
    assert host.cards == [card] and len(host.events) == 1


async def test_fake_host_waits_for_an_unanswered_card():
    host = FakeHost()
    card = Card("c2", "outside", copy.SCOPE_BRIEF, copy.STOPPED, ("yes", "no"))
    waiting = asyncio.create_task(host.ask(card))
    await asyncio.sleep(0)
    assert not waiting.done() and host.cards == [card]
    host.settle("c2", "no")
    assert await waiting == "no"


def test_fake_host_posts_team_messages():
    host = FakeHost()
    message = TeamMessage(host.brief_id, "m1", copy.ROLE_LEAD, copy.ROLE_SPECIALIST, "ابدأ - عينة")
    host.post(message)
    assert host.posted == [message] and host.events == [message]


# Fake clock and sleep -----------------------------------------------------------------------


async def test_fake_sleep_records_and_moves_the_clock(fake_clock, fake_sleep):
    start = fake_clock()
    await fake_sleep(5)
    await fake_sleep(15)
    assert fake_sleep.delays == [5, 15]
    assert (fake_clock() - start).total_seconds() == 20


# Records fixtures ---------------------------------------------------------------------------


def test_rec_and_general_are_open_and_separate(rec, general, data_dir):
    assert rec.is_open and general.is_open and rec.id != general.id
    assert general.folder == data_dir / "engineer"
    assert rec.folder.parent == data_dir / "projects"


# The fake `claude` --------------------------------------------------------------------------


def run_fake(args, *, script=None, stdin_lines=(), env=None, timeout=20):
    env = {**os.environ, **(env or {})}
    if script is not None:
        env["FAKE_CLAUDE_SCRIPT"] = json.dumps(script)
    stdin = "".join(json.dumps(line) + "\n" for line in stdin_lines)
    return subprocess.run(
        [*fake_claude_command(), *args],
        input=stdin,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=timeout,
    )


def user_line(text_: str) -> dict:
    return {
        "type": "user",
        "message": {"role": "user", "content": [{"type": "text", "text": text_}]},
    }


PRINT = ["-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose"]


def out_lines(proc) -> list[dict]:
    return [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]


def test_fake_claude_help_lists_the_flags_one_needs():
    help_ = run_fake(["--help"]).stdout
    for flag in ["--strict-mcp-config", "--system-prompt-file", "--include-partial-messages"]:
        assert flag in help_
    assert re.search(r"--model .*'opus'", help_)
    dropped = run_fake(["--help"], env={"FAKE_CLAUDE_DROP": "--strict-mcp-config"}).stdout
    assert "--strict-mcp-config" not in dropped and "--mcp-config" in dropped


def test_fake_claude_version_and_sign_in():
    assert run_fake(["--version"]).stdout.strip() == "2.1.318 (Claude Code)"
    assert "status" in run_fake(["auth", "--help"]).stdout
    assert json.loads(run_fake(["auth", "status"]).stdout) == {"loggedIn": True}
    out = run_fake(["auth", "status"], env={"FAKE_CLAUDE_SIGNED_OUT": "1"})
    assert json.loads(out.stdout) == {"loggedIn": False} and out.returncode == 1


def test_fake_claude_speaks_stream_json():
    proc = run_fake(
        PRINT, script=["init", {"text": "أهلاً - عينة"}, "result"], stdin_lines=[user_line("hi")]
    )
    assert proc.returncode == 0, proc.stderr
    lines = out_lines(proc)
    assert [(x["type"], x.get("subtype")) for x in lines] == [
        ("system", "init"),
        ("assistant", None),
        ("result", "success"),
    ]
    session = lines[0]["session_id"]
    assert lines[1]["message"]["content"] == [{"type": "text", "text": "أهلاً - عينة"}]
    assert lines[2]["result"] == "أهلاً - عينة" and lines[2]["session_id"] == session


def test_fake_claude_streams_partial_messages_and_usage():
    script = [
        "init",
        {"usage": [1200, 80]},
        {"text": ["مر", "حبا"], "id": "msg_a"},
        {"text": "مرحبا", "id": "msg_a"},  # a replayed message: same id
        {"result": {"cost": "0.0123"}},
    ]
    proc = run_fake(
        [*PRINT, "--include-partial-messages"], script=script, stdin_lines=[user_line("hi")]
    )
    lines = out_lines(proc)
    deltas = [
        x["event"]["delta"]["text"]
        for x in lines
        if x["type"] == "stream_event" and x["event"]["type"] == "content_block_delta"
    ]
    assert deltas[:2] == ["مر", "حبا"]
    assistants = [x for x in lines if x["type"] == "assistant"]
    assert {a["message"]["id"] for a in assistants} == {"msg_a"}
    assert assistants[0]["message"]["usage"]["input_tokens"] == 1200
    assert lines[-1]["total_cost_usd"] == 0.0123


def test_fake_claude_logs_argv_env_names_and_stdin(tmp_path, monkeypatch):
    log = tmp_path / "fake.log"
    monkeypatch.setenv("SOME_SECRET_FOR_TEST", "never-logged")
    proc = run_fake(
        [*PRINT, "--resume", "8f0c7c1e-4c1e-4a59-9a43-1d2b8c3e5f60"],
        script=["init", "result"],
        stdin_lines=[user_line("سعّر - عينة")],
        env={"FAKE_CLAUDE_LOG": str(log)},
    )
    assert out_lines(proc)[0]["session_id"] == "8f0c7c1e-4c1e-4a59-9a43-1d2b8c3e5f60"
    [run] = read_fake_log(log)
    assert run["argv"][-1] == "8f0c7c1e-4c1e-4a59-9a43-1d2b8c3e5f60"
    assert "SOME_SECRET_FOR_TEST" in run["env_names"]
    assert "never-logged" not in log.read_text(encoding="utf-8")
    assert run["stdin"] == [user_line("سعّر - عينة")]


def test_fake_claude_plays_one_script_per_run(tmp_path):
    log = tmp_path / "fake.log"
    cut_off = ["init", {"text": "a", "stop_reason": "max_tokens"}, "result"]
    script = {"runs": [cut_off, ["init", {"text": "b"}, "result"]]}
    env = {"FAKE_CLAUDE_LOG": str(log)}
    first = run_fake(PRINT, script=script, stdin_lines=[user_line("x")], env=env)
    second = run_fake(PRINT, script=script, stdin_lines=[user_line("x")], env=env)
    assert out_lines(first)[-1]["stop_reason"] == "max_tokens"
    assert out_lines(second)[-1]["result"] == "b" and len(read_fake_log(log)) == 2


def test_fake_claude_drop_error_and_unknown_tool():
    dropped = run_fake(PRINT, script=["init", "drop"], stdin_lines=[user_line("x")])
    assert dropped.returncode != 0 and "result" not in proc_types(dropped)
    limited = run_fake(
        PRINT, script=["init", {"error": "rate_limit"}, "result"], stdin_lines=[user_line("x")]
    )
    retry = [x for x in out_lines(limited) if x.get("subtype") == "api_retry"]
    assert retry[0]["error"] == "rate_limit" and retry[0]["error_status"] == 429
    tool = run_fake(
        PRINT, script=["init", {"tool_use": {"name": "Bash"}}], stdin_lines=[user_line("x")]
    )
    blocks = [
        b for x in out_lines(tool) if x["type"] == "assistant" for b in x["message"]["content"]
    ]
    assert blocks[0]["type"] == "tool_use" and blocks[0]["name"] == "Bash"


def proc_types(proc) -> list[str]:
    return [x["type"] for x in out_lines(proc)]


def start_fake(args, script, env=None):
    proc = subprocess.Popen(
        [*fake_claude_command(), *args],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        env={**os.environ, "FAKE_CLAUDE_SCRIPT": json.dumps(script), **(env or {})},
    )
    proc.stdin.write(json.dumps(user_line("x")) + "\n")
    proc.stdin.flush()
    assert json.loads(proc.stdout.readline())["subtype"] == "init"
    return proc


def test_fake_claude_stops_on_an_interrupt_line():
    proc = start_fake(PRINT, ["init", {"sleep": 60}, "result"])
    started = time.monotonic()
    interrupt = {"type": "control_request", "request_id": "r1", "request": {"subtype": "interrupt"}}
    proc.stdin.write(json.dumps(interrupt) + "\n")
    proc.stdin.flush()
    assert proc.wait(timeout=10) == 0 and time.monotonic() - started < 10
    reply = json.loads(proc.stdout.readline())
    assert reply["type"] == "control_response" and reply["response"]["request_id"] == "r1"


def test_fake_claude_stops_on_terminate():
    proc = start_fake(PRINT, ["init", {"sleep": 60}, "result"])
    started = time.monotonic()
    proc.terminate()
    proc.wait(timeout=10)
    assert time.monotonic() - started < 10
    if sys.platform != "win32":
        assert proc.returncode == 0  # a clean exit on SIGTERM


def test_fake_claude_steer_line_is_logged(tmp_path):
    log = tmp_path / "fake.log"
    proc = start_fake(PRINT, ["init", {"sleep": 0.5}, "result"], env={"FAKE_CLAUDE_LOG": str(log)})
    proc.stdin.write(json.dumps(user_line("steer - عينة")) + "\n")
    proc.stdin.flush()
    proc.stdin.close()
    assert proc.wait(timeout=10) == 0
    assert read_fake_log(log)[0]["stdin"][-1] == user_line("steer - عينة")


def test_fake_claude_calls_one_through_mcp(tmp_path, serve_app):
    from mcp.server.mcpserver import MCPServer

    server = MCPServer("one")
    seen_auth: list[str] = []

    @server.tool()
    def search_records(query: str) -> str:
        """Search - sample."""
        return f"found: {query}"

    inner = server.streamable_http_app()

    async def app(scope, receive, send):
        if scope["type"] == "http":
            seen_auth.append(dict(scope["headers"]).get(b"authorization", b"").decode())
        await inner(scope, receive, send)

    url = serve_app(app) + "/mcp"
    one = {"type": "http", "url": url, "headers": {"Authorization": "Bearer run-token"}}
    config = {"mcpServers": {"one": one}}
    (tmp_path / "mcp.json").write_text(json.dumps(config), encoding="utf-8")
    script = ["init", {"mcp_call": {"tool": "search_records", "args": {"query": "عزل"}}}, "result"]
    proc = run_fake(
        [*PRINT, "--mcp-config", str(tmp_path / "mcp.json")],
        script=script,
        stdin_lines=[user_line("x")],
    )
    assert proc.returncode == 0, proc.stderr
    lines = out_lines(proc)
    [use] = [b for x in lines if x["type"] == "assistant" for b in x["message"]["content"]]
    assert use["name"] == "mcp__one__search_records" and use["input"] == {"query": "عزل"}
    [result] = [b for x in lines if x["type"] == "user" for b in x["message"]["content"]]
    assert result["tool_use_id"] == use["id"] and not result["is_error"]
    assert "found: عزل" in result["content"][0]["text"]
    assert seen_auth and set(seen_auth) == {"Bearer run-token"}


def test_fake_claude_refuses_an_internet_mcp_url(tmp_path):
    config = {"mcpServers": {"one": {"type": "http", "url": "https://example.com/mcp"}}}
    (tmp_path / "mcp.json").write_text(json.dumps(config), encoding="utf-8")
    script = ["init", {"mcp_call": {"tool": "x", "args": {}}}, "result"]
    proc = run_fake(
        [*PRINT, "--mcp-config", str(tmp_path / "mcp.json")],
        script=script,
        stdin_lines=[user_line("x")],
    )
    assert proc.returncode != 0 and "loopback" in proc.stderr


def test_fake_claude_takes_its_settings_as_arguments_when_the_env_is_cleared(tmp_path):
    # One clears the environment it gives Claude Code, so tests pass the script as arguments.
    log = tmp_path / "fake.log"
    command = fake_claude_command(script=["init", {"text": "تمام"}, "result"], log=log)
    keep = {k: v for k, v in os.environ.items() if k in ("PATH", "SYSTEMROOT", "SystemRoot")}
    proc = subprocess.run(
        [*command, *PRINT],
        input=json.dumps(user_line("x")) + "\n",
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=keep,
        timeout=20,
    )
    assert out_lines(proc)[-1]["result"] == "تمام", proc.stderr
    [run] = read_fake_log(log)
    assert run["argv"] == PRINT and run["ended"] == "done"
    assert not any(a.startswith("--fake-") for a in run["argv"])


def test_fake_claude_refuses_an_unknown_flag():
    proc = run_fake([*PRINT, "--bare"], script=["init"], stdin_lines=[user_line("x")])
    assert proc.returncode == 1 and "unknown option '--bare'" in proc.stderr
