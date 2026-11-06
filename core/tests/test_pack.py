"""Synthetic PDFs only: pack composition, review and the local integrity seal."""

from io import BytesIO

import pytest
from pypdf import PdfReader, PdfWriter

from qsone.deliverables import changes, store
from qsone.deliverables.pack import build, validate_steps
from qsone.records.project import RecordsError


def source():
    writer = PdfWriter()
    for width in (200, 300, 400):
        writer.add_blank_page(width, 500)
    out = BytesIO()
    writer.write(out)
    return out.getvalue()


def test_order_ranges_bookmarks():
    steps = [
        {
            "kind": "file",
            "file_id": "f",
            "ranges": [[3, 3], [1, 2]],
            "title": {"en": "Tender", "ar": "المناقصة"},
        }
    ]
    pdf = PdfReader(BytesIO(build(steps, lambda _: source(), "en")))
    assert [float(p.mediabox.width) for p in pdf.pages] == [400, 200, 300]
    assert pdf.outline[0].title == "Tender"


@pytest.mark.parametrize("ranges", [[[0, 1]], [[2, 4]], [[3, 1]], [[True, 2]]])
def test_invalid_pages(ranges):
    with pytest.raises(RecordsError):
        validate_steps([{"kind": "file", "file_id": "f", "ranges": ranges}], lambda _: source())


def test_overlay_numbers_arabic():
    import pypdfium2 as pdfium

    steps = [
        {"kind": "cover", "text": {"en": "Sample tender", "ar": "مناقصة تجريبية"}},
        {"kind": "file", "file_id": "f", "ranges": [[1, 2]]},
        {"kind": "divider", "text": {"en": "Sample appendix", "ar": "ملحق تجريبي"}},
        {
            "kind": "stamp",
            "text": {"en": "FOR TENDER", "ar": "للمناقصة"},
            "pages": [2],
            "position": "center",
        },
        {"kind": "page_numbers"},
    ]
    with pdfium.PdfDocument(build(steps, lambda _: source(), "ar")) as pdf:
        texts = []
        for page in pdf:
            text = page.get_textpage()
            texts.append(text.get_text_range())
            text.close()
            page.close()
    assert len(texts) == 4
    assert ["للمناقصة" in t for t in texts] == [False, True, False, False]
    assert all("صفحة" in t and "من" in t for t in texts)
    english = PdfReader(BytesIO(build(steps, lambda _: source(), "en")))
    for n, page in enumerate(english.pages, 1):
        assert f"Page {n} of 4" in page.extract_text()


def test_pack_suggested_versions(rec):
    d = store.create(
        rec, kind="pack", variant="tender", title="Sample", language="en", actor="lead_qs"
    )
    steps = [{"kind": "cover", "text": {"en": "Sample", "ar": "عينة"}}]
    proposed = changes.propose(
        rec, d, [{"op": "set_pack", "steps": steps}], actor="lead_qs", reason="Sample"
    )
    assert store.view(rec, d)["steps"] == []
    changes.accept(rec, d, [proposed[0].id], actor="engineer")
    assert store.view(rec, d)["steps"] == steps
    assert store.view(rec, d, version=1)["steps"] == []


def test_seal_verifies(memory_keyring):
    from pyhanko.pdf_utils.reader import PdfFileReader
    from pyhanko.sign.validation import validate_pdf_signature
    from pyhanko_certvalidator import ValidationContext

    from qsone.deliverables.pack_seal import seal

    signed = seal(source())
    reader = PdfFileReader(BytesIO(signed))
    signature = reader.embedded_signatures[0]
    result = validate_pdf_signature(
        signature,
        signer_validation_context=ValidationContext(
            trust_roots=[signature.signer_cert], allow_fetching=False
        ),
    )
    assert result.intact and result.valid and result.trusted
    saved = dict(memory_keyring.store)
    seal(source())
    assert memory_keyring.store == saved


