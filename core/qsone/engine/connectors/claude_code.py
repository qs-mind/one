"""The Subscription Link: the engineer's own installed Claude Code, with their own subscription.

One drives the `claude` CLI through its documented flags (decision 4) and gives it only One's
instructions and One's tools, over MCP at `/mcp` with a token for each run:

- built-in tools off (`--tools ""`), user and project settings and hooks off, only the MCP
  server in the config One writes, and only One's tools allowed;
- the environment cleared to ordinary variables, so no `ANTHROPIC_*` variable reaches it and
  Claude Code uses its own sign-in, which One never handles, reads or copies;
- stderr discarded; One never logs stdout lines, argv or the instructions;
- every flag checked in `--help` before use; an npm `claude.cmd` shim is refused, because
  quoting through `cmd.exe` is unsafe.

`status` runs only when the engineer asks (no timer, no polling) and never asks a model
anything. Claude Code keeps its own copy of each conversation on this computer (that copy makes
`--resume` work); `keep_copy=False` passes `--no-session-persistence` instead, and then nothing
is resumed.

The process is `subprocess.Popen` with a reader thread that feeds an asyncio queue, so it works
on any event loop, uvicorn's on Windows too.
"""

import asyncio
import json
import logging
import os
import re
import subprocess
import sys
import threading
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Literal

from genai_prices import data_snapshot
from genai_prices.types import TieredPrices

from qsone import copy, settings
from qsone.engine.cards import GENAI
from qsone.engine.mcp_server import NAME as MCP_NAME
from qsone.engine.mcp_server import McpGate
from qsone.engine.tools import REGISTRY
from qsone.engine.types import AgentSpec, Event, ModelCard, ModelChoice, Progress, Text, TextDelta

log = logging.getLogger("qsone.engine.claude_code")

ID = "claude-code"
WINDOWS = sys.platform == "win32"
SHIM_SUFFIXES = (".cmd", ".bat", ".ps1")

# Decision 4: every one must be listed in `--help`, plus one of PROMPT_FLAGS.
REQUIRED = (
    "--print",
    "--input-format",
    "--output-format",
    "--verbose",
    "--include-partial-messages",
    "--tools",
    "--strict-mcp-config",
    "--mcp-config",
    "--setting-sources",
    "--settings",
    "--permission-mode",
    "--allowedTools",
    "--disallowedTools",
    "--model",
    "--resume",
)
PROMPT_FLAGS = ("--system-prompt-file", "--append-system-prompt-file")
# Claude Code's own tools, denied on top of `--tools ""`.
BUILT_IN = (
    "Bash,Edit,MultiEdit,Write,Read,Glob,Grep,WebFetch,WebSearch,Agent,Task,NotebookEdit,"
    "TodoWrite,Skill"
)
# Ordinary variables only: never a key, a base URL or anything that changes how it signs in.
ENV_NAMES = (
    "PATH",
    "PATHEXT",
    "HOME",
    "USER",
    "LOGNAME",
    "SHELL",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "XDG_CONFIG_HOME",
    "XDG_DATA_HOME",
    "XDG_RUNTIME_DIR",
    "DBUS_SESSION_BUS_ADDRESS",
    "SYSTEMROOT",
    "WINDIR",
    "USERPROFILE",
    "APPDATA",
    "LOCALAPPDATA",
    "HOMEDRIVE",
    "HOMEPATH",
    "TMP",
    "TEMP",
    "TMPDIR",
)
MCP_TOOL_TIMEOUT = "3600000"  # one hour, so a long `delegate` does not time out

MCP_FILE = "mcp.json"
INSTRUCTIONS_FILE = "instructions.txt"
CONTINUE = "Continue from where you stopped."  # after a cut-off answer; the model reads it
TOOL_PREFIX = f"mcp__{MCP_NAME}__"

CHECK_TIMEOUT = 10  # seconds, for --help, --version and auth status
CHECK_LIMIT = 256 * 1024  # bytes of output kept from each
LINE_LIMIT = 32 * 1024 * 1024  # one stream-json line
STOP_WAIT = 5  # seconds after the interrupt, and again after terminate

_OPTION = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,99}")
_VERSION = re.compile(r"[0-9][0-9.]{0,31}")

