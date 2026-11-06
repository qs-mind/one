import json
from decimal import Decimal
from types import SimpleNamespace

import pytest

from qsone.engine import cards, oneshot
from qsone.records import files
from qsone.records.mapping import ai, store
from tests.samples import sample_pdf
from tests.test_project_map import drain


def test_digest_bounded_and_locator_validation(rec):
    f = files.add_file(rec, "sample.pdf", sample_pdf([["Sample conditions"]]), actor="engineer")
    drain(rec)
    digest = ai.digest(rec, f.id)
    assert len(json.dumps(digest, ensure_ascii=False).encode()) <= 8000
    result = ai.FileMap(
        file_id=f.id,
        kind="contract",
        title={"en": "Sample", "ar": "عينة"},
        group="Tender",
        key_pages=[
            {
                "label": {"en": "Data", "ar": "البيانات"},
                "page": 99,
                "why": {"en": "Data", "ar": "البيانات"},
            },
            {
                "label": {"en": "Data", "ar": "البيانات"},
                "page": 1,
                "why": {"en": "Data", "ar": "البيانات"},
            },
        ],
    )
    assert [p["page"] for p in ai.valid_pages(result, digest)] == [1]


def test_batches():
    assert [len(b) for b in ai.batches([{"file_id": str(i)} for i in range(11)])] == [4, 4, 3]


@pytest.mark.anyio
@pytest.mark.parametrize(
    "price,approved,expected_calls", [("0.01", True, 2), ("10", False, 0), ("10", True, 2)]
)
async def test_cost_gate_and_batch(rec, monkeypatch, price, approved, expected_calls):
    f = files.add_file(rec, "sample.pdf", sample_pdf([["Sample data"]]), actor="engineer")
    drain(rec)
    asked = []
    calls = []

    async def ask(card):
        asked.append(card)
        return "yes" if approved else "no"

    monkeypatch.setattr(oneshot, "map_model", lambda _: object())
    monkeypatch.setattr(cards, "cost", lambda *args, **kwargs: Decimal(price))

    async def request(prompt, schema, instructions):
        calls.append(json.loads(prompt))
        if schema is ai.Groups:
            return ai.Groups(groups=[])
        return ai.Batch(
            files=[
                ai.FileMap(
                    file_id=f.id,
                    kind="contract",
                    title={"en": "Sample", "ar": "عينة"},
                    group="Tender",
                )
            ]
        )

    await ai.run(rec, SimpleNamespace(host=SimpleNamespace(ask=ask)), request=request)
    assert len(calls) == expected_calls
    assert len(asked) == (price == "10")
    if asked:
        assert asked[0].kind == "cost" and set(asked[0].title) == {"en", "ar"}
    if expected_calls:
        assert store.detail(rec, f.id)["ai_state"] == "done"
        # A second run must not send the already mapped file.
        assert not await ai.run(rec, SimpleNamespace(), request=request)


@pytest.mark.anyio
async def test_no_ai_stays_local(rec, monkeypatch):
    f = files.add_file(rec, "sample.pdf", sample_pdf([["Sample data"]]), actor="engineer")
    drain(rec)
    monkeypatch.setattr(oneshot, "map_model", lambda _: None)
    assert not await ai.run(rec, None)
    row = store.detail(rec, f.id)
    assert row["local_state"] == "done" and row["ai_state"] == "no_ai"
    assert set(row["note"]) == {"en", "ar"}


@pytest.mark.anyio
async def test_background_entrypoint_no_ai(rec, monkeypatch):
    from qsone.engine.runner import Engine, NoAI

    f = files.add_file(rec, "sample.pdf", sample_pdf([["Sample data"]]), actor="engineer")
    drain(rec)
    engine = object.__new__(Engine)
    monkeypatch.setattr(engine, "active", lambda _: None)
    monkeypatch.setattr(engine, "_place", lambda _: SimpleNamespace(rec=rec))

    async def no_sheet():
        raise NoAI({"en": "No AI", "ar": "مفيش ذكاء اصطناعي"})

    monkeypatch.setattr(engine, "sheet", no_sheet)
    await engine.map_project("sample", [f.id])
    assert store.detail(rec, f.id)["ai_state"] == "no_ai"


