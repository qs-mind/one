import pytest

from qsone.records import files
from qsone.records.mapping import facts, store
from qsone.records.project import RecordsError
from tests.samples import sample_pdf


def proposal(fid, value="10%", **extra):
    extra.setdefault("evidence", value)
    return dict(
        name={"en": "Retention", "ar": "المحتجز"},
        value=value,
        file_id=fid,
        locator={"page": 1},
        **extra,
    )


def test_validation_states_correction_and_gate(rec):
    f = files.add_file(
        rec, "sample.pdf", sample_pdf([["Retention 10%", "Security: ____"]]), actor="engineer"
    )
    ids = facts.accept(
        rec,
        [
            proposal(f.id),
            proposal(f.id, "110%"),
            dict(
                proposal(f.id, "", state="blank", evidence="Security: ____"),
                name={"en": "Security", "ar": "الضمان"},
            ),
        ],
    )
    assert len(ids) == 2
    rows = store.entries(rec, "facts")["facts"]
    assert {r["state"] for r in rows} == {"found", "blank"}
    view = {"sources": {"s": {"file_id": f.id, "locator": {"page": 1}}}}
    assert len(facts.gate(rec, view)) == 2
    assert "page 1" in facts.gate(rec, view)[0]["en"]
    facts.update(rec, ids[0], value="5%", actor="engineer")
    facts.update(rec, ids[1], confirm=True, actor="engineer")
    assert facts.gate(rec, view) == []
    row = next(r for r in store.entries(rec, "facts")["facts"] if r["id"] == ids[0])
    assert row["value"] == "10%" and row["corrected_value"] == "5%"
    assert row["confirmed_by"] == "engineer"
    with pytest.raises(RecordsError):
        facts.update(rec, "missing", confirm=True, actor="engineer")


def test_conflicts_and_exact_digits(rec):
    f = files.add_file(rec, "a.txt", b"Retention 110% and 10.5%", actor="engineer")
    g = files.add_file(rec, "b.txt", "Retention ١١٪".encode(), actor="engineer")
    assert facts.accept(rec, [dict(proposal(f.id), locator={})]) == []
    ids = facts.accept(
        rec, [dict(proposal(f.id, "110%"), locator={}), dict(proposal(g.id, "11%"), locator={})]
    )
    assert len(ids) == 2
    rows = store.entries(rec, "facts")["facts"]
    assert all(r["state"] == "conflict" and r["conflict_with"] for r in rows)
    assert all(
        r["verification"] == {"en": "Read by ONE, not checked", "ar": "ONE قراها، لسه ما اتراجعتش"}
        for r in rows
    )


def test_candidate_fallback_and_scripted_pass(rec):
    f = files.add_file(
        rec, "sample.pdf", sample_pdf([["Cover"], ["Bid validity 90 days"]]), actor="engineer"
    )
    seen = []

    def read(fid, loc):
        seen.append((fid, loc))
        return "Bid validity 90 days"

    def propose(pages):
        assert pages and pages[0]["text"] == "Bid validity 90 days"
        return [
            dict(
                proposal(f.id, "90 days"),
                locator={"page": 2},
                name={"en": "Bid validity", "ar": "سريان العرض"},
            )
        ]

    assert facts.run(rec, read=read, propose=propose)
    assert seen == [(f.id, {"page": 2})]


def test_deliverable_gate_and_source_mark(rec, monkeypatch):
    from qsone.deliverables import api, review
    from qsone.deliverables import store as deliverables
    from tests.samples import sample_sheet

    f = files.add_file(rec, "sample.pdf", sample_pdf([["Retention 10%"]]), actor="engineer")
    fact = facts.accept(rec, [proposal(f.id)])[0]
    import tests.samples as samples
    from qsone.records import ledger

    sid = ledger.add_source(
        rec,
        kind="file",
        title="Sample retention",
        file_id=f.id,
        locator={"page": 1},
        actor="engineer",
    )
    monkeypatch.setattr(samples, "sample_source", lambda _: sid)
    d = sample_sheet(rec)
    v = deliverables.view(rec, d)
    assert v["sources"][sid]["map_facts"][0]["verification"]["en"] == "Read by ONE, not checked"
    review.record_check(
        rec,
        d,
        version_n=v["version"],
        code="A",
        checker="sample",
        same_provider=False,
        summary="",
        comments=[],
    )
    with pytest.raises(RecordsError, match="Retention"):
        review.sign_off(rec, d, actor="engineer")
    with pytest.raises(RecordsError, match="Retention"):
        api._export(rec, d, "xlsx", None)
    facts.update(rec, fact, confirm=True)
    assert review.sign_off(rec, d, actor="engineer") == 1


