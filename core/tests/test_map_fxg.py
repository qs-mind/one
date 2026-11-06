import json
from types import SimpleNamespace

import pytest

from qsone.records import files
from qsone.records.mapping import ai, facts, store
from qsone.tools.project_map import MapArgs, read_map
from tests.test_project_map import drain


def test_local_key_pages_survive_ai_omission(rec):
    f = files.add_file(
        rec,
        "sample.txt",
        "فتح العروض 16/04/1448\nالترسية 29/06/1448\nبدء الأعمال 07/07/1448".encode(),
        actor="engineer",
    )
    drain(rec)
    source = ai.digest(rec, f.id)
    assert source["key_page_candidates"]
    result = ai.FileMap(file_id=f.id, kind="conditions", group="Tender", key_pages=[])
    assert ai.valid_pages(result, source)


@pytest.mark.anyio
async def test_project_sheets_and_filtered_counts(rec):
    f = files.add_file(rec, "MAIN POWER SINGLE LINE DIAGRAM.dwg", b"sample", actor="engineer")
    with rec.write("one") as c:
        for n in (505, 504):
            store.write(
                c,
                rec,
                "map_sheets",
                dict(
                    file_id=f.id,
                    sheet=f"SLD{n}",
                    number=f"EL-{n}",
                    title="Main single line diagram",
                    counts={"MCCB": 3, "Other": 8},
                    source={"layout": f"SLD{n}"},
                ),
            )
    ctx = SimpleNamespace(rec=rec)
    result = json.loads(await read_map(ctx, MapArgs(mode="sheets", limit=1)))
    assert result["sheets"][0]["number"] == "EL-504"
    assert result["sheets"][0]["file"] == f.name
    assert result["next_page"] == 2
    result = json.loads(await read_map(ctx, MapArgs(mode="counts", label="mccb", limit=1)))
    assert result["project_total"] == 6
    assert result["counts"][0]["file_id"] == f.id
    assert result["file_totals"][f.id] == 6


def test_dropped_wrapper_and_repeated_folder(rec):
    f = files.add_file(
        rec, "sample.txt", b"sample", folder="Dropped pack/01 المستلم", actor="engineer"
    )
    patch = ai._group_patch(rec, f.id, ai.Text(en="01 المستلم/Tender", ar="01 المستلم/المناقصة"))
    assert patch["ai_group"] == "01 المستلم/Tender"


@pytest.mark.anyio
async def test_empty_facts_is_explicit_failure(rec):
    f = files.add_file(rec, "sample.txt", b"Bid validity 90 days", actor="engineer")
    drain(rec)

    async def read(*args):
        return "Bid validity 90 days"

    async def request(*args):
        return facts.Result(facts=[])

    with pytest.raises(ValueError, match="NoTenderFacts"):
        await facts.run_approved(rec, read=read, request=request, file_ids={f.id})


def test_role_and_silent_retry():
    from qsone.engine import truth
    from qsone.records.mapping.roles import file_role

    assert file_role("pack/01 المستلم", "conditions")["en"] == "Received tender document"
    assert file_role("pack/02 الفني/P6 programme", "programme")["en"].startswith("Our")
    from qsone.engine.truth import Brief

    problems = truth.reply_problems(
        "ده المستند (Document)", cov=None, did=Brief(), engineer_text="هات المستند"
    )
    retry = next(p for p in problems if p.kind == "english")
    assert "silently" in retry.fix and "no apology" in retry.fix


