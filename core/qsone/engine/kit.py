"""The Lead's kit (Phase 1, C7): what the Lead gets at the start of any work.

The engineer's profile (its four fields for the Lead: first name, position, type of organisation,
country), the Lessons Learned kept in Engineer Records, newest first, and one line per tender:
its name, stage, submission date and the items waiting in it. The rows are Home's, from what the
core holds, so the kit opens no closed project.

A Confidential Project is in its own kit only: never in another tender's or in Home's. A removed
lesson is not in it. The whole kit is at most `LIMIT` characters, its fence included: names and
stage titles are cut shorter while that lets more lessons in, the older lessons that still do not
fit are left out, and the kit says how many."""

from collections.abc import Callable

from qsone import home, lessons
from qsone.engine.data_text import as_data, new_fence
from qsone.journey import profile as _profile
from qsone.records.project import Records

LIMIT = 2048
# Characters of a tender's name and of a stage's title, tried in turn until the kit fits.
CUTS = ((40, 32), (28, 20), (20, 12))
LESSON = 240  # characters of one lesson


def _profile_line(engineer: Records) -> str:
    return _profile.lead_line(_profile.read(engineer))


# The profile as one line for the Lead: its four fields only (C1).
profile_line: Callable[[Records], str] = _profile_line


def _cut(text: str, most: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= most else text[: most - 1] + "…"


def _stage(row: dict, most: int) -> str:
    stages = row["stages"]
    if not stages:
        return "no plan yet"
    at = next((i for i, s in enumerate(stages) if s in ("now", "waiting_engineer")), None)
    if at is None or row["stage"] is None:
        return f"{stages.count('approved')}/{len(stages)} stages approved"
    return f"stage {at + 1}/{len(stages)} {_cut(row['stage']['en'], most)}"


def tender_line(row: dict, *, own: bool, cut: tuple[int, int] = CUTS[0]) -> str:
    name = _cut(row["name"], cut[0]) + (" (this tender)" if own else "")
    due = f"due {row['submission_date']}" if row["submission_date"] else "no date"
    waiting = f" | {row['waiting']} waiting" if row["waiting"] else ""
    return f"- {name} | {_stage(row, cut[1])} | {due}{waiting}"


def _left_out(count: int, what: str) -> list[str]:
    return [f"({count} more {what} not shown.)"] if count else []


def _kit(head: list[str], tenders: list[str], left: int, kept: list[str], n: int, fence: str):
    lines = [
        *head,
        *(["Tenders:", *tenders] if tenders or left else ["Tenders: none yet."]),
        *_left_out(left, "tenders"),
    ]
    if kept:  # an empty section is left out: every request carries the kit
        lines += ["Lessons Learned, newest first:", *(f"- {x}" for x in kept[:n])]
        lines += _left_out(len(kept) - n, "lessons")
    return as_data("\n".join(lines), source="ONE's kit", fence=fence)


def _fit(head: list[str], rows: list[dict], project_id: str | None, kept: list[str]) -> str:
    """The kit within `LIMIT`: every tender, and as many lessons as fit, newest first; names
    and stage titles are cut shorter when that lets more lessons in. Only when even the
    shortest lines with no lesson do not fit, the last tenders (the least urgent on Home) are
    left out, and counted."""
    fence = new_fence()
    best: tuple[int, str] | None = None
    for cut in CUTS:
        tenders = [tender_line(r, own=r["project_id"] == project_id, cut=cut) for r in rows]
        for n in range(len(kept), -1, -1):
            found = _kit(head, tenders, 0, kept, n, fence)
            if len(found) <= LIMIT:
                if best is None or n > best[0]:
                    best = (n, found)
                break
    if best is not None:
        return best[1]
    for t in range(len(tenders) - 1, -1, -1):
        found = _kit(head, tenders[:t], len(tenders) - t, kept, 0, fence)
        if len(found) <= LIMIT:
            return found
    return found  # not reached: the head alone is far below the limit


def text(projects, engine, project_id: str | None) -> str:
    """The kit for work in `project_id`'s tender, or in the Home conversation (None). Raises
    `RecordsError` when Engineer Records do not open."""
    engineer = engine.engineer_records()
    rows, _, _ = home.tenders(projects, engine, None)
    shown = [r for r in rows if not r["confidential"] or r["project_id"] == project_id]
    profile = profile_line(engineer)
    head = [profile] if profile else []
    kept = [_cut(x["fields"]["text"], LESSON) for x in lessons.kept(engineer)]
    return _fit(head, shown, project_id, kept)