def test_route_confirm_and_strict_input(rec):
    from types import SimpleNamespace

    from pydantic import ValidationError

    from qsone.records.mapping.routes import FactEdit, router

    f = files.add_file(rec, "sample.pdf", sample_pdf([["Retention 10%"]]), actor="engineer")
    fact = facts.accept(rec, [proposal(f.id)])[0]
    route = next(
        r
        for r in router(SimpleNamespace(get=lambda _: rec)).routes
        if r.path.endswith("/{fact_id}")
    )
    with pytest.raises(ValidationError):
        FactEdit(confirm="true")
    result = route.endpoint("sample", fact, FactEdit(value="5%"))
    assert result["corrected_value"] == "5%"


def test_unread_proposal_and_invented_box_are_dropped(rec):
    f = files.add_file(
        rec, "sample.pdf", sample_pdf([["Retention 10%"], ["Retention 20%"]]), actor="engineer"
    )
    assert (
        facts.run(rec, read=lambda *_: "Retention 10%", propose=lambda _: [proposal(f.id, "20%")])
        == []
    )
    fact = facts.accept(rec, [dict(proposal(f.id), locator={"page": 1, "box": [0, 0, 1, 1]})])[0]
    row = next(r for r in store.entries(rec, "facts")["facts"] if r["id"] == fact)
    assert "box" not in row["locator"]


def test_pack_page_ranges_gate(rec):
    f = files.add_file(
        rec, "sample.pdf", sample_pdf([["Retention 10%"], ["Cover"]]), actor="engineer"
    )
    facts.accept(rec, [proposal(f.id)])
    assert facts.gate(rec, {"steps": [{"kind": "file", "file_id": f.id, "ranges": [[1, 1]]}]})
    assert not facts.gate(rec, {"steps": [{"kind": "file", "file_id": f.id, "ranges": [[2, 2]]}]})


def test_ai_prompt_has_guide_and_only_selected_pages():
    prompt = facts.prompt(
        [{"file_id": "sample", "locator": {"page": 58}, "text": "Sample retention 10%"}]
    )
    assert "bid validity" in prompt and "performance security" in prompt
    assert "Sample retention 10%" in prompt
    assert "blank" in prompt and "untrusted" in prompt


async def test_scripted_structured_facts_and_cost(general, fake_clock, data_dir):
    from pydantic_ai.messages import ModelResponse, ToolCallPart
    from pydantic_ai.models.function import FunctionModel
    from pydantic_ai.usage import RequestUsage

    from qsone.engine.costs import Spending
    from qsone.engine.oneshot import Models
    from qsone.engine.store import CostBook
    from tests.engine_fakes import HAIKU, FakeHost
    from tests.test_engine_runner import FakeLink

    async def answer(messages, info):
        return ModelResponse(
            parts=[
                ToolCallPart(
                    info.output_tools[0].name,
                    {"facts": [dict(proposal("sample"), state="found", evidence="Retention 10%")]},
                )
            ],
            usage=RequestUsage(input_tokens=100, output_tokens=50),
        )

    link = FakeLink(
        "anthropic", "Sample AI", "anthropic", models={HAIKU.choice.model: FunctionModel(answer)}
    )
    models = Models(
        sheet=(HAIKU,),
        roles={"quick": HAIKU.choice},
        connectors={link.id: link},
        spending=Spending(CostBook(general), clock=fake_clock),
        host=FakeHost(brief_id="sample"),
        brief_id="sample",
        project_id="sample-project",
        run_id="sample-run",
        work=data_dir / "work",
    )
    result = await facts.propose(
        [{"file_id": "sample", "locator": {"page": 1}, "text": "Retention 10%"}], models=models
    )
    assert result[0]["value"] == "10%"
    with general.read() as c:
        assert c.execute(
            "SELECT role,input_tokens,output_tokens FROM ai_costs WHERE run_id='sample-run'"
        ).fetchone() == ("quick", 100, 50)


async def test_no_ai_produces_no_facts():
    from types import SimpleNamespace

    models = SimpleNamespace(roles={}, card=lambda _: None, connectors={})
    assert await facts.propose([], models=models) == []


def test_arabic_guide_search_in_addition_to_key_pages(rec):
    from qsone.records.mapping import worker

    f = files.add_file(
        rec,
        "sample-ar.txt",
        "فتح العروض 03/02/1450\nسريان العرض 90 يوم\nالضمان الابتدائي 1%–2%".encode(),
        actor="engineer",
    )
    while worker.step(rec):
        pass
    with rec.write("one") as c:
        store.write(c, rec, "map_files", dict(file_id=f.id, key_pages=[{"page": 99}]))
    assert facts.candidates(rec)


def test_opening_label_cannot_be_submission(rec):
    f = files.add_file(rec, "sample-ar.txt", "فتح العروض 03/02/1450".encode(), actor="engineer")
    wrong = dict(
        name={"en": "Submission Date", "ar": "ميعاد التقديم"},
        value="03/02/1450",
        file_id=f.id,
        locator={},
        source_label="فتح العروض",
    )
    assert facts.accept(rec, [wrong]) == []


