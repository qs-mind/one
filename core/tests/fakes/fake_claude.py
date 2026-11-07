"""A stand-in for the engineer's own `claude` (the Claude Code CLI), for tests only.

It behaves like the documented CLI as far as One uses it:

- `--help` lists the flags One needs; `--version` prints `2.1.318 (Claude Code)`;
  `auth --help` lists `status`; `auth status` prints `{"loggedIn": true}`.
- `-p --input-format stream-json --output-format stream-json --verbose` waits for the first
  stream-json user line on stdin, then plays a script and exits. `--include-partial-messages`
  adds `stream_event` lines. An unknown flag is refused, as the real CLI does.
- An interrupt line (`control_request` / `interrupt`) or SIGTERM ends it cleanly (exit 0).

Settings come from the environment or, because One clears the environment it passes on, from
`--fake-<name>=<value>` arguments placed before the real ones (`engine_fakes.fake_claude_command`);
those are never logged as argv:

- FAKE_CLAUDE_SCRIPT / --fake-script: JSON text or a path to a JSON file. A list of steps for one
  run, or `{"runs": [[...], [...]]}`: run N plays runs[N], the last repeating. Runs that log are
  numbered 0, 1, … in the order they start, by a counter beside the log (`<log>.run<N>` files);
  a run with no log is run 0.
- FAKE_CLAUDE_LOG / --fake-log: a JSON-lines file; `engine_fakes.read_fake_log` reads it.
  It logs the argv, the environment's names (never values), the files named by --mcp-config and
  --system-prompt-file, each stdin line, and how the run ended.
- FAKE_CLAUDE_DROP / --fake-drop: comma-separated flags left out of `--help` (and refused).
- FAKE_CLAUDE_SIGNED_OUT / --fake-signed-out: `auth status` says signed out.
- FAKE_CLAUDE_VERSION / --fake-version.

Steps (a string, or an object with one key):

- "init": the `system/init` line; `{"init": {"model": …, "session_id": …}}` overrides.
- {"text": "…" | ["chunk", …], "id"?, "usage"?: [in, out], "stop_reason"?}: one assistant
  message. The same "id" twice is a replayed message, as Claude Code sends on resume.
- {"usage": [in, out]}: the usage of the following messages.
- {"tool_use": {"name", "input"?, "id"?}}: an assistant tool call that is only shown, never run.
- {"mcp_call": {"tool", "args"?, "server"?: "one"}}: a tool call through MCP, made for real
  with the `mcp` client to the URL and headers in --mcp-config; its result comes back as a
  `user` tool_result line. A URL that is not loopback stops the fake.
- {"sleep": seconds}: waits; an interrupt or SIGTERM ends it early.
- {"await_user": seconds}: waits for one more user line on stdin (a steer), at most that long.
- "drop": exits with code 3 mid-stream, with no result line.
- {"error": "rate_limit" | "authentication_failed" | …, "status"?}: a `system/api_retry` line.
- "result" or {"result": {"subtype"?, "is_error"?, "cost"?: "0.01"}}: the result line.
"""

import asyncio
import ipaddress
import json
import os
import queue
import signal
import sys
import threading
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit

OPTIONS = [
    ("-p, --print", "Print response and exit (useful for pipes)"),
    ("--input-format <format>", 'Input format (only works with --print): "text" or "stream-json"'),
    (
        "--output-format <format>",
        'Output format (only works with --print): "text", "json" or "stream-json"',
    ),
    ("--verbose", "Override verbose mode setting from config"),
    (
        "--include-partial-messages",
        "Include partial message chunks as they arrive (only with --print and stream-json)",
    ),
    ("--tools <tools...>", 'Built-in tools to make available; "" disables all of them'),
    ("--mcp-config <configs...>", "Load MCP servers from JSON files or strings"),
    ("--strict-mcp-config", "Only use MCP servers from --mcp-config"),
    (
        "--setting-sources <sources>",
        "Comma-separated setting sources to load (user, project, local)",
    ),
    ("--settings <file-or-json>", "Path to a settings JSON file or a JSON string"),
    ("--permission-mode <mode>", 'Permission mode: "default", "acceptEdits", "plan", "dontAsk"'),
    ("--allowedTools, --allowed-tools <tools...>", "Tool names to allow"),
    ("--disallowedTools, --disallowed-tools <tools...>", "Tool names to deny"),
    ("--system-prompt-file <file>", "Replace the system prompt with the contents of a file"),
    ("--append-system-prompt-file <file>", "Append a file's contents to the system prompt"),
    (
        "--model <model>",
        "Model for the current session. Provide an alias for the latest model (e.g. 'opus' or "
        "'sonnet' or 'haiku') or a model's full name (e.g. 'claude-opus-5-5').",
    ),
    ("--effort <level>", "Effort level for the current session (low, medium, high, xhigh, max)"),
    ("-r, --resume [sessionId]", "Resume a conversation by session ID"),
    ("--no-session-persistence", "Do not save the session to disk (only with --print)"),
    ("-v, --version", "Output the version number"),
    ("-h, --help", "Display help for command"),
]
VALUED = {
    "--input-format",
    "--output-format",
    "--mcp-config",
    "--setting-sources",
    "--settings",
    "--permission-mode",
    "--system-prompt-file",
    "--append-system-prompt-file",
    "--model",
    "--effort",
    "--resume",
    "-r",
}
VARIADIC = {
    "--tools",
    "--allowedTools",
    "--allowed-tools",
    "--disallowedTools",
    "--disallowed-tools",
}
FLAGS = {
    "-p",
    "--print",
    "--verbose",
    "--include-partial-messages",
    "--strict-mcp-config",
    "--no-session-persistence",
}