Ended = Literal["done", "max_tokens", "stopped", "dropped", "limit", "signed_out", "failed"]
_ERRORS: dict[str, Ended] = {"rate_limit": "limit", "authentication_failed": "signed_out"}


@dataclass(frozen=True)
class ClaudeCodeStatus:
    installed: bool
    compatible: bool
    signed_in: bool | None
    version: str | None
    code: str | None  # name of a copy.py text, e.g. "CLAUDE_CODE_TOO_OLD"
    models: tuple[str, ...]  # aliases from --model's help, e.g. ("opus", "sonnet")


@dataclass(frozen=True)
class AgentJob:
    run_id: str
    brief_id: str
    spec: AgentSpec
    task: str
    model: str | None  # an alias or a full model id; None lets Claude Code choose
    mcp_url: str
    mcp_token: str
    tools: tuple[str, ...]
    cwd: Path  # <data>/claude-work/<run id>/, the same folder again for --resume
    resume: str | None  # a session id


@dataclass(frozen=True)
class AgentOutcome:
    text: str
    session_id: str | None
    ended: Ended
    usage: tuple[tuple[str, int, int], ...]  # per assistant message id: input, output tokens
    reported_usd: Decimal | None  # the result line's total cost, when given


def saved() -> dict:
    """settings.json "ai.claude_code": {"path": str | None, "on": bool, "keep_copy": bool}."""
    entry = settings.ai().get("claude_code")
    entry = entry if isinstance(entry, dict) else {}
    path = entry.get("path")
    return {
        "path": path if isinstance(path, str) and path.strip() else None,
        "on": entry.get("on") is True,
        "keep_copy": entry.get("keep_copy") is not False,  # pending founder question 3
    }


def save(*, path: str | None, on: bool, keep_copy: bool | None = None) -> dict:
    """Raises `OSError` when settings.json cannot be written."""
    entry = {
        "path": path.strip() if path and path.strip() else None,
        "on": on,
        "keep_copy": saved()["keep_copy"] if keep_copy is None else keep_copy,
    }
    settings.save_ai("claude_code", entry)
    return entry


# Finding and checking the executable ----------------------------------------------------------


def _runnable(path: Path) -> bool:
    if not path.is_file():
        return False
    return WINDOWS or os.access(path, os.X_OK)


def executable(picked: str | None) -> tuple[Path | None, str | None]:
    """The file to run, or the name of the copy.py text that says why there is none.

    Only the file the engineer picked (an absolute path) or PATH: One never installs Claude
    Code or looks in its folders."""
    if picked and picked.strip():
        path = Path(picked.strip())
        if path.suffix.lower() in SHIM_SUFFIXES:
            return None, "CLAUDE_CODE_SHIM"
        if not path.is_absolute() or not _runnable(path):
            return None, "CLAUDE_CODE_MISSING"
        return path, None
    shim = False
    for folder in os.environ.get("PATH", "").split(os.pathsep):
        if not folder or not Path(folder).is_absolute():
            continue
        candidate = Path(folder) / ("claude.exe" if WINDOWS else "claude")
        if _runnable(candidate):
            return candidate, None
        shim = shim or (WINDOWS and (Path(folder) / "claude.cmd").is_file())
    return None, "CLAUDE_CODE_SHIM" if shim else "CLAUDE_CODE_MISSING"


def _env() -> dict[str, str]:
    env = {name: os.environ[name] for name in ENV_NAMES if name in os.environ}
    return env | {"MCP_TOOL_TIMEOUT": MCP_TOOL_TIMEOUT}


_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)  # Windows: no console pops up


def _output(command: Sequence[str], args: Sequence[str], *, any_exit: bool = False) -> str | None:
    """Its stdout, or None when it fails, runs over CHECK_TIMEOUT or prints over CHECK_LIMIT."""
    try:
        process = subprocess.Popen(
            [*command, *args],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=_env(),
            creationflags=_NO_WINDOW,
        )
    except OSError:
        return None
    timer = threading.Timer(CHECK_TIMEOUT, process.kill)
    timer.start()
    try:
        assert process.stdout is not None
        data = process.stdout.read(CHECK_LIMIT + 1)
        if len(data) > CHECK_LIMIT:
            process.kill()
        code = process.wait()
    finally:
        timer.cancel()
        if process.stdout is not None:
            process.stdout.close()
    if len(data) > CHECK_LIMIT or (code != 0 and not any_exit):
        return None
    return data.decode("utf-8", "replace")


