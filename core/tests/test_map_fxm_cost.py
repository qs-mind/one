import json
from decimal import Decimal

from qsone.engine import cards, request_size
from qsone.records import files
from qsone.records.mapping import ai, facts
from tests.samples import sample_pdf
from tests.test_project_map import drain


def test_candidates_hard_cap_and_one_page_per_short_file(rec):
    for n in range(12):
        files.add_file(
            rec,
            f"sample-{n}.pdf",
            sample_pdf([[f"Bid security {n}% validity"]] * 4),
            actor="engineer",
        )
    drain(rec)
    chosen = facts.candidates(rec)
    assert len(chosen) <= 30
    assert len(chosen) == len({p["file_id"] for p in chosen})
    assert len(facts.candidates(rec, limit=5)) <= 5


def test_priority_reservations_cannot_exceed_thirty(rec):
    files.add_file(
        rec,
        "sample-long.pdf",
        sample_pdf(
            [
                [f"Bid security validity 1% opening 01/01/1450 02/01/1450 sample {n}"]
                for n in range(40)
            ]
        ),
        actor="engineer",
    )
    drain(rec)
    assert len(facts.candidates(rec)) == 30
    assert len(facts.candidates(rec, limit=4)) == 4


async def test_estimate_tracks_scripted_recorded_cost(rec, monkeypatch):
    from types import SimpleNamespace

    from qsone.engine import oneshot

    f = files.add_file(rec, "sample.txt", b"Sample bid security 1%", actor="engineer")
    drain(rec)
    digests = [ai.digest(rec, f.id)]
    monkeypatch.setattr(
        cards,
        "cost",
        lambda card, *, input_tokens, output_tokens: (
            Decimal(input_tokens + output_tokens) / 1000000
        ),
    )
    monkeypatch.setattr(oneshot, "map_model", lambda _: object())
    estimate = ai.estimate_cost(rec, object(), digests, enrichment=True)
    recorded = Decimal(0)

    async def read(fid, locator):
        return "Sample bid security 1%"

    async def request(prompt, schema, instructions):
        nonlocal recorded
        if schema is ai.Batch:
            result = ai.Batch(
                files=[
                    ai.FileMap(file_id=f.id, kind="contract", group={"en": "Tender", "ar": "عطاء"})
                ]
            )
        elif schema is ai.Groups:
            result = ai.Groups(groups=[])
        elif schema is facts.Result:
            result = facts.Result(
                facts=[
                    facts.Fact(
                        name={"en": "Bid security", "ar": "ضمان ابتدائي"},
                        value="1%",
                        file_id=f.id,
                        locator={"paragraph": 1},
                        state="found",
                        evidence="Sample bid security 1%",
                    )
                ]
            )
        else:
            result = schema(links=[])
        recorded += cards.cost(
            None,
            input_tokens=request_size.estimate(
                prompt + instructions + json.dumps(schema.model_json_schema())
            ),
            output_tokens=request_size.estimate(result.model_dump_json()),
        )
        return result

    assert await ai.run(rec, SimpleNamespace(), request=request, passes={"read": read})
    assert recorded <= estimate <= recorded * 2
    assert estimate < Decimal("0.02")