def test_candidate_budget_includes_other_files(rec):
    from tests.test_project_map import drain

    first = files.add_file(
        rec,
        "sample-many.pdf",
        sample_pdf([[f"Retention sample {n}"] for n in range(20)]),
        actor="engineer",
    )
    second = files.add_file(
        rec, "sample-security.txt", "سريان العرض 90 يوم".encode(), actor="engineer"
    )
    drain(rec)
    # Stable ordering deliberately puts the long file first.
    selected = facts.candidates(rec, limit=2)
    assert {p["file_id"] for p in selected} == {first.id, second.id}


def test_source_label_is_kept_and_local_content_penalty_not_delay(rec):
    f = files.add_file(
        rec,
        "sample-label.txt",
        "فتح العروض 03/02/1450\nغرامة مخالفة المحتوى المحلي 10%".encode(),
        actor="engineer",
    )
    base = dict(file_id=f.id, locator={})
    accepted = facts.accept(
        rec,
        [
            dict(
                base,
                name={"en": "Opening of offers", "ar": "فتح العروض"},
                source_label="فتح العروض",
                value="03/02/1450",
                evidence="فتح العروض 03/02/1450",
            )
        ],
    )
    assert store.entries(rec, "facts")["facts"][0]["source_label"] == "فتح العروض"
    assert accepted
    assert not facts.accept(
        rec,
        [
            dict(
                base,
                name={"en": "Delay damages", "ar": "غرامة تأخير"},
                source_label="غرامة مخالفة المحتوى المحلي",
                value="10%",
            )
        ],
    )


@pytest.mark.anyio
async def test_synthetic_arabic_tender_pages_security_validity_and_blank(rec):
    import json

    from tests.test_project_map import drain

    # Synthetic OCR text, injected just as the local OCR adapter would persist it.
    tender = files.add_file(
        rec,
        "sample-conditions.pdf",
        sample_pdf(
            [["Sample cover"], ["Sample article 8"], ["Sample validity"]]
            + [["Sample appendix"]] * 8
        ),
        actor="engineer",
    )
    rules = files.add_file(
        rec,
        "sample-local-content.txt",
        "غرامة مخالفة المحتوى المحلي 10%".encode(),
        actor="engineer",
    )
    drain(rec)
    text = {
        1: "فتح العروض 03/02/1450",
        2: "المادة 8 (ج) الضمان الابتدائي 1%–2% من قيمة العرض صالح 90 يوم من فتح العروض",
        3: "مدة سريان العرض 90 يوم\nالدفعة المقدمة ____",
    }
    with rec.write("one") as c:
        for page, words in text.items():
            c.execute(
                "UPDATE chunks SET text=? WHERE file_id=? AND json_extract(locator,'$.page')=?",
                (words, tender.id, page),
            )
        store.write(c, rec, "map_files", dict(file_id=tender.id, key_pages=[{"page": 1}]))

    async def read(fid, locator):
        if fid == tender.id:
            return text[locator["page"]]
        return "غرامة مخالفة المحتوى المحلي 10%"

    async def request(prompt, schema, instructions):
        pages = json.loads(prompt.split("\n", 1)[1])
        assert {(p["file_id"], p["locator"].get("page")) for p in pages} >= {
            (tender.id, 1),
            (tender.id, 2),
            (tender.id, 3),
        }

        def fact(label, en, value, page, **extra):
            return facts.Fact(
                name={"en": en, "ar": label},
                source_label=label,
                value=value,
                file_id=tender.id,
                locator={"page": page},
                state=extra.get("state", "found"),
                evidence=extra.get("evidence", text[page]),
            )

        return facts.Result(
            facts=[
                fact("فتح العروض", "Submission Date", "03/02/1450", 1).model_copy(
                    update={"name": facts.Label(en="Submission Date", ar="ميعاد التقديم")}
                ),
                fact("فتح العروض", "Opening of offers", "03/02/1450", 1),
                fact("الضمان الابتدائي", "Bid security", "1%–2%", 2),
                fact("الضمان الابتدائي", "Bid security validity", "90 يوم", 2),
                fact("مدة سريان العرض", "Offer validity", "90 يوم", 3),
                fact(
                    "الدفعة المقدمة",
                    "Advance payment",
                    "",
                    3,
                    state="blank",
                    evidence="الدفعة المقدمة ____",
                ),
                facts.Fact(
                    name={"en": "Delay damages", "ar": "غرامة تأخير"},
                    source_label="غرامة مخالفة المحتوى المحلي",
                    value="10%",
                    file_id=rules.id,
                    locator={"line": 1},
                    state="found",
                    evidence="غرامة مخالفة المحتوى المحلي 10%",
                ),
            ]
        )

    ids = await facts.run_approved(rec, read=read, request=request, file_ids={tender.id, rules.id})
    assert len(ids) == 5
    saved = store.entries(rec, "facts")["facts"]
    blank = next(f for f in saved if f["state"] == "blank")
    assert blank["locator"] == {"page": 3}
    assert all(f["source_label"] for f in saved)
    assert not any(f["name"]["en"] in ("Submission Date", "Delay damages") for f in saved)