_out_lock = threading.Lock()
_log_lock = threading.Lock()


def settings(argv: list[str]) -> tuple[dict[str, str], list[str]]:
    """The fake's own settings, and the argv without its `--fake-*` arguments."""
    own = {
        name[len("FAKE_CLAUDE_") :].lower().replace("_", "-"): value
        for name, value in os.environ.items()
        if name.startswith("FAKE_CLAUDE_")
    }
    rest = []
    for arg in argv:
        if arg.startswith("--fake-"):
            name, _, value = arg[len("--fake-") :].partition("=")
            own[name] = value or "1"
        else:
            rest.append(arg)
    return own, rest


def flag_names(spec: str) -> list[str]:
    return [part.split(" ")[0] for part in spec.split(", ")]


def dropped(own: dict[str, str]) -> set[str]:
    return {f.strip() for f in own.get("drop", "").split(",") if f.strip()}


def help_text(own: dict[str, str]) -> str:
    gone = dropped(own)
    lines = [
        "Usage: claude [options] [command] [prompt]",
        "",
        "Claude Code - starts an interactive session by default, use -p/--print for "
        "non-interactive output",
        "",
        "Options:",
    ]
    for spec, about in OPTIONS:
        if not gone & set(flag_names(spec)):
            lines.append(f"  {spec:<50} {about}")
    lines += ["", "Commands:", "  auth                 Manage authentication", ""]
    return "\n".join(lines)


def parse(argv: list[str], own: dict[str, str]) -> dict:
    known = (VALUED | VARIADIC | FLAGS) - dropped(own)
    opts: dict = {}
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg not in known:
            fail(f"error: unknown option '{arg}'")
        if arg in FLAGS:
            opts[arg] = True
            i += 1
        elif arg in VALUED:
            if i + 1 >= len(argv):
                fail(f"error: option '{arg}' argument missing")
            opts[arg] = argv[i + 1]
            i += 2
        else:  # variadic: values up to the next option
            values = []
            i += 1
            while i < len(argv) and not argv[i].startswith("-"):
                values.append(argv[i])
                i += 1
            opts[arg] = values
    return opts


def fail(message: str, code: int = 1) -> None:
    sys.stderr.write(message + "\n")
    sys.stderr.flush()
    os._exit(code)


def out(obj: dict) -> None:
    with _out_lock:
        sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
        sys.stdout.flush()


def _lock_file(f) -> None:
    """An exclusive lock the system drops if this process dies."""
    if os.name == "nt":
        import msvcrt

        f.seek(0)
        while True:
            try:
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                return
            except OSError:
                time.sleep(0.005)
    else:
        import fcntl

        fcntl.flock(f.fileno(), fcntl.LOCK_EX)