@pytest.mark.anyio
async def test_costed_scripted_map(rec, general, fake_clock, data_dir):
    from qsone.engine.costs import Spending
    from qsone.engine.store import CostBook
    from tests.bench.fake import connectors
    from tests.engine_fakes import FakeHost

    found = connectors()
    sheet = [card for link in found for card in await link.cards()]
    models = oneshot.Models(
        sheet=sheet,
        roles={"quick": sheet[1].choice},
        connectors={link.id: link for link in found},
        spending=Spending(CostBook(general), clock=fake_clock),
        host=FakeHost(brief_id="sample"),
        brief_id="sample",
        project_id=rec.id,
        run_id="sample-map",
        work=data_dir / "work",
    )
    f = files.add_file(rec, "sample.pdf", sample_pdf([["Sample conditions"]]), actor="engineer")
    drain(rec)
    assert await ai.run(rec, models)
    assert store.detail(rec, f.id)["key_pages"]
    with general.read() as c:
        assert (
            c.execute("SELECT count(*) FROM ai_costs WHERE run_id=?", ("sample-map",)).fetchone()[0]
            == 2
        )


@pytest.mark.anyio
async def test_replacement_maps_only_changed_file(rec, monkeypatch):
    original = files.add_file(rec, "sample.txt", b"Sample original", actor="engineer")
    other = files.add_file(rec, "other.txt", b"Sample other", actor="engineer")
    drain(rec)
    with rec.write("one") as c:
        for fid in (original.id, other.id):
            store.write(
                c,
                rec,
                "map_files",
                {"file_id": fid, "ai_state": "done", "ai_title": {"en": "Sample", "ar": "عينة"}},
            )
    new = files.add_file(rec, "sample.txt", b"Sample replaced", actor="engineer")
    drain(rec)
    calls = []
    monkeypatch.setattr(oneshot, "map_model", lambda _: object())
    monkeypatch.setattr(cards, "cost", lambda *a, **kw: Decimal("0.01"))

    async def request(prompt, schema, instructions):
        data = json.loads(prompt)
        calls.append((schema, data))
        if schema is ai.Groups:
            return ai.Groups(groups=[])
        return ai.Batch(
            files=[
                ai.FileMap(
                    file_id=new.id,
                    kind="text",
                    title={"en": "Sample replaced", "ar": "عينة بديلة"},
                    group="Tender",
                )
            ]
        )

    await ai.run(rec, SimpleNamespace(), request=request)
    assert [f["file_id"] for f in calls[0][1]] == [new.id]
    assert [f["file_id"] for f in calls[1][1]["files"]] == [new.id]


@pytest.mark.anyio
async def test_2000_files_card_before_any_call(rec, monkeypatch):
    import time

    with rec.write("one") as c:
        c.executemany(
            "INSERT INTO files(id,name,kind,size,sha256,status,added_at,added_by) "
            "VALUES (?,?,'txt',1,?,'stored',?,'engineer')",
            ((str(i), f"Sample {i}", f"hash{i}", rec.clock()) for i in range(2000)),
        )
        c.executemany(
            "INSERT INTO map_files(file_id,kind,local_state) VALUES (?,'txt','done')",
            ((str(i),) for i in range(2000)),
        )
    start = time.monotonic()
    page = store.list_map(rec, limit=20)
    assert time.monotonic() - start < 2
    assert len(page["files"]) == 20 and page["status"]["total"] == 2000
    monkeypatch.setattr(oneshot, "map_model", lambda _: object())
    monkeypatch.setattr(cards, "cost", lambda *a, **kw: Decimal("0.01"))
    asked = []

    async def ask(card):
        asked.append(card)
        return "no"

    async def never(*args):
        raise AssertionError("Unapproved mapping request")

    assert not await ai.run(rec, SimpleNamespace(host=SimpleNamespace(ask=ask)), request=never)
    assert len(asked) == 1 and "2000" in asked[0].detail["en"]