@pytest.mark.anyio
async def test_arabic_real_shaped_facts_keep_three_dates_and_sources(rec):
    from tests.samples import sample_pdf

    text = {
        2: (
            "ضمان ابتدائي بقيمة تتراوح من (1%) إلى (2%) من قيمة العرض "
            "ساري المفعول لمدة 90 يوم (من تاريخ فتح المظاريف)"
        ),
        3: "مدة سريان العروض تسعين يوماً",
        7: "فتح العروض 16/04/1448\nالترسية 29/06/1448\nبدء الأعمال 07/07/1448",
    }
    f = files.add_file(
        rec,
        "sample-conditions.pdf",
        sample_pdf([["Sample page"] for _ in range(7)]),
        actor="engineer",
    )
    drain(rec)
    with rec.write("one") as c:
        for page, words in text.items():
            c.execute(
                "UPDATE chunks SET text=? WHERE file_id=? AND json_extract(locator,'$.page')=?",
                (words, f.id, page),
            )

    async def read(fid, locator):
        return text.get(locator["page"], "")

    async def request(prompt, schema, instructions):
        pages = json.loads(prompt.split("\n", 1)[1])
        assert {p["locator"]["page"] for p in pages} >= {2, 3, 7}
        proposals = []
        for label, en, value, page in [
            ("ضمان ابتدائي", "Bid security", "(1%) إلى (2%)", 2),
            ("مدة سريان العروض", "Bid validity", "تسعين يوماً", 3),
            ("فتح العروض", "Offer opening", "16/04/1448", 7),
            ("الترسية", "Award", "29/06/1448", 7),
            ("بدء الأعمال", "Commencement", "07/07/1448", 7),
        ]:
            proposals.append(
                facts.Fact(
                    name={"en": en, "ar": label},
                    source_label=label,
                    value=value,
                    file_id=f.id,
                    locator={"page": page},
                    state="found",
                    evidence=text[page],
                )
            )
        return facts.Result(facts=proposals)

    assert len(await facts.run_approved(rec, read=read, request=request, file_ids={f.id})) == 5
    assert {r["locator"]["page"] for r in store.entries(rec, "facts")["facts"]} == {2, 3, 7}


def test_fragmented_groups_are_bounded_within_folder(rec):
    ids = []
    for n in range(12):
        f = files.add_file(
            rec, f"sample-{n}.txt", f"Sample {n}".encode(), folder="01 المستلم", actor="engineer"
        )
        ids.append(f.id)
        with rec.write("one") as c:
            store.write(
                c,
                rec,
                "map_files",
                {
                    "file_id": f.id,
                    **ai._group_patch(rec, f.id, ai.Text(en=f"Subject {n}", ar=f"موضوع {n}")),
                },
            )
    ai.bound_groups(rec, ids)
    assert 2 <= len(store.list_map(rec, parent="01 المستلم")["groups"]) <= 6


def test_facts_do_not_take_tender_duration_from_our_programme(rec):
    tender = files.add_file(
        rec,
        "sample-tender.txt",
        b"Contract duration 120 days",
        folder="01 المستلم",
        actor="engineer",
    )
    ours = files.add_file(
        rec,
        "sample-programme.txt",
        b"Contract duration 90 days",
        folder="02 الفني/P6 programme",
        actor="engineer",
    )
    drain(rec)
    selected = facts.candidates(rec)
    assert {p["file_id"] for p in selected} == {tender.id}
    assert ours.id not in {p["file_id"] for p in selected}


@pytest.mark.anyio
async def test_scripted_model_lists_all_sheets_and_mccb_with_file_source(rec):
    from pydantic_ai import Agent
    from pydantic_ai.messages import ModelRequest, ToolReturnPart

    from tests.engine_fakes import call, scripted

    f = files.add_file(rec, "sample-main-single-line.dwg", b"sample", actor="engineer")
    with rec.write("one") as c:
        for n, title, counts in [
            (501, "Lighting", {}),
            (502, "Power", {}),
            (504, "Main single line diagram", {"MCCB": 7}),
        ]:
            store.write(
                c,
                rec,
                "map_sheets",
                dict(
                    file_id=f.id,
                    sheet=f"SLD{n}",
                    number=f"EL-{n}",
                    title=title,
                    discipline="electrical",
                    counts=counts,
                    source={"layout": f"SLD{n}"},
                ),
            )

    def answer(messages, info):
        returns = [
            json.loads(p.content)
            for m in messages
            if isinstance(m, ModelRequest)
            for p in m.parts
            if isinstance(p, ToolReturnPart)
        ]
        sheets, counts = returns
        assert [s["number"] for s in sheets["sheets"]] == ["EL-501", "EL-502", "EL-504"]
        source = counts["counts"][0]
        return (
            "; ".join(s["number"] + ": " + s["title"] for s in sheets["sheets"])
            + f"; MCCB {counts['project_total']} (source: {source['file']}, {source['number']})"
        )

    model = scripted(
        call("project_map", {"mode": "sheets"}),
        call("project_map", {"mode": "counts", "label": "mccb"}),
        answer,
    )
    agent = Agent(model)

    @agent.tool_plain
    async def project_map(mode: str, label: str | None = None) -> str:
        return await read_map(SimpleNamespace(rec=rec), MapArgs(mode=mode, label=label))

    result = await agent.run("List electrical sheets with number/title and MCCB in the main SLD.")
    assert "EL-504: Main single line diagram" in result.output
    assert "MCCB 7 (source: sample-main-single-line.dwg, EL-504)" in result.output


