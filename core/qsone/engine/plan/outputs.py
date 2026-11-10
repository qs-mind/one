"""What a stage's work made (contract S55): the ids of its outputs and its one-line `result`, which
the plan driver writes when the stage's latest Brief ends done, so route 11 can sign it off.

- A `deliverable` output is a Deliverable one of the stage's Briefs made (any attempt): the one
  whose title is the output's, else the next one made in order.
- A `file` output is a file added to the tender since the stage's first Brief (made by ONE or
  brought by the engineer): the one named as the output, else the next one added.
- `map` and `summary` have no id. An id found once is kept."""

import json

from qsone import copy
from qsone import phase1_contract as c
from qsone.engine import agents
from qsone.engine.plan import claims
from qsone.engine.store import Store
from qsone.records.project import Records

MADE_BY = ("deliverable_create", "pack_propose", "boq_price_from_sheet")  # tools that make one


def _same(title: c.Text, name: str) -> bool:
    name = name.strip().casefold()
    return any(t.strip().casefold() in (name, name.rsplit(".", 1)[0]) for t in (title.en, title.ar))


def _made(rec: Records, brief_ids: list[str]) -> list[str]:
    """The Deliverables these Briefs made, in order, each once."""
    store = Store(rec, project_id=rec.id)
    found: list[str] = []
    for brief_id in brief_ids:
        for run in store.runs(brief_id):
            if not run["history"]:
                continue
            for name, text in agents.tool_returns(run["history"]):
                if name not in MADE_BY:
                    continue
                try:
                    out = json.loads(text)
                except ValueError:
                    continue
                if isinstance(out, dict) and isinstance(out.get("id"), str):
                    found.append(out["id"])
    return list(dict.fromkeys(found))


def _pick(output: c.StageOutput, candidates: list[tuple[str, str]], taken: set[str]) -> str | None:
    free = [(i, name) for i, name in candidates if i not in taken]
    named = next((i for i, name in free if _same(output.title, name)), None)
    return named or (free[0][0] if free else None)


def ids(conn, rec: Records, stage: c.Stage) -> list[str | None]:
    """One id per output, None for one not made (yet)."""
    attempts = claims.every(conn, stage.id)
    if not attempts:
        return [o.id for o in stage.outputs]
    made = _made(rec, [brief_id for brief_id, _ in attempts])
    titles = dict(
        conn.execute(
            "SELECT id, title FROM deliverables WHERE id IN (SELECT value FROM json_each(?))",
            (json.dumps(made),),
        ).fetchall()
    )
    deliverables = [(i, titles[i]) for i in made if i in titles]
    files = conn.execute(
        "SELECT id, name FROM files WHERE valid_until IS NULL AND added_at >= ?"
        " ORDER BY added_at, rowid",
        (attempts[0][1],),
    ).fetchall()
    places = {"deliverable": deliverables, "file": [(i, n) for i, n in files]}
    taken = {o.id for o in stage.outputs if o.id is not None}
    found: list[str | None] = []
    for output in stage.outputs:
        picked = output.id
        if picked is None and output.kind in places:
            picked = _pick(output, places[output.kind], taken)
            if picked is not None:
                taken.add(picked)
        found.append(picked)
    return found


def result(stage: c.Stage, found: list[str | None]) -> dict:
    """The stage's one line, {en, ar}: what was made, then what is not made yet."""
    made, missing = [], []
    for output, i in zip(stage.outputs, found, strict=True):
        ready = i is not None or output.kind in ("map", "summary")
        (made if ready else missing).append(output.title.model_dump())
    if not made and not missing:
        return dict(copy.STAGE_RESULT_ENDED)

    def joined(titles: list[dict]) -> dict:
        return {k: copy.STAGE_JOIN[k].join(t[k] for t in titles) for k in ("en", "ar")}

    lines = []
    if made:
        lines.append(copy.fill(copy.STAGE_RESULT_DONE, made=joined(made)))
    if missing:
        lines.append(copy.fill(copy.STAGE_RESULT_MISSING, missing=joined(missing)))
    return {k: " ".join(line[k] for line in lines) for k in ("en", "ar")}