def test_replaced_fact_is_reextracted_unconfirmed(rec):
    from qsone.records.mapping import facts as fact_pass

    old = files.add_file(
        rec, "sample.pdf", sample_pdf([["Sample security 350000 USD"]]), actor="engineer"
    )
    drain(rec)
    with rec.write("one") as c:
        store.write(
            c,
            rec,
            "map_facts",
            {
                "id": "sample-fact",
                "file_id": old.id,
                "name": {"en": "Sample security", "ar": "تأمين العينة"},
                "value": "350000",
                "locator": {"page": 1},
                "state": "found",
                "confirmed_by": "engineer",
                "confirmed_at": rec.clock(),
            },
        )
    unchanged = files.add_file(rec, "other.txt", b"Retention 10%", actor="engineer")
    unchanged_id = fact_pass.accept(
        rec,
        [
            dict(
                name={"en": "Retention", "ar": "المحتجز"},
                value="10%",
                evidence="Retention 10%",
                file_id=unchanged.id,
                locator={"line": 1},
            )
        ],
    )[0]
    fact_pass.update(rec, unchanged_id, confirm=True)
    new = files.add_file(
        rec, "sample.pdf", sample_pdf([["Sample security is still 350000 USD"]]), actor="engineer"
    )
    drain(rec)
    remaining = store.entries(rec, "facts")["facts"]
    assert len(remaining) == 1 and remaining[0]["confirmed_by"] == "engineer"
    fact_pass.accept(
        rec,
        [
            dict(
                name={"en": "Sample security", "ar": "تأمين العينة"},
                value="350000",
                evidence="Sample security is still 350000 USD",
                file_id=new.id,
                locator={"page": 1},
            )
        ],
    )
    facts = [f for f in store.entries(rec, "facts")["facts"] if f["file_id"] == new.id]
    assert len(facts) == 1 and facts[0]["file_id"] == new.id
    assert facts[0]["confirmed_by"] is None
    files.add_file(
        rec, "sample.pdf", sample_pdf([["Sample security is 1350000 USD"]]), actor="engineer"
    )
    drain(rec)
    remaining = store.entries(rec, "facts")["facts"]
    assert len(remaining) == 1 and remaining[0]["id"] == unchanged_id
    assert remaining[0]["confirmed_by"] == "engineer"


@pytest.mark.anyio
async def test_background_brief_records_map_and_finishes(data_dir):
    import asyncio

    from qsone.engine.runner import Engine
    from qsone.projects import Projects
    from tests.bench.fake import connectors

    projects = Projects(data_dir)
    pid = projects.create("Sample map project", "engineer")["id"]
    rec = projects.get(pid)
    f = files.add_file(rec, "sample.pdf", sample_pdf([["Retention 10%"]]), actor="engineer")
    drain(rec)
    engine = Engine(projects=projects, data_dir=data_dir, connectors=connectors)
    try:
        await engine.start()
        await engine.map_project(pid, [f.id])
        brief = engine.active(pid)
        assert brief
        await asyncio.wait_for(engine.result(brief), timeout=10)
        assert store.detail(rec, f.id)["ai_state"] == "done"
        assert engine.active(pid) is None
        mapped_facts = store.entries(rec, "facts")["facts"]
        assert mapped_facts and mapped_facts[0]["value"] == "10%"
        assert mapped_facts[0]["file_id"] == f.id
        assert mapped_facts[0]["locator"] == {"page": 1}
        assert mapped_facts[0]["confirmed_at"] is None
        runs = engine._place(pid).store.runs(brief)
        assert any("files_read" in str(run["history"]) for run in runs)
    finally:
        await engine.shutdown()
        projects.close_all()


def test_map_allowance_setting(data_dir):
    from qsone import settings

    assert settings.map_auto_usd() == Decimal("0.50")
    settings.save_map_auto_usd("0.25")
    assert settings.map_auto_usd() == Decimal("0.25")
    with pytest.raises(ValueError):
        settings.save_map_auto_usd("-1")


@pytest.mark.anyio
async def test_background_cost_card_waits_for_engine_answer(data_dir):
    import asyncio

    from qsone import settings
    from qsone.engine.runner import Engine
    from qsone.projects import Projects
    from tests.bench.fake import connectors

    settings.save_map_auto_usd("0")
    projects = Projects(data_dir)
    pid = projects.create("Sample paid map", "engineer")["id"]
    rec = projects.get(pid)
    f = files.add_file(rec, "sample.pdf", sample_pdf([["Sample conditions"]]), actor="engineer")
    drain(rec)
    engine = Engine(projects=projects, data_dir=data_dir, connectors=connectors)
    try:
        await engine.start()
        await engine.map_project(pid, [f.id])
        brief_id = engine.active(pid)
        brief = engine._briefs[brief_id]
        for _ in range(100):
            if brief.waiting:
                break
            await asyncio.sleep(0.001)
        assert brief.waiting
        card_id, (card, _) = next(iter(brief.waiting.items()))
        assert card.title == {"en": "Project Map", "ar": "خريطة المشروع"}
        assert engine.book.spent(brief_id=brief_id, count_equivalent=True) == 0
        # A pending mapping approval does not occupy the engineer's foreground chat slot.
        assert engine.active(pid, include_mapping=False) is None
        await engine.answer(card_id, "yes")
        await asyncio.wait_for(engine.result(brief_id), timeout=10)
        assert store.detail(rec, f.id)["ai_state"] == "done"
        assert engine.book.spent(brief_id=brief_id, count_equivalent=True) > 0
    finally:
        await engine.shutdown()
        projects.close_all()


