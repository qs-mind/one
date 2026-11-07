import json
from types import SimpleNamespace

from qsone.engine import oneshot
from qsone.records import files
from qsone.records.mapping import ai, facts, store
from tests.samples import sample_pdf
from tests.test_project_map import drain


async def test_two_local_waves_one_approval(rec, monkeypatch):
    first = files.add_file(rec, "first.txt", b"Sample first", actor="engineer")
    drain(rec)
    rest = [
        files.add_file(rec, f"{n}.txt", f"Sample {n}".encode(), actor="engineer") for n in range(2)
    ]
    asked, batches, passes = [], [], []
    monkeypatch.setattr(oneshot, "map_model", lambda _: object())
    monkeypatch.setattr(ai, "estimate_cost", lambda *a, **kw: None)

    async def ask(card):
        asked.append(card)
        return "yes"

    async def request(prompt, schema, instructions):
        if schema is ai.Batch:
            ids = [d["file_id"] for d in json.loads(prompt)]
            batches.append(ids)
            return schema(files=[dict(file_id=fid, kind="text", group="Sample") for fid in ids])
        return schema(groups=[])

    async def enrichment(*args, **kwargs):
        passes.append(kwargs.get("file_ids"))

    monkeypatch.setattr(facts, "run_approved", enrichment)
    monkeypatch.setattr("qsone.records.mapping.links.run_approved", enrichment)
    models = SimpleNamespace(host=SimpleNamespace(ask=ask))
    assert not await ai.run(rec, models, request=request, passes={"read": None})
    assert not asked and not batches
    drain(rec)
    assert await ai.run(rec, models, request=request, passes={"read": None})
    assert len(asked) == 1 and set(batches[0]) == {first.id, *(f.id for f in rest)}
    assert passes[0] == {first.id, *(f.id for f in rest)}
    assert not await ai.run(rec, models, request=request)
    added = files.add_file(rec, "later.txt", b"Sample later", actor="engineer")
    drain(rec)
    assert await ai.run(rec, models, request=request)
    assert len(asked) == 2 and batches[-1] == [added.id]


def test_normalized_facts_are_idempotent(rec):
    f = files.add_file(rec, "sample.pdf", sample_pdf([["Retention 10%"]]), actor="engineer")
    p = dict(
        file_id=f.id,
        locator={"page": 1},
        name={"en": "Retention", "ar": "الاستقطاع"},
        value="10%",
        evidence="Retention 10%",
        source_label="Retention",
    )
    assert facts.accept(rec, [p], picture_fallback=False)
    changed = dict(p, name={"en": " RETENTION ", "ar": "استقطاع"}, value="١٠٪")
    assert not facts.accept(rec, [changed], picture_fallback=False)
    changed = dict(p, name={"en": "Retained amount", "ar": "مبلغ الاستقطاع"})
    assert not facts.accept(rec, [changed], picture_fallback=False)
    assert len(store.entries(rec, "facts")["facts"]) == 1


async def test_facts_pass_twice(rec):
    f = files.add_file(rec, "sample.pdf", sample_pdf([["Retention 10%"]]), actor="engineer")

    async def read(*args):
        return "Retention 10%"

    calls = 0

    async def request(prompt, schema, instructions):
        nonlocal calls
        calls += 1
        return schema(
            facts=[
                dict(
                    file_id=f.id,
                    locator={"page": 1},
                    name={"en": "Retention" if calls == 1 else " RETENTION ", "ar": "الاستقطاع"},
                    value="10%",
                    evidence="Retention 10%",
                    state="found",
                )
            ]
        )

    for _ in range(2):
        await facts.run_approved(rec, read=read, request=request, file_ids={f.id})
    assert calls == 2
    assert len(store.entries(rec, "facts")["facts"]) == 1


def test_legacy_equal_facts_are_superseded(rec):
    f = files.add_file(rec, "sample.pdf", sample_pdf([["Retention 10%"]]), actor="engineer")
    p = dict(
        file_id=f.id,
        locator={"page": 1},
        name={"en": "Retention", "ar": "الاستقطاع"},
        value="10%",
        evidence="Retention 10%",
    )
    original = facts.accept(rec, [p], picture_fallback=False)[0]
    with rec.write(store.ACTOR) as c:
        store.write(c, rec, "map_facts", dict(p, id="legacy", state="found"))
    assert not facts.accept(rec, [p], picture_fallback=False)
    assert [r["id"] for r in store.entries(rec, "facts")["facts"]] == [original]
    with rec.read() as c:
        assert c.execute("SELECT valid_until FROM map_facts WHERE id='legacy'").fetchone()[0]