def has(help_text: str, flag: str) -> bool:
    return flag in re.split(r"[\s,=\[\]]+", help_text)


def _about(help_text: str, flag: str) -> str:
    """The help lines that describe `flag`."""
    lines, matching = [], False
    for line in help_text.splitlines():
        trimmed = line.strip()
        if trimmed.startswith("-"):
            matching = flag in (word.rstrip(",") for word in trimmed.split())
        elif not trimmed or not line[:1].isspace():
            matching = False
        if matching:
            lines.append(trimmed)
    return " ".join(lines)


def model_aliases(help_text: str) -> tuple[str, ...]:
    """The aliases in --model's own example: "(e.g. 'opus' or 'sonnet')"."""
    _, found, examples = _about(help_text, "--model").partition("e.g.")
    if not found:
        return ()
    aliases: list[str] = []
    for quoted in re.findall(r"['\"`]([^'\"`]*)['\"`]", examples.split(")")[0]):
        if _OPTION.fullmatch(quoted) and quoted not in aliases:
            aliases.append(quoted)
    return tuple(aliases)


def compatible(help_text: str) -> bool:
    return (
        all(has(help_text, flag) for flag in REQUIRED)
        and "dontAsk" in help_text
        and any(has(help_text, flag) for flag in PROMPT_FLAGS)
    )


_HELP: dict[tuple[str, ...], str] = {}  # the last --help of each command, from a check or a run


async def _help(command: tuple[str, ...], *, fresh: bool = False) -> str | None:
    if fresh or command not in _HELP:
        found = await asyncio.to_thread(_output, command, ["--help"])
        if found is None:
            _HELP.pop(command, None)
            return None
        _HELP[command] = found
    return _HELP[command]


def _command(path: str | None, prefix: Sequence[str]) -> tuple[tuple[str, ...] | None, str | None]:
    if prefix:  # tests: [python, fake_claude.py, --fake-…]
        return tuple(prefix), None
    found, code = executable(path)
    return (None, code) if found is None else ((str(found),), None)


async def status(path: str | None, *, command_prefix: Sequence[str] = ()) -> ClaudeCodeStatus:
    """The engineer's Check button: free, asks no model, signs nothing in."""
    command, code = _command(path, command_prefix)
    if command is None:
        return ClaudeCodeStatus(False, False, None, None, code, ())
    help_text = await _help(command, fresh=True)
    if help_text is None:
        return ClaudeCodeStatus(True, False, None, None, "AI_FAILED", ())
    printed = await asyncio.to_thread(_output, command, ["--version"]) or ""
    words = printed.split()
    version = words[0] if words and _VERSION.fullmatch(words[0]) else None
    signed_in = None
    if any(line.strip().startswith("auth") for line in help_text.splitlines()):
        auth = await asyncio.to_thread(_output, command, ["auth", "--help"]) or ""
        if any(line.strip().startswith("status") for line in auth.splitlines()):
            said = await asyncio.to_thread(_output, command, ["auth", "status"], any_exit=True)
            try:
                logged_in = json.loads(said or "").get("loggedIn")
            except (ValueError, AttributeError):
                logged_in = None
            signed_in = logged_in if isinstance(logged_in, bool) else None
    fits = compatible(help_text)
    code = None if fits else "CLAUDE_CODE_TOO_OLD"
    if fits and signed_in is False:
        code = "CLAUDE_CODE_SIGNED_OUT"
    log.info("Claude Code checked: version %s, compatible %s", version, fits)
    return ClaudeCodeStatus(True, fits, signed_in, version, code, model_aliases(help_text))


# Pricing the aliases -------------------------------------------------------------------------