@pytest.mark.anyio
@pytest.mark.parametrize("approved", [False, True])
async def test_joined_passes_share_drop_approval(rec, monkeypatch, approved):
    from qsone.records.mapping import facts, links

    f = files.add_file(
        rec,
        "sample.pdf",
        sample_pdf([["Retention 10%. See Clause 14.3"], ["14.3 Payment 30 days"]]),
        actor="engineer",
    )
    drain(rec)
    calls, reads, asks = [], [], []
    monkeypatch.setattr(oneshot, "map_model", lambda _: object())
    monkeypatch.setattr(cards, "cost", lambda *a, **k: Decimal("0.2"))

    async def ask(card):
        asks.append(card)
        return "yes" if approved else "no"

    async def read(fid, loc):
        reads.append((fid, loc))
        return "Retention 10%. See Clause 14.3"

    async def request(prompt, schema, instructions):
        calls.append(schema)
        if schema is ai.Batch:
            return ai.Batch(
                files=[
                    ai.FileMap(
                        file_id=f.id,
                        kind="contract",
                        title={"en": "Sample", "ar": "عينة"},
                        group="Tender",
                        key_pages=[
                            ai.KeyPage(
                                label={"en": "Data", "ar": "بيانات"},
                                page=1,
                                why={"en": "Terms", "ar": "الشروط"},
                            )
                        ],
                    )
                ]
            )
        if schema is ai.Groups:
            return ai.Groups(groups=[])
        if schema is facts.Result:
            return facts.Result(
                facts=[
                    facts.Fact(
                        name={"en": "Retention", "ar": "المحتجز"},
                        value="10%",
                        file_id=f.id,
                        locator={"page": 1},
                        state="found",
                        evidence="Retention 10%",
                    )
                ]
            )
        return links.Result(
            links=[
                links.Link(
                    from_file_id=f.id,
                    from_locator={"page": 1},
                    to_file_id=f.id,
                    to_locator={"page": 2},
                    kind="changes",
                    words={"en": "Sample changes", "ar": "تغييرات العينة"},
                    evidence={"text": "Clause 14.3"},
                )
            ]
        )

    await ai.run(
        rec, SimpleNamespace(host=SimpleNamespace(ask=ask)), request=request, passes={"read": read}
    )
    assert len(asks) == 1
    assert len(calls) == (4 if approved else 0)
    assert bool(reads) == approved
    assert bool(store.entries(rec, "facts")["facts"]) == approved

    assert any(r["by"] == "ai" for r in store.entries(rec, "links")["links"]) == approved


@pytest.mark.anyio
async def test_failed_ai_keeps_local_reason_and_retries_only_once(rec, monkeypatch):
    f = files.add_file(rec, "sample.txt", b"Sample conditions", actor="engineer")
    drain(rec)
    monkeypatch.setattr(oneshot, "map_model", lambda _: object())
    monkeypatch.setattr(cards, "cost", lambda *a, **kw: Decimal("0.01"))
    calls = []

    async def fail(*args):
        calls.append(1)
        raise RuntimeError("private source text must never appear")

    assert not await ai.run(rec, SimpleNamespace(), request=fail)
    detail = store.detail(rec, f.id)
    assert detail["ai_state"] == "failed" and detail["local_state"] == "done"
    assert set(detail["note"]) == {"en", "ar"}
    assert store.list_map(rec)["files"][0]["note"] == detail["note"]
    assert "private source" not in str(detail["note"])
    assert "could not map 1 files with the AI" in store.list_map(rec)["status"]["line"]["en"]
    await ai.run(rec, SimpleNamespace(), request=fail)
    await ai.run(rec, SimpleNamespace(), request=fail)
    assert len(calls) == 2