def _unlock_file(f) -> None:
    if os.name == "nt":
        import msvcrt

        f.seek(0)
        msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def claim_run_number(log: Path) -> int:
    """The lowest run number no other run has: each is claimed by creating `<log>.run<n>`
    exclusively, which is atomic on every system, so runs started at once never share one."""
    n = 0
    while True:
        try:
            os.close(os.open(f"{log}.run{n}", os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            return n
        except FileExistsError:
            n += 1


class Log:
    def __init__(self, path: str | None) -> None:
        self.path = Path(path) if path else None
        self.n = claim_run_number(self.path) if self.path else 0

    def write(self, record: dict) -> None:
        if self.path:
            # Runs started at once share the log. _log_lock covers this process's threads; the
            # file lock covers other processes (Windows appends from two processes can collide).
            with _log_lock, open(f"{self.path}.lock", "a+b") as lock:
                _lock_file(lock)
                try:
                    with self.path.open("a", encoding="utf-8") as f:
                        f.write(json.dumps(record, ensure_ascii=False) + "\n")
                finally:
                    _unlock_file(lock)

    def start(self, argv: list[str], files: dict[str, str]) -> None:
        run = {
            "n": self.n,
            "argv": argv,
            "env_names": sorted(os.environ),
            "cwd": os.getcwd(),
            "files": files,
        }
        self.write({"kind": "start", "run": run})

    def end(self, how: str) -> None:
        self.write({"kind": "end", "n": self.n, "how": how})


def read_value(value: str) -> str:
    """A flag's value that may be a JSON string or a path to a file."""
    stripped = value.strip()
    if stripped.startswith("{"):
        return value
    return Path(value).read_text(encoding="utf-8")


def load_script(own: dict[str, str], n: int) -> list:
    raw = own.get("script", "[]")
    if not raw.strip().startswith(("[", "{")):
        raw = Path(raw).read_text(encoding="utf-8")
    script = json.loads(raw)
    if isinstance(script, dict):
        runs = script["runs"]
        return runs[min(n, len(runs) - 1)]
    return script


def loopback(url: str) -> bool:
    host = urlsplit(url).hostname or ""
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


async def mcp_call(url: str, headers: dict, tool: str, args: dict) -> tuple[str, bool]:
    from mcp.client.session import ClientSession
    from mcp.client.streamable_http import streamable_http_client
    from mcp.shared._httpx_utils import create_mcp_http_client

    async with create_mcp_http_client(headers=headers) as http:
        async with streamable_http_client(url, http_client=http) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool, args)
    texts = [c.text for c in result.content if getattr(c, "type", None) == "text"]
    return "\n".join(texts), bool(result.is_error)


class Run:
    def __init__(self, opts: dict, own: dict[str, str], log: Log) -> None:
        self.opts = opts
        self.log = log
        self.partial = bool(opts.get("--include-partial-messages"))
        self.session = opts.get("--resume") or opts.get("-r") or str(uuid.uuid4())
        self.model = opts.get("--model") or "claude-opus-5-5"
        self.mcp = json.loads(read_value(opts["--mcp-config"])) if "--mcp-config" in opts else {}
        self.usage = [100, 10]
        self.by_message: dict[str, list[int]] = {}
        self.text = ""
        self.stop_reason: str | None = None
        self.turns = 0
        self.started = time.monotonic()
        self.users: queue.Queue = queue.Queue()
        self.interrupted = threading.Event()

    # stdin -------------------------------------------------------------------------------------

    def read_stdin(self) -> None:
        for line in sys.stdin:
            if not line.strip():
                continue
            message = json.loads(line)
            self.log.write({"kind": "stdin", "n": self.log.n, "line": message})
            if message.get("type") == "control_request":
                if message.get("request", {}).get("subtype") == "interrupt":
                    out(
                        {
                            "type": "control_response",
                            "response": {
                                "subtype": "success",
                                "request_id": message.get("request_id"),
                            },
                        }
                    )
                    self.interrupted.set()
            elif message.get("type") == "user":
                self.users.put(message)
        self.users.put(None)  # end of input

    def await_user(self, seconds: float) -> None:
        """Waits for one more user line (a steer), the end of stdin, an interrupt or the time."""
        deadline = time.monotonic() + seconds
        while not self.interrupted.is_set() and time.monotonic() < deadline:
            try:
                self.users.get(timeout=0.05)
                return
            except queue.Empty:
                continue

    def stop_if_interrupted(self) -> None:
        if self.interrupted.is_set():
            self.log.end("interrupted")
            os._exit(0)

    # Lines -------------------------------------------------------------------------------------

    def event(self, event: dict) -> None:
        if self.partial:
            out(
                {
                    "type": "stream_event",
                    "event": event,
                    "session_id": self.session,
                    "parent_tool_use_id": None,
                    "uuid": str(uuid.uuid4()),
                }
            )

    def assistant(self, message_id: str, content: list, stop_reason: str, usage: list[int]):
        self.by_message[message_id] = usage
        self.stop_reason = stop_reason
        out(
            {
                "type": "assistant",
                "message": {
                    "id": message_id,
                    "type": "message",
                    "role": "assistant",
                    "model": self.model,
                    "content": content,
                    "stop_reason": stop_reason,
                    "usage": {"input_tokens": usage[0], "output_tokens": usage[1]},
                },
                "parent_tool_use_id": None,
                "session_id": self.session,
                "uuid": str(uuid.uuid4()),
            }
        )

    def message_start(self, message_id: str, usage: list[int]) -> None:
        self.event(
            {
                "type": "message_start",
                "message": {
                    "id": message_id,
                    "type": "message",
                    "role": "assistant",
                    "model": self.model,
                    "content": [],
                    "usage": {"input_tokens": usage[0], "output_tokens": 1},
                },
            }
        )

    def message_end(self, stop_reason: str, usage: list[int]) -> None:
        self.event(
            {
                "type": "message_delta",
                "delta": {"stop_reason": stop_reason},
                "usage": {"output_tokens": usage[1]},
            }
        )
        self.event({"type": "message_stop"})

    # Steps -------------------------------------------------------------------------------------

    def init(self, step: dict) -> None:
        self.session = step.get("session_id", self.session)
        self.model = step.get("model", self.model)
        allowed = self.opts.get("--allowedTools") or self.opts.get("--allowed-tools") or []
        out(
            {
                "type": "system",
                "subtype": "init",
                "cwd": os.getcwd(),
                "session_id": self.session,
                "tools": [t for value in allowed for t in value.replace(",", " ").split()],
                "mcp_servers": [
                    {"name": name, "status": "connected"} for name in self.mcp.get("mcpServers", {})
                ],
                "model": self.model,
                "permissionMode": self.opts.get("--permission-mode", "default"),
                "apiKeySource": "none",
                "claude_code_version": VERSION,
                "uuid": str(uuid.uuid4()),
            }
        )

    def say(self, step: dict) -> None:
        chunks = step["text"] if isinstance(step["text"], list) else [step["text"]]
        message_id = step.get("id") or f"msg_{uuid.uuid4().hex[:24]}"
        usage = step.get("usage") or self.usage
        stop_reason = step.get("stop_reason", "end_turn")
        whole = "".join(chunks)
        self.message_start(message_id, usage)
        self.event(
            {
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "text", "text": ""},
            }
        )
        for chunk in chunks:
            self.event(
                {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "text_delta", "text": chunk},
                }
            )
        self.event({"type": "content_block_stop", "index": 0})
        self.message_end(stop_reason, usage)
        self.assistant(message_id, [{"type": "text", "text": whole}], stop_reason, usage)
        self.text = whole
        self.turns += 1

    def use_tool(self, name: str, tool_input: dict, tool_id: str) -> None:
        message_id = f"msg_{uuid.uuid4().hex[:24]}"
        block = {"type": "tool_use", "id": tool_id, "name": name, "input": tool_input}
        self.message_start(message_id, self.usage)
        self.event(
            {"type": "content_block_start", "index": 0, "content_block": {**block, "input": {}}}
        )
        self.event(
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "input_json_delta", "partial_json": json.dumps(tool_input)},
            }
        )
        self.event({"type": "content_block_stop", "index": 0})
        self.message_end("tool_use", self.usage)
        self.assistant(message_id, [block], "tool_use", self.usage)
        self.turns += 1

    def tool_use(self, step: dict) -> None:
        tool_id = step.get("id") or f"toolu_{uuid.uuid4().hex[:24]}"
        self.use_tool(step["name"], step.get("input", {}), tool_id)

    def call_mcp(self, step: dict) -> None:
        server = step.get("server", "one")
        config = self.mcp.get("mcpServers", {}).get(server)
        if config is None:
            fail(f"fake claude: no MCP server {server!r} in --mcp-config", 2)
        if not loopback(config["url"]):
            fail("fake claude: the MCP URL is not loopback; tests never leave this computer", 2)
        tool_id = f"toolu_{uuid.uuid4().hex[:24]}"
        args = step.get("args", {})
        self.use_tool(f"mcp__{server}__{step['tool']}", args, tool_id)
        done = threading.Event()
        answer: list = []

        def work() -> None:
            try:
                answer.append(
                    asyncio.run(
                        mcp_call(config["url"], config.get("headers", {}), step["tool"], args)
                    )
                )
            except BaseException as e:  # noqa: BLE001 - shown to the model as a tool error
                answer.append((f"MCP error: {type(e).__name__}: {e}", True))
            done.set()

        threading.Thread(target=work, daemon=True).start()
        while not done.wait(0.05):
            self.stop_if_interrupted()
        result_text, is_error = answer[0]
        self.log.write(
            {
                "kind": "mcp",
                "n": self.log.n,
                "tool": step["tool"],
                "text": result_text,
                "is_error": is_error,
            }
        )
        out(
            {
                "type": "user",
                "message": {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": tool_id,
                            "content": [{"type": "text", "text": result_text}],
                            "is_error": is_error,
                        }
                    ],
                },
                "parent_tool_use_id": None,
                "session_id": self.session,
                "uuid": str(uuid.uuid4()),
            }
        )

    def api_retry(self, step: dict) -> None:
        category = step["error"]
        status = step.get(
            "status", {"rate_limit": 429, "authentication_failed": 401}.get(category, 500)
        )
        out(
            {
                "type": "system",
                "subtype": "api_retry",
                "attempt": 1,
                "max_retries": 10,
                "retry_delay_ms": 1000,
                "error_status": status,
                "error": category,
                "session_id": self.session,
                "uuid": str(uuid.uuid4()),
            }
        )

    def result(self, step: dict) -> None:
        subtype = step.get("subtype", "success")
        totals = [
            sum(u[0] for u in self.by_message.values()),
            sum(u[1] for u in self.by_message.values()),
        ]
        out(
            {
                "type": "result",
                "subtype": subtype,
                "is_error": step.get("is_error", subtype != "success"),
                "duration_ms": int((time.monotonic() - self.started) * 1000),
                "duration_api_ms": 0,
                "num_turns": self.turns,
                "result": step.get("text", self.text),
                "stop_reason": self.stop_reason,
                "session_id": self.session,
                "total_cost_usd": float(step.get("cost", "0")),
                "usage": {"input_tokens": totals[0], "output_tokens": totals[1]},
                "uuid": str(uuid.uuid4()),
            }
        )

    def play(self, script: list) -> None:
        for raw in script:
            self.stop_if_interrupted()
            name, step = (raw, {}) if isinstance(raw, str) else next(iter(raw.items()))
            if name == "init":
                self.init(step)
            elif name == "text":
                self.say(raw)
            elif name == "usage":
                self.usage = list(step)
            elif name == "tool_use":
                self.tool_use(step)
            elif name == "mcp_call":
                self.call_mcp(step)
            elif name == "sleep":
                self.interrupted.wait(float(step))
            elif name == "await_user":
                self.await_user(float(step))
            elif name == "drop":
                self.log.end("dropped")
                os._exit(3)
            elif name == "error":
                self.api_retry(raw)
            elif name == "result":
                self.result(step if isinstance(step, dict) else {})
            else:
                fail(f"fake claude: unknown step {raw!r}", 2)
        self.stop_if_interrupted()


