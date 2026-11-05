"""The Sandbox tools (Plan 5, Task 11): `sandbox_run` and `sandbox_rerun`.

`sandbox_run` runs an agent's Python script on files from Project Records (Engineer Records in
the General chat), in the Sandbox: CPython on WASI, no network, no disk, one run at a time.
1. The script is checked first (`sandbox.check`): a mistake or a module that cannot work goes
   back to the agent before anything runs.
2. Inputs are file ids; the script opens each by its file name. Pages the script needs are
   read by One through `web_read` (so the `online` gate, the Web Log and the address checks
   apply) and given as inputs `url-1`, `url-2`, …
3. The runtime is downloaded the first time a script runs (`SandboxRunner.ready`).
4. Each output is kept as a file, named as the script gave it with " (sandbox)" before the
   extension. Every run is kept in `sandbox_runs`: the script and its SHA-256, the inputs by
   file id with their SHA-256, the URLs' Web Log ids, the parameters, the limits with the
   clock the guest saw, the exit status, the time, the outputs with their SHA-256 and what it
   printed. A run that ran is deduplicated per Brief; a run that could not start (no
   internet for the download) is not, so trying again really tries again.

What the script said (its result, its printed text, its error) is data, never orders: fenced,
and it marks the Brief, when it printed text or worked on inputs. A number a script finds is
evidence only (Guardrail 2): a recorded number comes from the QS Calc Engine, and `add_source`
refuses both a Sandbox run and a file a script made.

`sandbox_rerun` (the Checking QS's check) runs a kept run again, with the same script, input
file versions, parameters, limits and clock, stores nothing, and says whether every output is
the same, byte for byte.

Importing this module registers the tools. No PydanticAI here."""

import asyncio
import hashlib
import json
import uuid

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from qsone import copy
from qsone.engine import data_text
from qsone.engine.tools import Tool, ToolContext, call, register
from qsone.meaning.download import DownloadError
from qsone.records import files
from qsone.records.project import Records, RecordsError
from qsone.sandbox import check
from qsone.sandbox.runner import MEMORY, RunResult
from qsone.tools import cite
from qsone.tools.cite import SourceRef
from qsone.web import log

INPUTS_MAX = 64 * 1024 * 1024  # bytes of input files and pages in one run (decision 26)
SAID_MAX = 4 * 1024  # bytes of what the script said (result, error, printed) in one result
RESULT_SHOWN = 1536  # of those, at most this much of the result
ERROR_SHOWN = 1024  # and of the error's last lines
NAMES_SHOWN = 5  # inputs and outputs named in one result; the rest are counted
NAME_CHARS = 60
_ROLES = frozenset({"lead", "specialist"})
_EVIDENCE = (
    "A number here is evidence only: record a number through the QS Calc Engine, with the "
    "input files as its sources."
)


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _cut(text: str, size: int) -> str:
    data = text.encode()
    if len(data) <= size:
        return text
    return data[: max(size - 3, 0)].decode(errors="ignore") + "…"


def _tail(text: str, size: int) -> str:
    data = text.encode()
    if len(data) <= size:
        return text
    return "…" + data[-(size - 3) :].decode(errors="ignore")


def _actor(ctx: ToolContext) -> str:
    return ctx.agent.name["en"]


def _records(ctx: ToolContext) -> Records:
    """Where the inputs are and the outputs go: the project, or Engineer Records."""
    return ctx.rec if ctx.rec is not None else ctx.services.engineer()


def _runner(ctx: ToolContext):
    return None if ctx.services is None else ctx.services.sandbox


async def _ready(runner) -> str | None:
    """None once the runtime is in place; else the result that says why not."""
    if runner is None:
        return cite.not_done(copy.SANDBOX_NOT_READY)
    try:
        await runner.ready()
    except DownloadError as e:
        return cite.not_done(e.text, retry_online=e.text == copy.SANDBOX_DOWNLOAD_FAILED)
    return None