@pytest.mark.anyio
async def test_approved_facts_searches_existing_files_too(rec):
    from tests.test_project_map import drain

    existing = files.add_file(rec, "sample-existing.txt", b"Bid validity 90 days", actor="engineer")
    added = files.add_file(rec, "sample-added.txt", b"Opening date 2026-11-06", actor="engineer")
    drain(rec)
    seen = set()

    async def read(fid, loc):
        seen.add(fid)
        return "Bid validity 90 days" if fid == existing.id else "Opening date 2026-11-06"

    async def request(*args):
        return facts.Result(facts=[])

    with pytest.raises(facts.NoTenderFacts):
        await facts.run_approved(rec, read=read, request=request, file_ids={added.id})
    assert seen == {existing.id, added.id}


def test_evidence_grounding_arabic_variants_numbers_and_conflicts(rec):
    first = "على المتنافس تقديم الضمان الابتدائي بنسبة 1 بالمائة"
    second = "الضمان الابتدائي (2%) إلى (1%)"
    a = files.add_file(rec, "sample-a.txt", first.encode(), actor="engineer")
    b = files.add_file(rec, "sample-b.txt", second.encode(), actor="engineer")

    def item(fid, value, evidence):
        return dict(
            file_id=fid,
            locator={"line": 1},
            name={"en": "Bid security", "ar": "نسبة الضمان الابتدائي"},
            source_label="الضمان الابتدائي",
            value=value,
            evidence=evidence,
        )

    ids = facts.accept(rec, [item(a.id, "1%", first), item(b.id, "1% إلى 2%", second)])
    assert len(ids) == 2
    saved = store.entries(rec, "facts")["facts"]
    assert all(r["state"] == "conflict" and r["conflict_with"] for r in saved)
    assert {r["file_id"] for r in saved} == {a.id, b.id}
    assert not facts.accept(rec, [item(a.id, "10%", first), item(a.id, "2%", first)])
    assert facts.evidence_matches("تَاريخ فَتح العروض ٠٣ / ٠٢ / ١٤٥٠", "تاريخ فتح العروض 03/02/1450")
    assert facts.evidence_matches("الضمان الإبتدائي للأميرسلطان", "الضمان الابتدائي للأمير سلطان")
    assert facts.evidence_matches(first, "على المتنافس تقديم الضمان الابتدائى بنسة 1 بالمائة")
    assert not facts.evidence_matches(first, "الدفعة المقدمة عشرون بالمائة")
    assert not facts.evidence_matches(first, "[]")
    assert not facts.accept(rec, [dict(item(a.id, "1%", ""))])


@pytest.mark.anyio
async def test_approved_grounding_accepts_range_format_and_longer_fact_name(rec):
    from tests.test_project_map import drain

    opening = "فتح العروض 03/02/1450"
    security = "الضمان الابتدائي (2%) إلى (1%)"
    first = files.add_file(rec, "sample-opening.txt", opening.encode(), actor="engineer")
    second = files.add_file(rec, "sample-security.txt", security.encode(), actor="engineer")
    drain(rec)
    texts = {first.id: opening, second.id: security}

    async def read(fid, loc):
        return texts[fid]

    async def request(*args):
        return facts.Result(
            facts=[
                facts.Fact(
                    name={"en": "Date of opening offers", "ar": "تاريخ فتح العروض"},
                    value="03/02/1450",
                    file_id=first.id,
                    locator={"line": 1},
                    state="found",
                    evidence=opening,
                    source_label="فتح العروض",
                ),
                facts.Fact(
                    name={"en": "Bid security", "ar": "نسبة الضمان الابتدائي"},
                    value="1% إلى 2%",
                    file_id=second.id,
                    locator={"line": 1},
                    state="found",
                    evidence=security,
                    source_label="الضمان الابتدائي",
                ),
            ]
        )

    assert len(await facts.run_approved(rec, read=read, request=request, file_ids=set(texts))) == 2


@pytest.mark.parametrize(
    "words,number",
    [
        ("تسعين", "90"),
        ("تسعون", "90"),
        ("ستين", "60"),
        ("ثلاثين", "30"),
        ("مائة", "100"),
        ("مئة", "100"),
        ("ثلاثمائة وستين", "360"),
        ("ninety", "90"),
    ],
)
def test_number_words(words, number):
    assert facts.grounded(words, {"value": number, "evidence": words})
    assert not facts.grounded(words, {"value": "110", "evidence": words})


def test_title_label_is_optional(rec):
    text = "كراسةالشروطوالمواصفات\nفتح العروض 03/02/1450"
    f = files.add_file(rec, "sample.txt", text.encode(), actor="engineer")
    p = dict(
        file_id=f.id,
        locator={},
        name={"en": "Opening", "ar": "فتح العروض"},
        value="03/02/1450",
        source_label="كراسة الشروط والمواصفات",
        evidence="فتح العروض 03/02/1450",
    )
    assert len(facts.accept(rec, [p])) == 1
    assert store.entries(rec, "facts")["facts"][0]["source_label"] == "فتح العروض"


