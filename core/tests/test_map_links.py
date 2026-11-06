from qsone.records import files
from qsone.records.mapping import links, store
from tests.samples import sample_pdf


def test_local_references_and_checked_ai_endpoints(rec):
    a = files.add_file(
        rec, "spec.pdf", sample_pdf([["See Clause 14.3 and Section 03300"]]), actor="engineer"
    )
    b = files.add_file(
        rec, "conditions.pdf", sample_pdf([["14.3 Payment terms"]]), actor="engineer"
    )
    links.step(rec, a.id)
    rows = store.entries(rec, "links")["links"]
    assert any(r["from_file_id"] == a.id and r["to_file_id"] == b.id for r in rows)
    base = dict(
        from_file_id=a.id,
        from_locator={"page": 1},
        to_file_id=b.id,
        to_locator={"page": 1},
        kind="changes",
        words={"en": "Changes", "ar": "بيغيّر"},
        evidence={},
    )
    assert links.accept(rec, [base], by="ai")
    assert not links.accept(rec, [base | {"to_locator": {"page": 99}}], by="ai")
    assert not links.accept(rec, [base | {"to_file_id": "invented"}], by="ai")
    assert not links.accept(rec, [base | {"kind": "invented"}], by="ai")


def test_ai_digest_proposals_are_checked(rec):
    a = files.add_file(rec, "a.txt", b"See Section 03300", actor="engineer")
    b = files.add_file(rec, "b.txt", b"Section 03300 concrete", actor="engineer")

    def propose(digests):
        assert {d["file_id"] for d in digests} == {a.id, b.id}
        return [
            dict(
                from_file_id=a.id,
                from_locator={},
                to_file_id=b.id,
                to_locator={},
                kind="refers_to",
                words={"en": "Concrete", "ar": "خرسانة"},
            )
        ]

    assert links.run(rec, [{"file_id": a.id}, {"file_id": b.id}], propose=propose)


def test_drawing_sheet_endpoint_and_invented_box(rec):
    a = files.add_file(rec, "a.txt", b"See A-101", actor="engineer")
    b = files.add_file(rec, "drawing.txt", b"Sample drawing", actor="engineer")
    with rec.write("one") as c:
        store.write(
            c,
            rec,
            "map_sheets",
            dict(file_id=b.id, sheet="Model", number="A-101", source={"sheet": "Model"}),
        )
    links.step(rec, a.id)
    assert store.entries(rec, "links")["links"][0]["to_locator"] == {"sheet": "Model"}
    p = dict(
        from_file_id=a.id,
        from_locator={"box": [0, 0, 1, 1]},
        to_file_id=b.id,
        to_locator={"sheet": "invented"},
        kind="refers_to",
        words={"en": "Sheet", "ar": "لوحة"},
    )
    assert not links.accept(rec, [p])
