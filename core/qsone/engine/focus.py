"""Which canvas frame an agent works on, read from its tool calls (Plan 7's `Focus`).

`of(tool, args, rec)` gives `{"frame": "<kind>:<id>", "anchor": {...} | None}` for a call that
names a Deliverable, a file (or a chunk of one) or a Desk, and None for any other. The frame key is
only ever built from an id that fits the canvas's keys, so a cursor never points at a frame that
cannot exist. No PydanticAI here; nothing is logged."""

import json
import re

from qsone.records.project import Records

_REF = re.compile(r"[0-9a-z_-]{1,64}")
_DESK_TOOLS = ("use_desk", "save_desk")


def _frame(kind: str, ref) -> str | None:
    return f"{kind}:{ref}" if isinstance(ref, str) and _REF.fullmatch(ref) else None


def _cell(anchor) -> dict | None:
    """A Deliverable anchor's row and column, as the canvas's `Anchor`."""
    if not isinstance(anchor, dict):
        return None
    found = {k: anchor[k] for k in ("row", "column") if isinstance(anchor.get(k), str)}
    return found or None


def _page(locator) -> dict | None:
    page = locator.get("page") if isinstance(locator, dict) else None
    return {"page": page} if isinstance(page, int) and not isinstance(page, bool) else None


def _chunk(rec: Records | None, chunk_id) -> dict | None:
    if rec is None or not isinstance(chunk_id, int):
        return None
    with rec.read() as conn:
        found = conn.execute(
            "SELECT file_id, locator FROM chunks WHERE id = ?", (chunk_id,)
        ).fetchone()
    if found is None:
        return None
    frame = _frame("file", found[0])
    return None if frame is None else {"frame": frame, "anchor": _page(json.loads(found[1]))}


def of(tool: str, args: dict, rec: Records | None) -> dict | None:
    if not isinstance(args, dict):
        return None
    if tool.startswith("deliverable_") and "id" in args:
        frame = _frame("deliverable", args["id"])
        return None if frame is None else {"frame": frame, "anchor": _cell(args.get("anchor"))}
    if "deliverable_id" in args:
        frame = _frame("deliverable", args["deliverable_id"])
        return None if frame is None else {"frame": frame, "anchor": None}
    if "file_id" in args:
        frame = _frame("file", args["file_id"])
        return None if frame is None else {"frame": frame, "anchor": _page(args.get("locator"))}
    if tool == "read_chunk":
        return _chunk(rec, args.get("chunk_id"))
    if tool in _DESK_TOOLS:
        frame = _frame("desk", args.get("slug"))
        return None if frame is None else {"frame": frame, "anchor": None}
    return None