def test_picture_comparison():
    from qsone.records import ocr
    from qsone.records.mapping.picture import compare

    page = ocr.Page([ocr.Word("٩٠", [0, 0, 10, 10], 95)], False)
    result = compare("01 days", page)
    assert result["value"] == "01 days"
    assert result["text_value"] == "01 days"
    assert set(result["warning"]) == {"en", "ar"}
    assert compare("90 days", ocr.Page([ocr.Word("٠٩", [], 95)], False)) is None
    assert compare("01 days", ocr.Page([ocr.Word("90", [], 20)], True)) is None
    assert compare("01 يوم", ocr.Page([ocr.Word("٠", [], 77)], False)) is None
    assert compare("01 يوم", ocr.Page([ocr.Word("90", [], 77)], False)) is None
    assert compare("01 يوم", ocr.Page([ocr.Word("٠", [], 95)], False)) is None


@pytest.mark.anyio
async def test_reviewer_five_rows_keep_conflict(rec):
    from tests.test_project_map import drain

    book = files.add_file(
        rec, "sample-book.pdf", sample_pdf([["Sample page"] for _ in range(20)]), actor="engineer"
    )
    cond = files.add_file(
        rec,
        "sample-conditions.pdf",
        sample_pdf([["Sample condition"] for _ in range(11)]),
        actor="engineer",
    )
    rows = [
        (
            book.id,
            7,
            "Opening",
            "فتح العروض",
            "03/02/1450",
            "كراسة الشروط والمواصفات",
            "فتح العروض 03/02/1450",
        ),
        (
            book.id,
            20,
            "Bid security",
            "الضمان الابتدائي",
            "1%",
            "كراسة الشروط والمواصفات",
            "الضمان الابتدائي بنسبة 1 بالمائة من القيمة الإجمالية للعرض",
        ),
        (
            cond.id,
            2,
            "Bid security",
            "الضمان الابتدائي",
            "1% - 2%",
            "المملكة العربية السعودية وزارة",
            "يقدم مع العرض ضمان ابتدائي بقيمة تتراوح من )2%( إلى )1%( من",
        ),
        (
            book.id,
            20,
            "Security validity",
            "سريان الضمان الابتدائي",
            "90 days",
            "",
            "ساري المفعول مدة لا تقل عن)90(تسعين يوماً من التاريخ المحدد",
        ),
        (
            cond.id,
            3,
            "Offer validity",
            "مدة سريان العروض",
            "90 days",
            "",
            "تكون مدة سريان العروض في المنافسات العامة تسعين يوماً من الت",
        ),
    ]
    drain(rec)
    texts = {}
    for fid, page, *_, evidence in rows:
        texts[(fid, page)] = texts.get((fid, page), "كراسةالشروطوالمواصفات\n") + "\n" + evidence
    with rec.write("one") as c:
        for (fid, page), text in texts.items():
            c.execute(
                "UPDATE chunks SET text=? WHERE file_id=? AND json_extract(locator,'$.page')=?",
                (text, fid, page),
            )

    async def read(fid, loc):
        return texts.get((fid, loc["page"]), "Sample")

    async def request(*args):
        return facts.Result(
            facts=[
                facts.Fact(
                    file_id=fid,
                    locator={"page": page},
                    name={"en": en, "ar": ar},
                    value=value,
                    source_label=label,
                    evidence=ev,
                    state="found",
                )
                for fid, page, en, ar, value, label, ev in rows
            ]
        )

    assert (
        len(await facts.run_approved(rec, read=read, request=request, file_ids={book.id, cond.id}))
        == 5
    )
    saved = store.entries(rec, "facts")["facts"]
    security = [r for r in saved if r["name"]["en"] == "Bid security"]
    assert len(security) == 2 and all(r["state"] == "conflict" for r in security)


def test_picture_result_persisted(rec, monkeypatch):
    from qsone.records.mapping import picture

    f = files.add_file(rec, "sample.pdf", sample_pdf([["Validity 01 days"]]), actor="engineer")
    from qsone.records import ocr

    monkeypatch.setattr(
        picture,
        "check",
        lambda *args: picture.compare(args[-1], ocr.Page([ocr.Word("٩٠", [], 95)], False)),
    )
    p = dict(
        file_id=f.id,
        locator={"page": 1},
        name={"en": "Validity", "ar": "السريان"},
        value="01 days",
        evidence="Validity 01 days",
    )
    assert facts.accept(rec, [p])
    row = store.entries(rec, "facts")["facts"][0]
    assert row["value"] == "01 days"
    assert row["picture_check"]["text_value"] == "01 days"
    assert row["evidence"] == p["evidence"]
    assert row["confirmed_at"] is None
    assert facts.accept(rec, [p]) == []