class _Args(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


# sandbox_run ---------------------------------------------------------------------------------


class RunArgs(_Args):
    model_config = ConfigDict(str_strip_whitespace=False)  # a script is kept as written

    script: str = Field(min_length=1)  # its size is `check.script`'s to refuse, in plain words
    inputs: list[str] = Field(
        default_factory=list, max_length=50, validation_alias=AliasChoices("inputs", "files")
    )
    urls: list[str] = Field(default_factory=list, max_length=10)
    params: dict = Field(default_factory=dict)
    timeout: int = Field(60, ge=1, le=600)


_RUN_EXAMPLE = {
    "script": (
        "import openpyxl\n"
        "ws = openpyxl.load_workbook(one_io.open_input('BOQ - sample.xlsx'))['BOQ']\n"
        "one_io.result([r for r in range(2, ws.max_row + 1) if ws.cell(r, 4).value is None])"
    ),
    "inputs": ["<file id>"],
    "timeout": 60,
}

_RUN_DOC = f"""Run a Python script on project files in the Sandbox (no network, no disk): \
check, count or reshape a client's Excel.
- script: Python's own modules plus openpyxl and xlrd. one_io.open_input("<file name>") opens \
an input by its name in files_list; one_io.params; one_io.save(name, data) keeps an output \
file; one_io.result(value) answers.
- inputs: file ids from files_list. urls: pages One opens for the script, as inputs url-1, \
url-2, ….
- timeout: 1 to 600 seconds.
Outputs are kept as files "… (sandbox)". A number a script finds is evidence only: \
record numbers through the QS Calc Engine.
Example:
{_json(_RUN_EXAMPLE)}"""


def _unique(name: str, taken: dict) -> str:
    """`name`, or `name (2)` and so on when two inputs share a name."""
    stem, dot, ext = name.rpartition(".")
    stem, ext = (stem, f".{ext}") if dot and stem else (name, "")
    found, n = name, 1
    while found in taken:
        n += 1
        found = f"{stem} ({n}){ext}"
    return found


def _too_much(size: int, field: str) -> None:
    if size > INPUTS_MAX:
        raise RecordsError(copy.SANDBOX_TOO_MUCH, status=422, field=field)


def _input_files(rec: Records, file_ids: list[str]) -> tuple[dict[str, bytes], list[dict]]:
    """The inputs by name, and how the run keeps them. Raises `RecordsError`:
    FILE_NOT_IN_PROJECT for an unknown id; SANDBOX_TOO_MUCH above `INPUTS_MAX`."""
    infos = []
    for file_id in dict.fromkeys(file_ids):
        info = files.file_info(rec, file_id)
        if info is None:
            raise RecordsError(copy.FILE_NOT_IN_PROJECT, status=422, field="inputs")
        infos.append(info)
    _too_much(sum(i.size for i in infos), "inputs")
    data: dict[str, bytes] = {}
    kept = []
    for info in infos:
        name = _unique(info.name, data)
        data[name] = files.read_original(rec, info.id)
        kept.append({"name": name, "file_id": info.id, "sha256": info.sha256})
    return data, kept


async def _pages(ctx: ToolContext, rec: Records, urls: list[str], data: dict, kept: list):
    """Reads each URL through `web_read` and adds the page as an input. Returns None, or the
    result to give when a page could not be read. Raises `Denied` when the engineer said no."""
    for n, url in enumerate(dict.fromkeys(urls), 1):
        before = await asyncio.to_thread(log.last_read, rec, brief_id=ctx.brief_id, url=url)
        said = await call("web_read", {"url": url}, ctx)
        row = await asyncio.to_thread(log.last_read, rec, brief_id=ctx.brief_id, url=url)
        if row is None or (before is not None and row["id"] == before["id"]):
            return f"not done: One could not read {url} for the script, so nothing ran.\n{said}"
        page = await asyncio.to_thread(files.read_original, rec, row["file_id"])
        name = f"url-{n}"
        data[name] = page
        kept.append(
            {"name": name, "url": url, "log_id": row["id"], "file_id": row["file_id"],
             "sha256": _sha(page)}  # fmt: skip
        )
    _too_much(sum(len(d) for d in data.values()), "urls")
    return None


def _kept_name(name: str) -> str:
    stem, dot, ext = name.rpartition(".")
    return f"{stem} (sandbox).{ext}" if dot and stem else f"{name} (sandbox)"


def _ok(r: RunResult) -> bool:
    return r.exit == 0 and not r.error and not r.timed_out and not r.memory_exceeded


def _result_sha(value) -> str:
    return _sha(json.dumps(value, ensure_ascii=False, sort_keys=True).encode())


def _keep(
    ctx: ToolContext,
    rec: Records,
    args: RunArgs,
    kept_inputs: list,
    limits: dict,
    r: RunResult,
    at: str,
    ended: str,
) -> tuple[str, list[dict]]:
    """Stores the outputs of a run that ended well, and the run itself. Returns the run id and
    its outputs as kept."""
    actor = _actor(ctx)
    embedder = ctx.embedder if rec is ctx.rec else None
    outputs = []
    for name, data in r.outputs.items():
        out = {"name": name, "sha256": _sha(data), "size": len(data), "file_id": None}
        if _ok(r) and data:
            info = files.add_file(rec, _kept_name(name), data, actor=actor, embedder=embedder)
            out |= {"file_id": info.id, "kept_as": info.name, "new": not info.duplicate}
        outputs.append(out)
    run_id = uuid.uuid4().hex
    row = {
        "id": run_id,
        "at": at,
        "actor": actor,
        "brief_id": ctx.brief_id,
        "script": args.script,
        "script_sha256": _sha(args.script.encode()),
        "inputs": _json(kept_inputs),
        "params": _json(args.params),
        "limits": _json(limits),
        "exit": r.exit,
        "ended": ended,
        "seconds": r.seconds,
        "outputs": _json(
            {"files": outputs, "result": r.result, "result_sha256": _result_sha(r.result)}
        ),
        "printed": r.printed,
    }
    with rec.write(actor) as conn:
        conn.execute(
            "INSERT INTO sandbox_runs(id, at, actor, brief_id, script, script_sha256, inputs,"
            " params, limits, exit, ended, seconds, outputs, printed) VALUES (:id, :at, :actor,"
            " :brief_id, :script, :script_sha256, :inputs, :params, :limits, :exit, :ended,"
            " :seconds, :outputs, :printed)",
            row,
        )
    return run_id, outputs


def _named(entries: list[str]) -> str:
    shown = ", ".join(entries[:NAMES_SHOWN])
    more = len(entries) - NAMES_SHOWN
    return shown + (f", and {more} more" if more > 0 else "")


def _what_it_said(r: RunResult) -> str:
    """The script's own words, at most `SAID_MAX` bytes."""
    parts = []
    if r.result is not None:
        parts.append("result: " + _cut(_json(r.result), RESULT_SHOWN))
    if r.error and not (r.timed_out or r.memory_exceeded):
        parts.append("error (its last lines):\n" + _tail(r.error, ERROR_SHOWN))
    if r.printed:
        room = SAID_MAX - sum(len(p.encode()) + 1 for p in parts) - 9
        parts.append("printed:\n" + _cut(r.printed, max(room, 0)))
    return "\n".join(parts)


def _failure(r: RunResult, timeout: int) -> dict | None:
    """The copy text for a run that did not end well, or None."""
    if r.timed_out:
        return copy.fill(copy.SANDBOX_TIMEOUT, seconds=timeout)
    if r.memory_exceeded:
        return copy.SANDBOX_MEMORY
    if r.error == "output too large":
        return copy.SANDBOX_TOO_MUCH
    if (r.error or "").startswith("runtime:"):
        return copy.SANDBOX_NOT_READY
    return None if _ok(r) else copy.SANDBOX_FAILED


def _said(
    ctx: ToolContext,
    args: RunArgs,
    kept_inputs: list,
    run_id: str,
    outputs: list,
    r: RunResult,
    read: str,
) -> str:
    failed = _failure(r, args.timeout)
    lines = [
        cite.not_done(failed)
        if failed
        else f"Sandbox run {run_id}: done in {r.seconds} s, exit {r.exit}."
    ]
    if kept_inputs:
        refs = [
            f"{i['name']} = web:{i['log_id']}"
            if "log_id" in i
            else f"«{i['name'][:NAME_CHARS]}» = file:{i['file_id']}"
            for i in kept_inputs
        ]
        lines.append("inputs: " + _named(refs))
    kept = [o for o in outputs if o["file_id"]]
    if kept:
        refs = [f"«{o['kept_as'][:NAME_CHARS]}» = file:{o['file_id']}" for o in kept]
        lines.append("outputs kept as files: " + _named(refs))
    said = _what_it_said(r)
    untrusted = bool(r.printed) or (bool(kept_inputs) and bool(said))
    if said:
        if untrusted:
            said = data_text.as_data(said, source="sandbox_run", fence=ctx.fence)
            ctx.store.mark_untrusted(ctx.brief_id)
        lines.append(said)
    source = SourceRef(f"sandbox:{run_id}", f"Sandbox run on {len(kept_inputs)} inputs", read)
    notes = [f"run: sandbox:{run_id} is kept; sandbox_rerun runs it again", _EVIDENCE]
    return cite.render("\n".join(lines), sources=[source], notes=notes)


def _write_key(args: RunArgs) -> str:
    """As the engine's own write key: the same run asked again in a Brief is not run again."""
    canonical = json.dumps(
        args.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return _sha(f"sandbox_run\n{canonical}".encode())


async def _sandbox_run(ctx: ToolContext, args: RunArgs) -> str:
    check.script(args.script)
    key = _write_key(args)
    earlier = ctx.store.known_write(ctx.brief_id, key)
    if earlier is not None:
        return earlier
    runner = _runner(ctx)
    if runner is None:
        return cite.not_done(copy.SANDBOX_NOT_READY)
    rec = _records(ctx)
    data, kept_inputs = await asyncio.to_thread(_input_files, rec, args.inputs)
    if (not_ready := await _ready(runner)) is not None:
        return not_ready
    if args.urls and (unread := await _pages(ctx, rec, args.urls, data, kept_inputs)):
        return unread
    started = ctx.services.clock()
    limits = {"timeout": args.timeout, "memory": MEMORY, "clock": int(started.timestamp())}
    r = await runner.run(
        args.script,
        data,
        args.params,
        timeout=limits["timeout"],
        memory=limits["memory"],
        clock=limits["clock"],
    )
    del data
    ended = ctx.services.clock()
    run_id, outputs = await asyncio.to_thread(
        _keep, ctx, rec, args, kept_inputs, limits, r, started.isoformat(), ended.isoformat()
    )
    out = _said(ctx, args, kept_inputs, run_id, outputs, r, ended.strftime("%Y-%m-%d %H:%M UTC"))
    ctx.store.remember_write(ctx.brief_id, key, out)
    return out


# sandbox_rerun -------------------------------------------------------------------------------


class RerunArgs(_Args):
    run_id: str = Field(
        min_length=1, max_length=64, validation_alias=AliasChoices("run_id", "run", "id")
    )


_RERUN_EXAMPLE = {"run_id": "<run id from a sandbox: source>"}

_RERUN_DOC = f"""Run a kept Sandbox run again, to check it: the same script on the same input \
file versions, with the same parameters, limits and clock. Nothing is stored.
- run_id: from a sandbox:<run id> source in a result or the check packet.
Returns same (true when the exit, the result and every output file match, byte for byte) and \
differs (what does not).
Example:
{_json(_RERUN_EXAMPLE)}"""


def _stored_run(rec: Records, run_id: str) -> dict:
    with rec.read() as conn:
        row = conn.execute(
            "SELECT script, inputs, params, limits, exit, outputs FROM sandbox_runs WHERE id = ?",
            (run_id.removeprefix("sandbox:"),),
        ).fetchone()
    if row is None:
        raise RecordsError(copy.SANDBOX_RUN_UNKNOWN, status=422, field="run_id")
    script, inputs, params, limits, exit_code, outputs = row
    inputs = json.loads(inputs)
    return {
        "id": run_id.removeprefix("sandbox:"),
        "script": script,
        "inputs": {i["name"]: files.read_original(rec, i["file_id"]) for i in inputs},
        "params": json.loads(params),
        "limits": json.loads(limits),
        "exit": exit_code,
        "outputs": json.loads(outputs),
    }


def _differs(kept: dict, r: RunResult) -> list[str]:
    differs = [] if kept["exit"] == r.exit else ["exit"]
    if kept["outputs"].get("result_sha256") != _result_sha(r.result):
        differs.append("result")
    before = {o["name"]: o["sha256"] for o in kept["outputs"]["files"]}
    now = {name: _sha(data) for name, data in r.outputs.items()}
    differs += [n for n in dict.fromkeys([*before, *now]) if before.get(n) != now.get(n)]
    return differs


async def _sandbox_rerun(ctx: ToolContext, args: RerunArgs) -> str:
    runner = _runner(ctx)
    if (not_ready := await _ready(runner)) is not None:
        return not_ready
    kept = await asyncio.to_thread(_stored_run, _records(ctx), args.run_id)
    limits = kept["limits"]
    r = await runner.run(
        kept["script"],
        kept["inputs"],
        kept["params"],
        timeout=limits["timeout"],
        memory=limits["memory"],
        clock=limits["clock"],
    )
    if (r.error or "").startswith("runtime:"):
        return cite.not_done(copy.SANDBOX_NOT_READY)
    differs = _differs(kept, r)
    read = ctx.services.clock().strftime("%Y-%m-%d %H:%M UTC")
    source = SourceRef(f"sandbox:{kept['id']}", "Sandbox run, run again", read)
    text = f"Sandbox run {kept['id']} run again in {r.seconds} s."
    return cite.render(text, data={"same": not differs, "differs": differs}, sources=[source])


for _tool in (
    Tool(
        "sandbox_run",
        _RUN_DOC,
        RunArgs,
        "write",
        _sandbox_run,
        lambda a: copy.fill(copy.DOING_SANDBOX, count=len(a.inputs) + len(a.urls)),
        example=_RUN_EXAMPLE,
        roles=_ROLES,
        group="sandbox",
    ),
    Tool(
        "sandbox_rerun",
        _RERUN_DOC,
        RerunArgs,
        "read",
        _sandbox_rerun,
        lambda _: copy.fill(copy.TOOL_WORKING, tool="sandbox_rerun"),
        example=_RERUN_EXAMPLE,
        group="sandbox",
    ),
):
    register(_tool)

SANDBOX_TOOLS = ("sandbox_run", "sandbox_rerun")
