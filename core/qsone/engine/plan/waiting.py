"""What Home and the tender's side column read from the plan and the Findings: the plan as
`TenderPlan` JSON (`home.plan_reader`) and the durable waiting items (`home.waiting_readers`):
a proposed plan, a stage to sign off, a Suggested change, the raised Finding. `install()` is
called once when the app is made."""

from __future__ import annotations

import json

from qsone import copy, home
from qsone.engine.plan import store
from qsone.records.project import Records


def plan(rec: Records) -> dict | None:
    found = store.current(rec)
    return None if found is None else found.model_dump(mode="json")


def _filled(pair: dict, **values: dict) -> dict:
    return {lang: pair[lang].format(**{k: v[lang] for k, v in values.items()}) for lang in pair}


def plan_items(rec: Records) -> list[dict]:
    with rec.read() as conn:
        body = store._body(conn)
        at = conn.execute(f"SELECT at FROM {store.TABLE} ORDER BY rev DESC LIMIT 1").fetchone()
    if body is None:
        return []
    found, since = body["plan"], at[0]
    if found["status"] == "proposed":
        return [home.item("plan", found["id"], rec.id, copy.WAITING_PLAN, since)]
    items = [
        home.item("stage", s["id"], rec.id, _filled(copy.WAITING_STAGE, stage=s["title"]), since)
        for s in found["stages"]
        if s["status"] == "waiting_engineer"
    ]
    if found.get("change") is not None:
        items.append(home.item("plan_change", found["id"], rec.id, copy.WAITING_PLAN_CHANGE, since))
    return items


def finding_items(rec: Records) -> list[dict]:
    with rec.read() as conn:
        rows = conn.execute(
            "SELECT id, title, raised_at FROM findings WHERE status = 'raised'"
        ).fetchall()
    return [home.item("decision", i, rec.id, json.loads(title), at) for i, title, at in rows]


def install() -> None:
    home.plan_reader = plan
    for read in (plan_items, finding_items):
        if read not in home.waiting_readers:
            home.waiting_readers.append(read)