def test_picture_renders_evidence_region_with_stub_ocr(rec, monkeypatch, tmp_path):
    from qsone.records import ocr
    from qsone.records.mapping import picture

    f = files.add_file(
        rec, "sample.pdf", sample_pdf([["Validity 01 days", "Unrelated 500"]]), actor="engineer"
    )
    for language in ("ara", "eng"):
        (tmp_path / f"{language}.traineddata").write_bytes(b"sample")
    monkeypatch.setattr(ocr, "find_tesseract", lambda: "sample-tesseract")
    monkeypatch.setattr(ocr, "model_folder", lambda: tmp_path)
    monkeypatch.setattr(ocr, "system_folders", lambda _: [])
    images = []

    def read(png, **kwargs):
        width, height = ocr.png_size(png)
        assert width > 0 and height > 0
        assert kwargs["points"] == (width / 3, height / 3)
        images.append(png)
        return ocr.Page([ocr.Word("٩٠", [], 95)], False)

    monkeypatch.setattr(ocr, "read_image", read)
    result = picture.check(rec, f.id, {"page": 1}, "Validity 01 days", "01 days")
    assert images and result["value"] == "01 days"
    assert picture.check(rec, f.id, {"page": 1}, "Missing 01", "01") is None


@pytest.mark.anyio
@pytest.mark.parametrize("reading, warned", [("٩٠", True), ("01", False)])
async def test_approved_batched_vision_keeps_text_value(rec, monkeypatch, reading, warned):
    from qsone.records.mapping import picture

    f = files.add_file(rec, "sample.pdf", sample_pdf([["Validity 01 days"]]), actor="engineer")

    async def read(*args):
        return "Validity 01 days"

    async def request(*args):
        return facts.Result(
            facts=[
                facts.Fact(
                    file_id=f.id,
                    locator={"page": 1},
                    name={"en": "Validity", "ar": "السريان"},
                    value="01 days",
                    evidence="Validity 01 days",
                    state="found",
                )
            ]
        )

    calls = []

    async def vision(images, schema, instructions):
        calls.append(images)
        assert len(images) == 1 and images[0]["png"].startswith(b"\x89PNG")
        assert "exactly" in instructions and "Arabic-Indic" in instructions
        return schema.model_validate({"readings": [{"id": images[0]["id"], "numbers": reading}]})

    monkeypatch.setattr(
        picture, "check", lambda *args: pytest.fail("OCR must not judge before vision")
    )
    ids = await facts.run_approved(
        rec, read=read, request=request, file_ids={f.id}, vision_request=vision
    )
    assert len(calls) == 1 and len(ids) == 1
    row = store.entries(rec, "facts")["facts"][0]
    assert row["value"] == "01 days"
    assert bool(row["picture_check"] and row["picture_check"].get("warning")) == warned
    assert row["picture_check"]["text_value"] == "01 days"
    assert row["picture_check"]["picture_text"] == reading
    assert row["confirmed_at"] is None
    assert facts.gate(rec, {"fact_ids": ids})
    facts.update(rec, ids[0], confirm=True)
    assert facts.gate(rec, {"fact_ids": ids}) == []


@pytest.mark.anyio
async def test_costed_quick_vision_request(general, fake_clock, data_dir):
    from pydantic_ai.messages import BinaryContent, ModelResponse, ToolCallPart
    from pydantic_ai.models.function import FunctionModel
    from pydantic_ai.usage import RequestUsage

    from qsone.engine import oneshot
    from qsone.engine.costs import Spending
    from qsone.engine.oneshot import Models
    from qsone.engine.store import CostBook
    from qsone.records.mapping import picture
    from tests.engine_fakes import HAIKU, FakeHost
    from tests.test_engine_runner import FakeLink

    async def answer(messages, info):
        assert any(
            isinstance(part, BinaryContent)
            for message in messages
            for p in message.parts
            for part in (p.content if isinstance(getattr(p, "content", None), list) else [])
        )
        return ModelResponse(
            parts=[
                ToolCallPart(
                    info.output_tools[0].name, {"readings": [{"id": "sample", "numbers": "90"}]}
                )
            ],
            usage=RequestUsage(input_tokens=100, output_tokens=50),
        )

    link = FakeLink(
        "anthropic", "Sample AI", "anthropic", models={HAIKU.choice.model: FunctionModel(answer)}
    )
    models = Models(
        sheet=(HAIKU,),
        roles={"quick": HAIKU.choice},
        connectors={link.id: link},
        spending=Spending(CostBook(general), clock=fake_clock),
        host=FakeHost(brief_id="sample"),
        brief_id="sample",
        project_id="sample-project",
        run_id="vision-run",
        work=data_dir / "work",
    )

    async def request(images, schema, instructions):
        return await oneshot.map_pictures(models, images, schema, instructions)

    f = files.add_file(general, "sample.pdf", sample_pdf([["Validity 01 days"]]), actor="engineer")
    ids = facts.accept(
        general,
        [
            dict(
                file_id=f.id,
                locator={"page": 1},
                name={"en": "Validity", "ar": "السريان"},
                value="01 days",
                evidence="Validity 01 days",
            )
        ],
        picture_fallback=False,
    )

    # Return the actual fact id from the scripted provider.
    async def answer_with_id(messages, info):
        response = await answer(messages, info)
        response.parts[0].args["readings"][0]["id"] = ids[0]
        return response

    link.models[HAIKU.choice.model] = FunctionModel(answer_with_id)
    await picture.verify(general, ids, request=request)
    with general.read() as c:
        assert c.execute(
            "SELECT role,input_tokens,output_tokens FROM ai_costs WHERE run_id='vision-run'"
        ).fetchone() == ("quick", 100, 50)