def test_seal_unavailable(failing_keyring):
    from qsone.deliverables.pack_seal import seal

    with pytest.raises(RecordsError):
        seal(source())


def test_export_requires_signoff(rec):
    from qsone.deliverables.api import _export

    d = store.create(
        rec, kind="pack", variant="tender", title="Sample", language="en", actor="lead_qs"
    )
    with pytest.raises(RecordsError) as error:
        _export(rec, d, "pdf", None)
    assert error.value.status == 409


def test_tool_proposes_and_checks(rec):
    from types import SimpleNamespace

    from qsone.deliverables.tools import check_draft, pack_propose

    ctx = SimpleNamespace(
        rec=rec,
        agent=SimpleNamespace(role="lead"),
        host=SimpleNamespace(emit=lambda _: None),
        brief_id="sample",
    )
    steps = [{"kind": "cover", "text": {"en": "Sample", "ar": "عينة"}}]
    made = pack_propose(ctx, steps=steps, title="Sample", language="en", reason="Sample")
    assert store.view(rec, made["id"])["pending"] == 1
    changes.accept(rec, made["id"], made["change_ids"], actor="engineer")
    draft, version, _ = check_draft(rec, made["id"])
    assert "Sample" in draft.body
    assert version == 2
    with pytest.raises(RecordsError):
        pack_propose(
            ctx,
            id=made["id"],
            steps=[{"kind": "file", "file_id": "missing", "ranges": [[1, 1]]}],
            reason="Sample",
        )


def test_pack_lists_and_always_requires_checker(rec):
    from qsone.deliverables.tools import check_draft
    from qsone.engine.checker import has_numbers

    d = store.create(
        rec, kind="pack", variant="tender", title="Sample", language="en", actor="lead_qs"
    )
    assert store.list_deliverables(rec)[0]["kind"] == "pack"
    assert has_numbers(check_draft(rec, d)[0])


def test_review_export_preview_and_undo(rec):
    from qsone.deliverables import revert, review
    from qsone.deliverables.api import _export
    from qsone.deliverables.pack import preview

    d = store.create(
        rec, kind="pack", variant="tender", title="Sample", language="en", actor="lead_qs"
    )
    steps = [{"kind": "cover", "text": {"en": "Sample", "ar": "عينة"}}]
    c = changes.propose(
        rec, d, [{"op": "set_pack", "steps": steps}], actor="lead_qs", reason="Sample"
    )[0]
    changes.accept(rec, d, [c.id], actor="engineer")
    assert preview(rec, d, 2, 1)["image"].startswith("data:image/png;base64,")
    assert not review.closeout(rec, d)["can_sign_off"]
    revert.undo_accept(rec, d, 2, actor="engineer")
    assert store.view(rec, d)["steps"] == []
    changes.accept(rec, d, [c.id], actor="engineer")
    version = store.view(rec, d)["version"]
    review.record_check(
        rec,
        d,
        version_n=version,
        code="A",
        checker="scripted",
        same_provider=False,
        summary="Sample",
        comments=[],
    )
    revision = review.sign_off(rec, d, actor="engineer")
    assert len(PdfReader(BytesIO(_export(rec, d, "pdf", revision).body)).pages) == 1


def test_pack_keeps_file_provenance(rec):
    from qsone.records.files import add_file

    f = add_file(rec, "Sample tender.pdf", source(), actor="engineer")
    d = store.create(
        rec, kind="pack", variant="tender", title="Sample", language="en", actor="lead_qs"
    )
    c = changes.propose(
        rec,
        d,
        [{"op": "set_pack", "steps": [{"kind": "file", "file_id": f.id, "ranges": [[1, 1]]}]}],
        actor="lead_qs",
        reason="Sample",
    )[0]
    assert c.after["files"][f.id]["name"] == "Sample tender.pdf"
    changes.accept(rec, d, [c.id], actor="engineer")
    assert store.view(rec, d)["files"][f.id]["added_at"]


