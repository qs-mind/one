"""`data-sources` (contract 3.1, rules 6 and 7): what the core can prove a reply rests on, made when
the reply ends beside `data-sourced` and rebuilt the same way for a stored reply.

In this order, each place once, at most `LIMIT`: the ledger sources of the figures `data-sourced`
names, then the places in the `sources:` lines of the Lead's own tool results in this Brief, in
the order they were read (the `tools.cite` form: `- ref | title | where | dated … | read …`)."""

import json
from urllib.parse import parse_qsl

from qsone.deliverables.store import sources_of
from qsone.engine import agents
from qsone.engine.types import Data
from qsone.records.project import Records, RecordsError

LIMIT = 20


def _ledger(rec: Records, named: dict) -> list[dict]:
    number_ids = list(dict.fromkeys(n["id"] for n in named.values()))
    if not number_ids:
        return []
    with rec.read() as conn:
        rows = conn.execute(
            "SELECT id, source_id FROM numbers WHERE id IN (SELECT value FROM json_each(?))",
            (json.dumps(number_ids),),
        ).fetchall()
    of = dict(rows)
    source_ids = list(dict.fromkeys(of[i] for i in number_ids if i in of))
    found = sources_of(rec, source_ids)
    return [found[s] for s in source_ids if s in found]


def _number(value: str):
    try:
        return int(value)
    except ValueError:
        return value


def _line(line: str) -> dict | None:
    """One `sources:` line as a `Source`, or None for one that is not in that form."""
    parts = line[2:].split(" | ")
    if len(parts) < 4 or not parts[-1].startswith("read ") or ":" not in parts[0]:
        return None
    ref, title, *where, dated = parts[:-1]
    kind, _, rest = ref.partition(":")
    target, _, fragment = rest.partition("#")
    locator: dict = {k: _number(v) for k, v in parse_qsl(fragment)}
    url = None
    if where:
        if where[0].startswith(("http://", "https://")):
            url = where[0]
        else:
            try:
                given = json.loads(where[0])
            except ValueError:
                given = None
            if isinstance(given, dict):
                locator = given
    is_file = kind == "file"
    return {
        "kind": kind,
        "title": title,
        "file_name": title if is_file else None,
        "file_id": target if is_file and target else None,
        "locator": locator,
        "url": url,
        "dated": dated[len("dated ") :] if dated.startswith("dated ") else None,
        "quote": None,
    }


def _read(history: bytes | None) -> list[dict]:
    if not history:
        return []
    found = []
    for _, text in agents.tool_returns(history):
        lines = text.splitlines()
        if "sources:" not in lines:
            continue
        for line in lines[lines.index("sources:") + 1 :]:
            if not line.startswith("- "):
                break
            source = _line(line)
            if source is not None:
                found.append(source)
    return found


def _place(source: dict) -> str:
    keys = ("kind", "file_id", "locator", "url", "title")
    return json.dumps([source.get(k) for k in keys], sort_keys=True, ensure_ascii=False)


def sources(rec: Records | None, named: dict, lead_history: bytes | None) -> list[dict]:
    """The reply's sources, as `Source` dicts. `named` is what `data-sourced` carries."""
    found = []
    if rec is not None and named:
        try:
            found += _ledger(rec, named)
        except RecordsError:
            pass  # only the row of links: the reply stands without the ledger's half
    found += _read(lead_history)
    out, seen = [], set()
    for source in found:
        if _place(source) not in seen:
            seen.add(_place(source))
            out.append(source)
    return out[:LIMIT]


def part(brief_id: str, rec: Records | None, named: dict, lead_history: bytes | None):
    """`data-sources` for the reply, or None when the core can prove no source."""
    found = sources(rec, named, lead_history)
    return Data(brief_id, "sources", brief_id, {"sources": found}) if found else None