def _priced_as(alias: str) -> tuple[str, Decimal, Decimal, str] | None:
    """genai-prices' newest Claude model of the alias's family, its prices and source."""
    family = re.compile(rf"claude-{re.escape(alias)}-([0-9]+)(?:-([0-9]+))?")
    try:
        provider = data_snapshot.get_snapshot().find_provider(None, "anthropic", None)
    except LookupError:
        return None
    newest = None
    for model in provider.models:
        match = family.fullmatch(model.id)
        if match:
            version = (int(match[1]), int(match[2] or 0))
            if newest is None or version > newest[0]:
                newest = (version, model)
    if newest is None:
        return None
    model = newest[1]
    price = model.get_prices(datetime.now(UTC))
    price_in, price_out = (
        p.base if isinstance(p, TieredPrices) else p for p in (price.input_mtok, price.output_mtok)
    )
    if not isinstance(price_in, Decimal) or not isinstance(price_out, Decimal):
        return None
    url = (provider.pricing_urls or [None])[0]
    source = f"{GENAI}: {url}" if url else GENAI
    return model.id, price_in, price_out, f"{source}, as {model.id}"


# The connector -------------------------------------------------------------------------------


class _Process:
    """One running `claude -p`: its stdin is kept open for steering and the interrupt."""

    def __init__(self, process: subprocess.Popen) -> None:
        self.process = process
        self.stopping = False
        self._lock = threading.Lock()

    def send(self, line: dict) -> bool:
        with self._lock:
            stdin = self.process.stdin
            if stdin is None or stdin.closed:
                return False
            try:
                stdin.write((json.dumps(line, ensure_ascii=False) + "\n").encode("utf-8"))
                stdin.flush()
            except (OSError, ValueError):
                return False
            return True

    def close_stdin(self) -> None:
        with self._lock:
            try:
                if self.process.stdin is not None:
                    self.process.stdin.close()
            except OSError:
                pass

    def halt(self) -> None:
        """Interrupt, then terminate after STOP_WAIT, then kill after STOP_WAIT more."""
        self.send(
            {
                "type": "control_request",
                "request_id": uuid.uuid4().hex,
                "request": {"subtype": "interrupt"},
            }
        )
        self.close_stdin()
        self.reap()

    def reap(self) -> None:
        for end in (None, self.process.terminate, self.process.kill):
            if end is not None:
                try:
                    end()
                except OSError:
                    pass
            try:
                self.process.wait(STOP_WAIT)
                return
            except subprocess.TimeoutExpired:
                continue
        self.process.wait()


def _user_line(text: str) -> dict:
    return {
        "type": "user",
        "message": {"role": "user", "content": [{"type": "text", "text": text}]},
    }


def _private_file(path: Path, text: str) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)


def _prepare(cwd: Path) -> None:
    """The run's own folder: not a symlink, 0700, and holding nothing but One's two files."""
    if cwd.is_symlink():
        raise OSError(f"{cwd.name} is a symlink")
    cwd.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.name == "posix":
        cwd.chmod(0o700)
    for name in (MCP_FILE, INSTRUCTIONS_FILE):  # left by a crash
        (cwd / name).unlink(missing_ok=True)
    if any(cwd.iterdir()):
        raise OSError(f"{cwd.name} is not empty")


def _short(text: str, limit: int = 200) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _session(value: object) -> str | None:
    try:
        return str(uuid.UUID(str(value))) if value else None
    except ValueError:
        return None