@pytest.mark.anyio
async def test_vision_retry_checks_already_persisted_facts(rec):
    f = files.add_file(rec, "sample.pdf", sample_pdf([["Validity 01 days"]]), actor="engineer")

    async def read(*args):
        return "Validity 01 days"

    async def request(*args):
        return facts.Result(
            facts=[
                facts.Fact(
                    file_id=f.id,
                    locator={"page": 1},
                    name={"en": "Validity", "ar": "السريان"},
                    value="01 days",
                    evidence="Validity 01 days",
                    state="found",
                )
            ]
        )

    calls = []

    async def vision(images, schema, instructions):
        calls.append(images)
        if len(calls) == 1:
            raise ValueError("Sample interrupted request")
        return schema.model_validate({"readings": [{"id": images[0]["id"], "numbers": "90"}]})

    with pytest.raises(ValueError, match="interrupted"):
        await facts.run_approved(
            rec, read=read, request=request, file_ids={f.id}, vision_request=vision
        )
    await facts.run_approved(
        rec, read=read, request=request, file_ids={f.id}, vision_request=vision
    )
    assert len(calls) == 2
    row = store.entries(rec, "facts")["facts"][0]
    assert row["value"] == "01 days" and row["picture_check"]["warning"]


@pytest.mark.anyio
async def test_numeric_pdf_facts_share_one_vision_batch(rec):
    from qsone.records.mapping import picture

    f = files.add_file(
        rec,
        "sample.pdf",
        sample_pdf([["Validity 01 days"], ["Validity 02 days"]]),
        actor="engineer",
    )
    ids = facts.accept(
        rec,
        [
            dict(
                file_id=f.id,
                locator={"page": page},
                name={"en": "Validity", "ar": "السريان"},
                value=value,
                evidence=f"Validity {value}",
            )
            for page, value in [(1, "01 days"), (2, "02 days")]
        ],
        picture_fallback=False,
    )
    calls = []

    async def vision(images, schema, instructions):
        calls.append(images)
        return schema.model_validate(
            {"readings": [{"id": image["id"], "numbers": "٩٠"} for image in images]}
        )

    await picture.verify(rec, ids, request=vision)
    assert len(calls) == 1 and len(calls[0]) == 2
    saved = store.entries(rec, "facts")["facts"]
    assert {r["value"] for r in saved} == {"01 days", "02 days"}
    assert all(r["picture_check"]["warning"] for r in saved)