@pytest.mark.anyio
async def test_groups_chunks_receive_previous_paths(rec, monkeypatch):
    with rec.write("one") as c:
        c.executemany(
            "INSERT INTO files(id,name,kind,size,sha256,status,added_at,added_by) "
            "VALUES (?,?,'txt',1,?,'stored',?,'engineer')",
            ((f"{i:03}", f"Sample {i}", f"hash{i}", rec.clock()) for i in range(250)),
        )
        c.executemany(
            "INSERT INTO map_files(file_id,kind,local_state) VALUES (?,'txt','done')",
            ((f"{i:03}",) for i in range(250)),
        )
    monkeypatch.setattr(oneshot, "map_model", lambda _: object())
    monkeypatch.setattr(cards, "cost", lambda *a, **kw: Decimal("0"))
    groups = []

    async def request(prompt, schema, instructions):
        data = json.loads(prompt)
        if schema is ai.Groups:
            groups.append(data)
            return ai.Groups(
                groups=[ai.Group(file_id=data["files"][0]["file_id"], path="Electrical/Power")]
            )
        return ai.Batch(
            files=[
                ai.FileMap(
                    file_id=f["file_id"],
                    kind="text",
                    title={"en": "Sample", "ar": "عينة"},
                    group="Tender",
                )
                for f in data
            ]
        )

    await ai.run(rec, SimpleNamespace(), request=request)
    assert [len(g["files"]) for g in groups] == [100, 100, 50]
    assert "Electrical/Power" in groups[1]["existing_groups"]
    assert "Electrical/Power" in groups[2]["existing_groups"]


@pytest.mark.anyio
async def test_group_failure_retries_without_reclassifying(rec, monkeypatch):
    f = files.add_file(rec, "sample.txt", b"Sample conditions", actor="engineer")
    drain(rec)
    monkeypatch.setattr(oneshot, "map_model", lambda _: object())
    monkeypatch.setattr(cards, "cost", lambda *a, **kw: Decimal("0"))
    calls = []

    async def request(prompt, schema, instructions):
        calls.append(schema)
        if schema is ai.Batch:
            return ai.Batch(
                files=[
                    ai.FileMap(
                        file_id=f.id,
                        kind="text",
                        title={"en": "Sample", "ar": "عينة"},
                        group="Tender",
                    )
                ]
            )
        if calls.count(ai.Groups) == 1:
            raise RuntimeError("provider unavailable")
        return ai.Groups(groups=[])

    await ai.run(rec, SimpleNamespace(), request=request)
    assert store.detail(rec, f.id)["ai_state"] == "failed"
    await ai.run(rec, SimpleNamespace(), request=request)
    assert store.detail(rec, f.id)["ai_state"] == "done"
    assert calls.count(ai.Batch) == 1 and calls.count(ai.Groups) == 2


@pytest.mark.anyio
async def test_existing_duplicate_is_never_sent_to_ai(rec, monkeypatch):
    first = files.add_file(rec, "sample.txt", b"Sample conditions", actor="engineer")
    drain(rec)
    with rec.write("one") as c:
        store.write(c, rec, "map_files", {"file_id": first.id, "ai_state": "done"})
        c.execute(
            "INSERT INTO files(id,name,kind,size,sha256,status,added_at,added_by) "
            "SELECT 'copy','copy.txt',kind,size,sha256,status,added_at,added_by "
            "FROM files WHERE id=?",
            (first.id,),
        )
        store.enqueue(c, rec, "copy", "txt", None)
        store.write(c, rec, "map_files", {"file_id": "copy", "local_state": "done"})

    async def never(*args):
        raise AssertionError("Duplicate sent to AI")

    monkeypatch.setattr(
        oneshot, "map_model", lambda _: (_ for _ in ()).throw(AssertionError("AI consulted"))
    )
    assert not await ai.run(rec, SimpleNamespace(), request=never)
    assert store.detail(rec, "copy")["ai_state"] == "local"


@pytest.mark.anyio
async def test_links_retry_keeps_successful_groups_facts_and_link_batches(rec, monkeypatch):
    from collections import Counter

    from qsone.records.mapping import facts, links

    for i in range(9):
        files.add_file(
            rec, f"sample{i}.txt", f"Retention 10% sample {i}".encode(), actor="engineer"
        )
    drain(rec)
    monkeypatch.setattr(oneshot, "map_model", lambda _: object())
    monkeypatch.setattr(cards, "cost", lambda *a, **kw: Decimal("0"))
    calls = Counter()
    link_inputs = []
    reads = []

    async def read(fid, loc):
        reads.append(fid)
        return "Retention 10%"

    async def request(prompt, schema, instructions):
        calls[schema] += 1
        if schema is ai.Batch:
            return ai.Batch(
                files=[
                    ai.FileMap(
                        file_id=d["file_id"],
                        kind="text",
                        title={"en": "Sample", "ar": "عينة"},
                        group="Tender",
                    )
                    for d in json.loads(prompt)
                ]
            )
        if schema is ai.Groups:
            return ai.Groups(groups=[])
        if schema is facts.Result:
            pages = json.loads(prompt.split("\n", 1)[1])
            return facts.Result(
                facts=[
                    facts.Fact(
                        name={"en": "Retention", "ar": "المحتجز"},
                        value="10%",
                        source_label="Retention",
                        file_id=p["file_id"],
                        locator=p["locator"],
                        state="found",
                        evidence="Retention 10%",
                    )
                    for p in pages
                ]
            )
        batch = json.loads(prompt.split("\n", 1)[1])
        link_inputs.append([d["file_id"] for d in batch])
        if calls[links.Result] == 2:
            raise RuntimeError("sample interruption")
        return links.Result(links=[])

    await ai.run(rec, SimpleNamespace(), request=request, passes={"read": read})
    first_reads = list(reads)
    await ai.run(rec, SimpleNamespace(), request=request, passes={"read": read})
    assert calls == {ai.Batch: 3, ai.Groups: 1, facts.Result: 1, links.Result: 4}
    assert reads == first_reads
    assert link_inputs[2] == link_inputs[1]
    assert all(row["ai_state"] == "done" for row in store.list_map(rec)["files"])