class _Stream:
    """Reads one process's stream-json lines into events, usage and how it ended."""

    def __init__(self, job: AgentJob, sink: Callable[[Event], None], usage: dict) -> None:
        self.job = job
        self.sink = sink
        self.usage = usage  # message id -> (input, output), shared across one job's processes
        self.earlier = set(usage)  # ids seen by an earlier process: replayed, so not shown again
        self.allowed = {TOOL_PREFIX + name for name in job.tools}
        self.session: str | None = None
        self.version: str | None = None
        self.result: dict | None = None
        self.verdict: Ended | None = None  # a refused tool, the limit or signed out: ended early
        self.stop_reason: str | None = None
        self.text: list[str] = []
        self._message: str | None = None
        self._streamed: set[str] = set()
        self._blocks: dict[int, dict] = {}
        self._tools: set[str] = set()

    def read(self, value: dict) -> Ended | None:
        """How the run must end now (a refused tool, the limit, signed out), or None."""
        kind = value.get("type")
        if kind == "system" and value.get("subtype") == "init":
            self.session = _session(value.get("session_id")) or self.session
            version = value.get("claude_code_version")
            self.version = (
                version if isinstance(version, str) and _VERSION.fullmatch(version) else None
            )
        elif kind == "system" and value.get("subtype") == "api_retry":
            return _ERRORS.get(str(value.get("error")))
        elif kind == "stream_event":
            return self._event(value.get("event") or {})
        elif kind == "assistant":
            return self._assistant(value)
        elif kind == "result":
            self.result = value
            self.session = _session(value.get("session_id")) or self.session
        return None

    def _replayed(self, message_id: str | None) -> bool:
        return message_id in self.earlier

    def _event(self, event: dict) -> Ended | None:
        kind = event.get("type")
        if kind == "message_start":
            self._message = (event.get("message") or {}).get("id")
            self._blocks.clear()
        if self._replayed(self._message):
            return None
        if kind == "content_block_start":
            block = event.get("content_block") or {}
            if block.get("type") == "tool_use":
                if block.get("name") not in self.allowed:
                    return "failed"
                self._blocks[event.get("index")] = {"block": block, "json": ""}
        elif kind == "content_block_delta":
            delta = event.get("delta") or {}
            if delta.get("type") == "text_delta" and isinstance(delta.get("text"), str):
                if self._message:
                    self._streamed.add(self._message)
                self._say(delta["text"])
            elif delta.get("type") == "input_json_delta" and event.get("index") in self._blocks:
                self._blocks[event["index"]]["json"] += str(delta.get("partial_json", ""))
        elif kind == "content_block_stop":
            partial = self._blocks.pop(event.get("index"), None)
            if partial is not None:
                try:
                    args = json.loads(partial["json"]) if partial["json"] else {}
                except ValueError:
                    args = {}
                block = partial["block"]
                self._tool(str(block.get("id")), str(block.get("name")), args)
        return None

    def _assistant(self, value: dict) -> Ended | None:
        error = value.get("error")
        if error in _ERRORS:
            return _ERRORS[error]
        message = value.get("message") or {}
        message_id = message.get("id")
        if isinstance(message.get("stop_reason"), str):
            self.stop_reason = message["stop_reason"]
        replayed = self._replayed(message_id)
        if isinstance(message_id, str):
            u = message.get("usage") or {}
            tokens_in = sum(
                int(u.get(name) or 0)
                for name in (
                    "input_tokens",
                    "cache_read_input_tokens",
                    "cache_creation_input_tokens",
                )
            )
            self.usage[message_id] = (tokens_in, int(u.get("output_tokens") or 0))
        texts = []
        for block in message.get("content") or ():
            if block.get("type") == "tool_use":
                if block.get("name") not in self.allowed:
                    return "failed"
                if not replayed:
                    self._tool(str(block.get("id")), str(block["name"]), block.get("input") or {})
            elif block.get("type") == "text" and isinstance(block.get("text"), str):
                texts.append(block["text"])
        if replayed or not texts:
            return None
        if message_id not in self._streamed:
            for text in texts:
                self._say(text)
        if self.job.spec.role != "lead":
            said = _short("".join(texts))
            self._progress({"en": said, "ar": said})
        return None

    def _say(self, text: str) -> None:
        self.text.append(text)
        if self.job.spec.role == "lead":
            self.sink(TextDelta(self.job.brief_id, text))

    def _tool(self, tool_id: str, name: str, args: object) -> None:
        if tool_id in self._tools:
            return
        self._tools.add(tool_id)
        tool = REGISTRY.get(name.removeprefix(TOOL_PREFIX))
        words = copy.fill(copy.TOOL_WORKING, tool=name.removeprefix(TOOL_PREFIX))
        if tool is not None:
            try:
                words = tool.activity(tool.args.model_validate(args))
            except Exception:  # noqa: BLE001 - its own words are only for the Progress Line
                pass
        self._progress(words)

    def _progress(self, text: Text) -> None:
        job = self.job
        self.sink(Progress(job.brief_id, job.run_id, job.spec.name, text))

    def ended(self, stopping: bool) -> Ended:
        if self.verdict is not None:
            return self.verdict
        result = self.result
        if result is None:
            return "stopped" if stopping else "dropped"
        if result.get("is_error") or result.get("subtype") != "success":
            if stopping:
                return "stopped"
            return _ERRORS.get(str(result.get("error")), "failed")
        reason = result.get("stop_reason") or self.stop_reason
        return "max_tokens" if reason in ("max_tokens", "max_output_tokens") else "done"

    def answer(self) -> str:
        said = self.result.get("result") if self.result else None
        return said if isinstance(said, str) else "".join(self.text)

    def cost(self) -> Decimal | None:
        value = self.result.get("total_cost_usd") if self.result else None
        if isinstance(value, bool) or not isinstance(value, int | float | str):
            return None
        try:
            return Decimal(str(value))
        except InvalidOperation:
            return None