def test_picture_check_releases_write_lock(rec, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor

    from qsone.records.mapping import picture

    f = files.add_file(rec, "sample.pdf", sample_pdf([["Retention 10%"]]), actor="engineer")

    def check(*args):
        def write():
            with rec.write("engineer") as c:
                rec.set_meta(c, "concurrent_sample", "ok")

        with ThreadPoolExecutor() as pool:
            pool.submit(write).result(timeout=2)
        return None

    monkeypatch.setattr(picture, "check", check)
    assert facts.accept(rec, [proposal(f.id)])


def test_candidate_reservations(rec):
    pages = [["Retention security payment validity 10% 20% 30%"]] * 4
    pages += [["فتح العروض 03/02/1450 الترسية 18/04/1450 بدء الأعمال 25/04/1450"]]
    f = files.add_file(rec, "sample.pdf", sample_pdf(pages), actor="engineer")
    g = files.add_file(rec, "short.pdf", sample_pdf([["Sample cover"]]), actor="engineer")
    chosen = facts.candidates(rec, limit=3)
    assert {"file_id": f.id, "locator": {"page": 5}} in chosen
    assert {"file_id": g.id, "locator": {"page": 1}} in chosen


async def test_fact_pass_reports_private_text_free_counts(rec):
    f = files.add_file(rec, "sample.pdf", sample_pdf([["Retention 10%"]]), actor="engineer")
    good = dict(proposal(f.id), state="found", source_label="Retention")
    missing = dict(good, value="99%")
    ungrounded = dict(good, evidence="Invented condition 10%")

    async def read(fid, loc):
        return "Retention 10%"

    async def request(*args):
        return facts.Result(facts=[good, good, missing, ungrounded])

    await facts.run_approved(rec, read=read, request=request, file_ids={f.id})
    with rec.read() as c:
        stats = store._pass_summary(c)["facts"]["counts"]
    assert stats == {
        "candidate_pages": 1,
        "proposed": 4,
        "accepted": 1,
        "rejected": {"not_grounded": 1, "number_missing": 1, "duplicate": 1, "other": 0},
    }


async def test_approved_picture_work_does_not_block_event_loop(rec, monkeypatch):
    import threading

    from qsone.records.mapping import picture

    main_thread = threading.get_ident()
    f = files.add_file(rec, "sample.pdf", sample_pdf([["Retention 10%"]]), actor="engineer")

    def check(*args):
        assert threading.get_ident() != main_thread

    monkeypatch.setattr(picture, "check", check)

    async def read(fid, loc):
        return "Retention 10%"

    async def request(*args):
        return facts.Result(facts=[dict(proposal(f.id), state="found")])

    assert await facts.run_approved(rec, read=read, request=request, file_ids={f.id})


def test_key_data_and_short_bid_conditions_keep_conflicting_sources(rec):
    book = files.add_file(
        rec,
        "sample-book.pdf",
        sample_pdf([["Retention security payment validity 10% 20% 30%"]] * 28),
        actor="engineer",
    )
    bid = files.add_file(
        rec,
        "sample-conditions.pdf",
        sample_pdf([["Sample cover"], ["Sample terms"]]),
        actor="engineer",
    )
    dates = "فتح العروض 03/02/1450 / الترسية 18/04/1450 / بدء الأعمال 25/04/1450"
    security = "ضمان ابتدائي بقيمة تتراوح من (2%) إلى (1%)"
    with rec.write("engineer") as c:
        for fid, page, text in [
            (book.id, 7, dates),
            (book.id, 20, "ضمان ابتدائي 1%"),
            (bid.id, 2, security),
        ]:
            c.execute(
                "UPDATE chunks SET text=? WHERE file_id=? AND json_extract(locator,'$.page')=?",
                (text, fid, page),
            )
    chosen = facts.candidates(rec, limit=3)
    assert all(
        {"file_id": fid, "locator": {"page": page}} in chosen
        for fid, page in [(book.id, 7), (book.id, 20), (bid.id, 2)]
    )
    name = {"en": "Bid security", "ar": "ضمان ابتدائي"}
    accepted = facts.accept(
        rec,
        [
            dict(
                proposal(book.id, "1%", evidence="ضمان ابتدائي 1%"), locator={"page": 20}, name=name
            ),
            dict(proposal(bid.id, "1%–2%", evidence=security), locator={"page": 2}, name=name),
        ],
        picture_fallback=False,
    )
    assert len(accepted) == 2
    assert all(r["state"] == "conflict" for r in store.entries(rec, "facts")["facts"])


def test_scripted_missing_locator_uses_only_sent_pages(rec):
    from tests.test_project_map import drain

    f = files.add_file(
        rec, "sample.pdf", sample_pdf([["Cover"], ["Bid validity 90 days"]]), actor="engineer"
    )
    drain(rec)
    assert facts.run(
        rec,
        read=lambda fid, loc: "Bid validity 90 days",
        propose=lambda pages: [
            dict(proposal(f.id, "90 days", evidence="Bid validity 90 days"), locator={})
        ],
    )
    assert store.entries(rec, "facts")["facts"][0]["locator"] == {"page": 2}


def test_locator_recovery_prefers_key_lines_and_does_not_search_unsent_pages():
    p = proposal("missing", "90 days", evidence="Bid validity 90 days")
    p["locator"] = {}
    pages = [
        {
            "file_id": "first",
            "locator": {"page": 1},
            "text": "The Bid validity 90 days is stated here. " + "Sample prose. " * 20,
        },
        {"file_id": "key", "locator": {"page": 7}, "text": "Bid validity 90 days"},
    ]
    recovered, ambiguous = facts.recover_locator(p, pages)
    assert ambiguous and recovered["file_id"] == "key"
    assert recovered["locator"] == {"page": 7}
    assert facts.recover_locator(p, [pages[0]])[0]["file_id"] == "first"
    assert facts.recover_locator(p, [dict(pages[0], text="Bid validity 30 days")])[0] == p


def test_fact_schema_requires_file_and_locator_but_not_a_page():
    """A sheet fact has sheet+row and no page; recover_locator fills a missing one."""
    schema = facts.Fact.model_json_schema()
    assert {"file_id", "locator"} <= set(schema["required"])
    assert "required" not in schema["properties"]["locator"]


async def test_approved_scripted_reply_with_empty_locator(rec):
    from tests.test_project_map import drain

    f = files.add_file(rec, "sample.pdf", sample_pdf([["Bid validity 90 days"]]), actor="engineer")
    drain(rec)

    async def read(fid, loc):
        return "Bid validity 90 days"

    async def request(prompt, schema, instructions):
        return schema(
            facts=[
                dict(
                    proposal(f.id, "90 days", evidence="Bid validity 90 days"),
                    locator={},
                    state="found",
                )
            ]
        )

    assert await facts.run_approved(rec, read=read, request=request, file_ids=[f.id])
    assert store.entries(rec, "facts")["facts"][0]["locator"] == {"page": 1}


def test_legacy_scripted_proposal_can_omit_locator_and_file():
    p = proposal("sample", "90 days", evidence="Bid validity 90 days", state="found")
    del p["locator"]
    del p["file_id"]
    parsed = facts.Fact.model_validate(p)
    assert parsed.locator == {} and parsed.file_id == ""