def test_migrates_populated_deliverables(data_dir, monkeypatch):
    from qsone.records import schema
    from qsone.records.project import Records
    from tests.samples import sample_document, sample_sheet

    migrations = schema.MIGRATIONS
    with monkeypatch.context() as m:
        m.setattr(schema, "MIGRATIONS", migrations[:-1])
        rec = Records.create(data_dir / "old", name="Sample", actor="engineer")
        d = sample_document(rec, sample_sheet(rec))
        before = store.view(rec, d)
    rec._migrate()
    assert store.view(rec, d) == before
    with rec.read() as conn:
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    store.create(rec, kind="pack", variant="tender", title="Sample", language="en", actor="lead_qs")
    rec.close()


def test_qpdf_repair_is_memory_only(monkeypatch):
    import os
    import shutil

    from qsone.deliverables import pack

    if not shutil.which("qpdf") or not hasattr(os, "memfd_create"):
        pytest.skip("qpdf memory repair unavailable")
    original = pack.PdfReader
    calls = 0

    def fail_once(stream):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ValueError("synthetic parser refusal")
        return original(stream)

    monkeypatch.setattr(pack, "PdfReader", fail_once)
    assert len(pack._reader(source()).pages) == 3
    assert calls == 2


def test_missing_qpdf_refuses_cleanly(monkeypatch):
    from qsone.deliverables import pack

    monkeypatch.setattr(pack.shutil, "which", lambda _: None)
    with pytest.raises(RecordsError):
        pack._reader(b"not a PDF")


def test_tool_registered_for_lead_and_deferred_group():
    from qsone.deliverables import tools  # noqa: F401
    from qsone.engine.tool_groups import group_of
    from qsone.engine.tools import REGISTRY

    assert group_of("pack_propose") == "documents"
    assert REGISTRY["pack_propose"].roles == {"lead"}


@pytest.mark.parametrize(
    "step",
    [
        {"kind": []},
        {"kind": "file", "file_id": "f", "ranges": []},
        {"kind": "stamp", "text": {"en": "Sample"}, "pages": [1], "position": "top"},
    ],
)
def test_malformed_step_refuses(step):
    with pytest.raises(RecordsError):
        validate_steps([step], lambda _: source())


def test_repeated_source_pages_get_independent_stamps():
    steps = [
        {"kind": "file", "file_id": "f", "ranges": [[1, 1], [1, 1]]},
        {"kind": "stamp", "text": {"en": "SAMPLE", "ar": "عينة"}, "pages": [1], "position": "top"},
    ]
    pdf = PdfReader(BytesIO(build(steps, lambda _: source(), "en")))
    assert "SAMPLE" in pdf.pages[0].extract_text()
    assert "SAMPLE" not in pdf.pages[1].extract_text()


def test_version_comparison_uses_engineer_words(rec):
    from qsone.deliverables.compare import compare

    d = store.create(
        rec, kind="pack", variant="tender", title="Sample", language="en", actor="lead_qs"
    )
    before = store.view(rec, d)
    c = changes.propose(
        rec,
        d,
        [
            {
                "op": "set_pack",
                "steps": [{"kind": "cover", "text": {"en": "Sample cover", "ar": "غلاف تجريبي"}}],
            }
        ],
        actor="lead_qs",
        reason="Sample",
    )[0]
    changes.accept(rec, d, [c.id], actor="engineer")
    result = compare(before, store.view(rec, d))
    words = "".join(s["text"] for s in result["blocks"][0]["segments"])
    assert "Sample cover" in words and "Cover" in words
    assert '"kind"' not in words


def test_password_protected_source_is_a_plain_refusal():
    writer = PdfWriter()
    writer.add_blank_page(200, 300)
    writer.encrypt("sample-only-password")
    out = BytesIO()
    writer.write(out)
    with pytest.raises(RecordsError):
        validate_steps(
            [{"kind": "file", "file_id": "f", "ranges": [[1, 1]]}], lambda _: out.getvalue()
        )