@pytest.mark.anyio
async def test_links_never_receive_failed_classification(rec, monkeypatch):
    from qsone.records.mapping import facts, links

    for i in range(5):
        files.add_file(
            rec, f"sample{i}.txt", f"Retention 10% sample {i}".encode(), actor="engineer"
        )
    drain(rec)
    monkeypatch.setattr(oneshot, "map_model", lambda _: object())
    monkeypatch.setattr(cards, "cost", lambda *a, **kw: Decimal("0"))
    failed_ids = set()
    link_ids = set()

    async def read(fid, loc):
        return "Retention 10%"

    async def request(prompt, schema, instructions):
        if schema is ai.Batch:
            data = json.loads(prompt)
            if not failed_ids:
                failed_ids.update(d["file_id"] for d in data)
                raise RuntimeError("sample interruption")
            return ai.Batch(
                files=[
                    ai.FileMap(
                        file_id=d["file_id"],
                        kind="text",
                        title={"en": "Sample", "ar": "عينة"},
                        group="Tender",
                    )
                    for d in data
                ]
            )
        if schema is ai.Groups:
            return ai.Groups(groups=[])
        if schema is facts.Result:
            pages = json.loads(prompt.split("\n", 1)[1])
            return facts.Result(
                facts=[
                    facts.Fact(
                        name={"en": "Retention", "ar": "المحتجز"},
                        value="10%",
                        source_label="Retention",
                        file_id=p["file_id"],
                        locator=p["locator"],
                        state="found",
                        evidence="Retention 10%",
                    )
                    for p in pages
                ]
            )
        link_ids.update(d["file_id"] for d in json.loads(prompt.split("\n", 1)[1]))
        return links.Result(links=[])

    await ai.run(rec, SimpleNamespace(), request=request, passes={"read": read})
    assert link_ids and not link_ids & failed_ids


@pytest.mark.anyio
async def test_invalid_batch_isolated_and_missing_title_falls_back(rec, monkeypatch):
    from pydantic import ValidationError

    for n in range(2):
        files.add_file(rec, f"sample{n}.txt", f"Sample heading {n}".encode(), actor="engineer")
    drain(rec)
    monkeypatch.setattr(oneshot, "map_model", lambda _: object())
    monkeypatch.setattr(cards, "cost", lambda *a, **kw: Decimal("0"))
    calls = []

    async def request(prompt, schema, instructions):
        if schema is ai.Groups:
            return ai.Groups(groups=[])
        data = json.loads(prompt)
        calls.append(len(data))
        if len(data) > 1:
            raise ValidationError.from_exception_data("Batch", [])
        return ai.Batch.model_validate(
            {
                "files": [
                    dict(
                        file_id=data[0]["file_id"],
                        kind="text",
                        group="Tender",
                        title={"en": "", "ar": ""},
                    )
                ]
            }
        )

    await ai.run(rec, SimpleNamespace(), request=request)
    assert calls == [2, 1, 1]
    assert all(
        f["ai_state"] == "done" and f["ai_title"]["en"] for f in store.list_map(rec)["files"]
    )


@pytest.mark.anyio
async def test_timeout_has_plain_bilingual_cause(rec, monkeypatch):
    f = files.add_file(rec, "sample.txt", b"Sample", actor="engineer")
    drain(rec)
    monkeypatch.setattr(oneshot, "map_model", lambda _: object())
    monkeypatch.setattr(cards, "cost", lambda *a, **kw: Decimal("0"))

    async def request(*args):
        raise TimeoutError("private text")

    await ai.run(rec, SimpleNamespace(), request=request)
    assert "timed out" in store.detail(rec, f.id)["note"]["en"]


