"""The Lead's summary on Home: where it is kept, and the rule that it never disagrees with the
lists under it (Phase 1, C7; contract section 1, row 6, and section 7, Q13).

It is kept in Engineer Records' meta (encrypted), with the ids of the tenders it covers and what
Home showed of them when it was written: for each covered tender its `state`, `stage`, `stages`
and `submission_date`, and the ids of the waiting items of those tenders and of the Home
conversation. `current` answers None as soon as any of that is no longer so, or a covered tender
is gone, archived or Confidential. A Confidential Project is never covered, and a text that names
one is not kept.

Nothing here writes the text: when the Lead writes it, and under which cap, is decided by a
later job (Q13). Until then Home's `summary` is null."""

import json

from qsone.records.project import Records, RecordsError

META = "home_summary"


def _basis(rows: list[dict], waiting: list[dict], covers: list[str]) -> list:
    by_id = {r["project_id"]: r for r in rows}
    shown = [
        [p, *(by_id[p][k] for k in ("state", "stage", "stages", "submission_date"))] for p in covers
    ]
    items = sorted(i["id"] for i in waiting if i["project_id"] is None or i["project_id"] in covers)
    return [shown, items]


def save(
    engineer: Records, text: str, rows: list[dict], waiting: list[dict], *, actor: str
) -> bool:
    """Keeps `text` as the summary of the tenders in `rows` that are not Confidential, as Home
    shows them now (`home.home`'s `tenders` and `waiting`). False, and nothing kept, when the
    text names a Confidential Project."""
    if any(r["confidential"] and r["name"].casefold() in text.casefold() for r in rows):
        return False
    covers = [r["project_id"] for r in rows if not r["confidential"]]
    kept = {
        "text": text,
        "at": engineer.clock(),
        "covers": covers,
        "basis": _basis(rows, waiting, covers),
    }
    with engineer.write(actor) as conn:
        engineer.set_meta(conn, META, json.dumps(kept, ensure_ascii=False))
    return True


def current(engine, rows: list[dict], waiting: list[dict]) -> dict | None:
    """The `HomeSummary` as JSON while it still agrees with `rows` and `waiting`; else None."""
    try:
        saved = engine.engineer_records().meta().get(META)
    except RecordsError:
        return None
    if not saved:
        return None
    kept = json.loads(saved)
    shown = {r["project_id"]: r for r in rows}
    covers = kept["covers"]
    if not covers or any(p not in shown or shown[p]["confidential"] for p in covers):
        return None
    if _basis(rows, waiting, covers) != kept["basis"]:
        return None
    return {"text": kept["text"], "at": kept["at"], "covers": len(covers)}