VERSION = "2.1.318"


def main() -> None:
    global VERSION
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    own, argv = settings(sys.argv[1:])
    VERSION = own.get("version", VERSION)
    if argv[:1] == ["auth"]:
        if argv[1:2] == ["status"]:
            signed_in = own.get("signed-out", "") in ("", "0")
            print(json.dumps({"loggedIn": signed_in}))
            sys.exit(0 if signed_in else 1)
        print("Usage: claude auth [options] [command]\n\nCommands:\n  status   Show sign-in status")
        return
    if not argv or argv[0] in ("-h", "--help"):
        print(help_text(own))
        return
    if argv[0] in ("-v", "--version"):
        print(f"{VERSION} (Claude Code)")
        return
    opts = parse(argv, own)
    if not (opts.get("-p") or opts.get("--print")):
        fail("fake claude: only -p (print mode) is supported")
    if opts.get("--input-format") != "stream-json" or opts.get("--output-format") != "stream-json":
        fail("fake claude: only --input-format stream-json --output-format stream-json")
    if not opts.get("--verbose"):
        fail("Error: When using --print, --output-format=stream-json requires --verbose")

    log = Log(own.get("log"))
    files = {}
    for flag in ("--mcp-config", "--system-prompt-file", "--append-system-prompt-file"):
        if flag in opts:
            value = opts[flag][0] if isinstance(opts[flag], list) else opts[flag]
            files[flag] = (
                read_value(value)
                if flag == "--mcp-config"
                else Path(value).read_text(encoding="utf-8")
            )
    log.start(argv, files)
    run = Run(opts, own, log)

    def terminated(signum, frame) -> None:
        log.end("terminated")
        os._exit(0)

    signal.signal(signal.SIGTERM, terminated)
    threading.Thread(target=run.read_stdin, daemon=True).start()
    if run.users.get() is None:  # stdin closed before any message
        log.end("done")
        return
    run.play(load_script(own, log.n))
    log.end("done")
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