@pytest.mark.anyio
async def test_groups_bilingual_reuse_and_keep_engineer_folder(rec, monkeypatch):
    with rec.write("engineer") as c:
        rec.set_meta(c, "name", "Sample project")
    a = files.add_file(
        rec, "a.txt", b"Sample a", folder="001 Sample project/01 المستلم", actor="engineer"
    )
    b = files.add_file(
        rec, "b.txt", b"Sample b", folder="001 Sample project/01 المستلم", actor="engineer"
    )
    drain(rec)
    monkeypatch.setattr(oneshot, "map_model", lambda _: object())
    monkeypatch.setattr(cards, "cost", lambda *a, **kw: Decimal("0"))

    async def request(prompt, schema, instructions):
        if schema is ai.Groups:
            return ai.Groups(
                groups=[
                    ai.Group(
                        file_id=a.id, path={"en": "Project Documentation", "ar": "مستندات المشروع"}
                    ),
                    ai.Group(
                        file_id=b.id, path={"en": "project_documentation", "ar": "مستندات المشروع"}
                    ),
                ]
            )
        return ai.Batch(
            files=[
                ai.FileMap(
                    file_id=d["file_id"],
                    kind="text",
                    title={"en": "Sample", "ar": "عينة"},
                    group="Tender",
                )
                for d in json.loads(prompt)
            ]
        )

    await ai.run(rec, SimpleNamespace(), request=request)
    group = store.list_map(rec, parent="01 المستلم")["groups"]
    assert len(group) == 1
    assert group[0]["label"] == {"en": "Project Documentation", "ar": "مستندات المشروع"}
    assert group[0]["count"] == 2


def test_engineer_folder_is_not_mistaken_for_dropped_root(rec):
    f = files.add_file(rec, "sample.txt", b"Sample", folder="01 المستلم/عقود", actor="engineer")
    assert (
        ai._group_patch(rec, f.id, ai.Text(en="Conditions", ar="الشروط"))["ai_group"]
        == "01 المستلم/عقود/Conditions"
    )


@pytest.mark.anyio
async def test_wrapped_timeout_keeps_specific_cause(rec, monkeypatch):
    from qsone import copy

    f = files.add_file(rec, "sample.txt", b"Sample", actor="engineer")
    drain(rec)
    monkeypatch.setattr(oneshot, "map_model", lambda _: object())
    monkeypatch.setattr(cards, "cost", lambda *a, **kw: Decimal("0"))

    async def request(*args):
        try:
            raise TimeoutError("private text")
        except TimeoutError:
            raise oneshot.OneShotFailed(copy.MAP_AI_FAILED_REASON) from None

    await ai.run(rec, SimpleNamespace(), request=request)
    assert "timed out" in store.detail(rec, f.id)["note"]["en"]


def test_request_too_large_has_plain_reason(rec):
    import httpx

    f = files.add_file(rec, "sample.txt", b"Sample", actor="engineer")
    drain(rec)
    response = httpx.Response(413, request=httpx.Request("POST", "https://sample.invalid"))
    ai._failed(
        rec,
        [f.id],
        httpx.HTTPStatusError("private text", request=response.request, response=response),
    )
    assert "too large" in store.detail(rec, f.id)["note"]["en"]


@pytest.mark.anyio
async def test_model_slice_yields_only_to_matching_active_model(monkeypatch):
    agent = SimpleNamespace(model="foreground-model", state="thinking")
    brief = SimpleNamespace(
        finished=False, mapping_files=None, state="running", agents={"run": agent}
    )
    models = SimpleNamespace(host=SimpleNamespace(engine=SimpleNamespace(_briefs={"brief": brief})))
    slept = []

    async def sleep(seconds):
        slept.append(seconds)
        brief.state = "waiting_engineer"

    monkeypatch.setattr(ai.asyncio, "sleep", sleep)
    await ai._wait_for_model(models, SimpleNamespace(choice=SimpleNamespace(model="other-model")))
    assert not slept
    await ai._wait_for_model(
        models, SimpleNamespace(choice=SimpleNamespace(model="foreground-model"))
    )
    assert slept == [0.05]