_EOF = object()
_OVERSIZE = object()


class ClaudeCodeConnector:
    """Kind "agent": Claude Code runs its own loop over One's tools through MCP."""

    id = ID
    kind: Literal["agent"] = "agent"
    name = "Claude Code"
    provider = "anthropic"
    on_device = False

    def __init__(
        self,
        path: str | None,
        *,
        command_prefix: Sequence[str] = (),
        keep_copy: bool = True,
        gate: McpGate | None = None,
    ) -> None:
        """`command_prefix` replaces the executable (tests: the fake `claude`). `gate`, when
        given, has each job's MCP token revoked as soon as the job ends."""
        self.path = path
        self.keep_copy = keep_copy
        self._prefix = tuple(command_prefix)
        self._gate = gate
        self._runs: dict[str, _Process] = {}
        self._stopping: set[str] = set()  # runs the engineer stopped

    async def _ready(self) -> tuple[tuple[str, ...], str] | None:
        command, _ = _command(self.path, self._prefix)
        if command is None:
            return None
        help_text = await _help(command)
        if help_text is None or not compatible(help_text):
            return None
        return command, help_text

    async def cards(self) -> list[ModelCard]:
        """One card per alias in --model's help, on the subscription, priced as genai-prices'
        newest model of that family. Runs `--help` once (free), then keeps it."""
        ready = await self._ready()
        if ready is None:
            return []
        found = []
        for alias in model_aliases(ready[1]):
            priced = _priced_as(alias)
            found.append(
                ModelCard(
                    choice=ModelChoice(ID, alias),
                    name=f"Claude Code: {alias}",
                    provider=self.provider,
                    images=False,  # One sends it text only
                    tools=True,
                    context=None,
                    price_in=priced[1] if priced else None,
                    price_out=priced[2] if priced else None,
                    price_source=priced[3] if priced else None,
                    subscription=True,
                )
            )
        return found

    async def check(self) -> Text | None:
        """`auth status` only, never a model request: None when ready, else why not."""
        found = await status(self.path, command_prefix=self._prefix)
        if found.code is not None:
            return copy.fill(getattr(copy, found.code), provider=self.name)
        return None

    async def run(self, job: AgentJob, sink: Callable[[Event], None]) -> AgentOutcome:
        usage: dict[str, tuple[int, int]] = {}
        try:
            ready = await self._ready()
            if ready is None:
                log.warning("Claude Code run %s cannot start: not found or too old", job.run_id)
                return AgentOutcome("", job.resume, "failed", (), None)
            command, help_text = ready
            texts, costs = [], []
            stream = await self._once(job, job.task, job.resume, command, help_text, usage, sink)
            ended = stream.ended(self._stopped(job.run_id))
            session = stream.session or job.resume
            texts.append(stream.answer())
            costs.append(stream.cost())
            if (
                ended == "max_tokens"
                and session
                and self.keep_copy
                and not self._stopped(job.run_id)
            ):
                stream = await self._once(job, CONTINUE, session, command, help_text, usage, sink)
                ended = stream.ended(self._stopped(job.run_id))
                session = stream.session or session
                texts.append(stream.answer())
                costs.append(stream.cost())
            known = [c for c in costs if c is not None]
            log.info("Claude Code run %s ended %s (version %s)", job.run_id, ended, stream.version)
            return AgentOutcome(
                text="".join(texts),
                session_id=session,
                ended=ended,
                usage=tuple((i, n_in, n_out) for i, (n_in, n_out) in usage.items()),
                reported_usd=sum(known, Decimal(0)) if known else None,
            )
        except _Refused as refused:
            log.warning("Claude Code run %s refused: %s", job.run_id, refused)
            return AgentOutcome("", job.resume, "failed", (), None)
        finally:
            self._stopping.discard(job.run_id)
            if self._gate is not None:
                self._gate.revoke(job.mcp_token)

    def _stopped(self, run_id: str) -> bool:
        return run_id in self._stopping

    def _argv(self, job: AgentJob, resume: str | None, command, help_text: str) -> list[str]:
        prompt = next(f for f in PROMPT_FLAGS if has(help_text, f))
        argv = [
            *command,
            "-p",
            "--input-format",
            "stream-json",
            "--output-format",
            "stream-json",
            "--verbose",
            "--include-partial-messages",
            "--tools",
            "",
            "--strict-mcp-config",
            "--mcp-config",
            str(job.cwd / MCP_FILE),
            "--setting-sources",
            "",
            "--settings",
            '{"disableAllHooks":true}',
            "--permission-mode",
            "dontAsk",
            "--allowedTools",
            ",".join(TOOL_PREFIX + name for name in job.tools),
            "--disallowedTools",
            BUILT_IN,
            prompt,
            str(job.cwd / INSTRUCTIONS_FILE),
        ]
        if job.model is not None:
            if not _OPTION.fullmatch(job.model):
                raise _Refused("the model id is not a plain name")
            argv += ["--model", job.model]
        if not self.keep_copy:
            argv.append("--no-session-persistence")
        elif resume is not None:
            if _session(resume) != resume:
                raise _Refused("the session id is not a UUID")
            argv += ["--resume", resume]
        return argv

    async def _once(
        self,
        job: AgentJob,
        task: str,
        resume: str | None,
        command: tuple[str, ...],
        help_text: str,
        usage: dict,
        sink: Callable[[Event], None],
    ) -> _Stream:
        argv = self._argv(job, resume, command, help_text)
        if not self.keep_copy and not has(help_text, "--no-session-persistence"):
            raise _Refused("--no-session-persistence is not listed")
        try:
            _prepare(job.cwd)
            config = {
                "mcpServers": {
                    MCP_NAME: {
                        "type": "http",
                        "url": job.mcp_url,
                        "headers": {"Authorization": f"Bearer {job.mcp_token}"},
                    }
                }
            }
            _private_file(job.cwd / MCP_FILE, json.dumps(config))
            _private_file(job.cwd / INSTRUCTIONS_FILE, job.spec.instructions)
        except OSError as error:
            raise _Refused(f"the run folder: {type(error).__name__}") from None
        stream = _Stream(job, sink, usage)
        try:
            await self._drive(argv, job.cwd, _user_line(task), stream, job.run_id)
        finally:
            self._remove_files(job.cwd)
        return stream

    async def _drive(
        self, argv: list[str], cwd: Path, first: dict, stream: _Stream, key: str
    ) -> None:
        """Starts the process, sends `first`, and reads its lines into `stream` until it ends.
        A refused tool, the limit or signed out ends it early (`stream.verdict`)."""
        try:
            process = subprocess.Popen(
                argv,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                env=_env(),
                cwd=cwd,
                creationflags=_NO_WINDOW,
            )
        except OSError:
            raise _Refused("it did not start") from None
        running = self._runs[key] = _Process(process)
        lines: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_running_loop()
        threading.Thread(target=_read, args=(process, lines, loop), daemon=True).start()
        try:
            running.send(first)
            verdict: Ended | None = None
            while True:
                line = await lines.get()
                if line is _EOF:
                    break
                try:
                    value = json.loads(line) if line is not _OVERSIZE else None
                except ValueError:
                    value = None
                if not isinstance(value, dict):
                    verdict = "failed"
                else:
                    verdict = stream.read(value)
                    if value.get("type") == "result":
                        running.close_stdin()  # the turn is over: let it finish and exit
                if verdict is not None:
                    break
            if verdict is not None:
                stream.verdict = verdict
                await asyncio.to_thread(running.halt)
            else:
                await asyncio.to_thread(running.reap)
        except asyncio.CancelledError:
            await asyncio.shield(asyncio.to_thread(running.halt))
            raise
        finally:
            self._runs.pop(key, None)

    async def oneshot(
        self,
        content: list[dict],
        *,
        instructions: str,
        model: str | None,
        tools: tuple[str, ...],
        cwd: Path,
    ) -> AgentOutcome:
        """One answer to one user message (`content`: stream-json blocks, e.g. an image), for a
        tool (Plan 5's `oneshot`): no MCP server, Claude Code's built-in `tools` only (none, or
        WebSearch), and nothing kept: `--no-session-persistence` must be listed, or it does not
        run. `cwd` is its own new folder, which holds only the instructions while it runs."""
        run_id = f"oneshot-{uuid.uuid4().hex}"
        spec = AgentSpec(run_id, {"en": "One", "ar": "One"}, "quick", instructions, (), "quick")
        job = AgentJob(run_id, run_id, spec, "", model, "", "", (), cwd, None)
        failed = AgentOutcome("", None, "failed", (), None)
        ready = await self._ready()
        if ready is None or not has(ready[1], "--no-session-persistence"):
            log.warning("Claude Code cannot run a one-shot call: not found, too old or keeps it")
            return failed
        command, help_text = ready
        if model is not None and not _OPTION.fullmatch(model):
            return failed
        prompt = next(f for f in PROMPT_FLAGS if has(help_text, f))
        argv = [
            *command,
            "-p",
            "--input-format",
            "stream-json",
            "--output-format",
            "stream-json",
            "--verbose",
            "--tools",
            ",".join(tools),
            "--strict-mcp-config",
            "--mcp-config",
            '{"mcpServers":{}}',
            "--setting-sources",
            "",
            "--settings",
            '{"disableAllHooks":true}',
            "--permission-mode",
            "dontAsk",
            *(("--allowedTools", ",".join(tools)) if tools else ()),
            "--disallowedTools",
            ",".join(t for t in BUILT_IN.split(",") if t not in tools),
            prompt,
            str(cwd / INSTRUCTIONS_FILE),
            "--no-session-persistence",
            *(("--model", model) if model is not None else ()),
        ]
        usage: dict[str, tuple[int, int]] = {}
        stream = _Stream(job, lambda event: None, usage)  # its text is never shown as progress
        stream.allowed = set(tools)
        try:
            _prepare(cwd)
            _private_file(cwd / INSTRUCTIONS_FILE, instructions)
            first = {"type": "user", "message": {"role": "user", "content": content}}
            await self._drive(argv, cwd, first, stream, run_id)
        except (OSError, _Refused) as error:
            log.warning("Claude Code one-shot call refused: %s", type(error).__name__)
            return failed
        finally:
            self._remove_files(cwd)
        return AgentOutcome(
            text=stream.answer(),
            session_id=None,
            ended=stream.ended(False),
            usage=tuple((i, n_in, n_out) for i, (n_in, n_out) in usage.items()),
            reported_usd=stream.cost(),
        )

    @staticmethod
    def _remove_files(cwd: Path) -> None:
        for name in (MCP_FILE, INSTRUCTIONS_FILE):
            try:
                (cwd / name).unlink(missing_ok=True)
            except OSError:
                log.warning("A Claude Code config file could not be removed")

    async def steer(self, run_id: str, text: str) -> None:
        """One more stream-json user line. Raises `LookupError` when the run is not running."""
        running = self._runs.get(run_id)
        if running is None or not await asyncio.to_thread(running.send, _user_line(text)):
            raise LookupError(run_id)

    async def stop(self, run_id: str) -> None:
        """Interrupt, then terminate after 5 s, then kill after 5 s more."""
        running = self._runs.get(run_id)
        if running is None:
            return
        self._stopping.add(run_id)
        await asyncio.to_thread(running.halt)


class _Refused(Exception):
    """The job cannot run as asked; the reason goes to core.log only."""


def _read(process: subprocess.Popen, lines: asyncio.Queue, loop: asyncio.AbstractEventLoop):
    """The reader thread: each stdout line to the queue, then the end."""

    def put(item) -> bool:
        try:
            loop.call_soon_threadsafe(lines.put_nowait, item)
        except RuntimeError:  # the loop is closed: nobody is listening
            return False
        return True

    stdout = process.stdout
    assert stdout is not None
    try:
        while True:
            line = stdout.readline(LINE_LIMIT + 1)
            if not line:
                break
            if len(line) > LINE_LIMIT:
                put(_OVERSIZE)
                break
            if line.strip() and not put(line):
                return
    except (OSError, ValueError):
        pass
    finally:
        try:
            stdout.close()
        except OSError:
            pass
    put(_EOF)