@pytest.mark.anyio
async def test_facts_failure_is_recorded_and_links_do_not_run(rec, monkeypatch):
    from decimal import Decimal

    from qsone import copy
    from qsone.engine import cards, oneshot
    from qsone.records.mapping import links

    f = files.add_file(rec, "sample.txt", b"Bid validity 90 days", actor="engineer")
    drain(rec)
    monkeypatch.setattr(oneshot, "map_model", lambda _: object())
    monkeypatch.setattr(cards, "cost", lambda *a, **kw: Decimal("0"))

    async def read(*args):
        return "Bid validity 90 days"

    async def request(prompt, schema, instructions):
        assert schema is not links.Result
        if schema is facts.Result:
            return facts.Result(facts=[])
        if schema is ai.Groups:
            return ai.Groups(groups=[])
        return ai.Batch(files=[ai.FileMap(file_id=f.id, kind="conditions", group="Tender")])

    await ai.run(rec, SimpleNamespace(), request=request, passes={"read": read})
    row = store.detail(rec, f.id)
    assert row["ai_state"] == "done" and row["note"] is None
    status = store.list_map(rec)["status"]
    assert status["ai_failed"] == 0
    assert status["passes"]["facts"]["state"] == "failed"
    assert status["passes"]["facts"]["attempts"] == 2
    assert status["passes"]["facts"]["note"] == copy.MAP_FACTS_EMPTY
    assert "Tender facts" in status["line"]["en"]


def test_amount_table_is_a_local_key_candidate(rec):
    f = files.add_file(
        rec, "sample.txt", b"Sample table\n100,000 SAR\n200,000 SAR", actor="engineer"
    )
    drain(rec)
    assert ai.local_key_pages(rec, f.id)


@pytest.mark.anyio
@pytest.mark.parametrize("failed_pass", ["facts", "links"])
@pytest.mark.parametrize("recovers", [False, True])
async def test_project_pass_retries_once_without_failing_file(
    rec, monkeypatch, failed_pass, recovers
):
    from collections import Counter
    from decimal import Decimal

    from qsone.engine import cards, oneshot
    from qsone.records.mapping import links

    f = files.add_file(rec, "sample.txt", b"Retention 10%", actor="engineer")
    drain(rec)
    monkeypatch.setattr(oneshot, "map_model", lambda _: object())
    monkeypatch.setattr(cards, "cost", lambda *a, **kw: Decimal("0"))
    calls = Counter()
    target = facts.Result if failed_pass == "facts" else links.Result

    async def read(*args):
        return "Retention 10%"

    async def request(prompt, schema, instructions):
        calls[schema] += 1
        if schema is target and (not recovers or calls[schema] == 1):
            assert store.detail(rec, f.id)["ai_state"] == "done"
            raise TimeoutError("private provider body")
        if schema is ai.Batch:
            return ai.Batch(files=[ai.FileMap(file_id=f.id, kind="conditions", group="Tender")])
        if schema is ai.Groups:
            return ai.Groups(groups=[])
        if schema is links.Result:
            return links.Result(links=[])
        return facts.Result(
            facts=[
                facts.Fact(
                    name={"en": "Retention", "ar": "المحتجز"},
                    value="10%",
                    source_label="Retention",
                    file_id=f.id,
                    locator={"line": 1},
                    state="found",
                    evidence="Retention 10%",
                )
            ]
        )

    await ai.run(rec, SimpleNamespace(), request=request, passes={"read": read})
    assert calls[target] == 2
    row = store.detail(rec, f.id)
    assert row["ai_state"] == "done" and row["note"] is None
    status = store.list_map(rec)["status"]
    result = status["passes"][failed_pass]
    assert result["attempts"] == 2
    assert result["state"] == ("done" if recovers else "failed")
    assert (result["note"] is None) == recovers
    assert status["ai_failed"] == 0
    assert "private provider body" not in json.dumps(status)
    if failed_pass == "facts" and not recovers:
        assert calls[links.Result] == 0
    # Completed per-file work is not replayed to retry a project pass a third time.
    assert not await ai.run(rec, SimpleNamespace(), request=request, passes={"read": read})
    assert calls[target] == 2
