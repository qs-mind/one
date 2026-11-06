import pytest

from qsone.records import files
from qsone.records.mapping import facts, store
from qsone.records.project import RecordsError
from tests.samples import sample_pdf


def proposal(fid, value="10%", **extra):
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
        return [dict(proposal(f.id, "90 days"), locator={"page": 2})]

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