@pytest.mark.anyio
@pytest.mark.parametrize("enrichment,expected", [(False, "0.80"), (True, "2.40")])
async def test_drop_estimate_reserves_validation_retry(rec, monkeypatch, enrichment, expected):
    files.add_file(rec, "sample.txt", b"Sample contract data", actor="engineer")
    drain(rec)
    asked = []

    async def ask(card):
        asked.append(card)
        return "no"

    async def request(*args):
        pytest.fail("approval declined")

    monkeypatch.setattr(oneshot, "map_model", lambda _: object())
    # Two passes at $0.20 each: one request each is below $0.50, reserving
    # one validation retry each must trigger approval at $0.80.
    monkeypatch.setattr(cards, "cost", lambda *a, **kw: Decimal("0.20"))
    assert not await ai.run(
        rec,
        SimpleNamespace(host=SimpleNamespace(ask=ask)),
        request=request,
        passes={} if enrichment else None,
    )
    assert len(asked) == 1
    assert expected in asked[0].detail["en"]


@pytest.mark.anyio
async def test_missing_batch_file_retried_alone(rec, monkeypatch):
    from qsone.records.extract import Extracted, Piece
    from tests.samples import sample_docx, sample_xls

    original_extract = files.extract

    def extract(name, data):
        if name.endswith(".pptx"):
            return Extracted(
                "pptx", "read", None, [Piece({"slide": 1}, "Sample presentation")], None
            )
        if name.endswith(".docx"):
            return Extracted(
                "docx", "read", None, [Piece({"paragraph": 1}, "Sample document")], None
            )
        return original_extract(name, data)

    monkeypatch.setattr(files, "extract", extract)
    fs = [
        files.add_file(rec, "sample.pptx", b"Sample presentation fixture", actor="engineer"),
        files.add_file(
            rec, "sample.docx", sample_docx([("p", "Sample document")]), actor="engineer"
        ),
        files.add_file(
            rec,
            "sample.xls",
            sample_xls({f"Sample {i}": [["Sample", i]] for i in range(19)}),
            actor="engineer",
        ),
    ]
    drain(rec)
    monkeypatch.setattr(oneshot, "map_model", lambda _: object())
    monkeypatch.setattr(cards, "cost", lambda *a, **k: Decimal("0.001"))
    batches_seen = []

    async def request(prompt, schema, instructions):
        if schema is ai.Groups:
            return ai.Groups(groups=[])
        batch = json.loads(prompt)
        batches_seen.append([d["file_id"] for d in batch])
        chosen = batch[:-1] if len(batch) > 1 else batch
        return ai.Batch(
            files=[
                ai.FileMap(file_id=d["file_id"], kind="contract", group="Tender") for d in chosen
            ]
        )

    await ai.run(rec, SimpleNamespace(), request=request)
    assert len(batches_seen) == 2
    assert batches_seen[1] == [batches_seen[0][-1]]
    assert all(store.detail(rec, f.id)["ai_state"] == "done" for f in fs)


def test_nonpage_locators():
    text = {"en": "Sample", "ar": "عينة"}
    for key in ("slide", "paragraph"):
        result = ai.FileMap(
            file_id="sample",
            kind="contract",
            group=text,
            key_pages=[{"label": text, "why": text, key: 2}],
        )
        source = {
            "pages": None,
            "sheets": [],
            "drawing_sheets": [],
            "positions": [{key: 2}],
            "key_page_candidates": [],
        }
        assert ai.valid_pages(result, source)[0][key] == 2


@pytest.mark.anyio
async def test_vision_is_in_drop_estimate_before_any_image_leaves(rec, monkeypatch):
    from qsone.records.mapping import picture

    f = files.add_file(rec, "sample.pdf", sample_pdf([["Validity 01 days"]]), actor="engineer")
    drain(rec)
    monkeypatch.setattr(oneshot, "map_model", lambda _: object())
    priced = []

    def price(card, *, input_tokens, output_tokens):
        priced.append((input_tokens, output_tokens))
        return Decimal("1")

    monkeypatch.setattr(cards, "cost", price)
    asked = []

    async def ask(card):
        asked.append(card)
        return "no"

    async def forbidden(*args):
        pytest.fail("Declined drop must not send text or images")

    await ai.run(
        rec,
        SimpleNamespace(host=SimpleNamespace(ask=ask)),
        request=forbidden,
        vision_request=forbidden,
        passes={"read": forbidden},
    )
    assert (picture.MAX_FACTS * picture.IMAGE_TOKENS + 2000, picture.MAX_FACTS * 100) in priced
    assert len(asked) == 1
    assert store.detail(rec, f.id)["ai_state"] == "declined"
