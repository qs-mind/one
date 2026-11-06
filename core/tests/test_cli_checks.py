"""Pure walk assertions reject false coverage without accessing files or providers."""

from copy import deepcopy

import pytest


def concrete_sheet():
    return {
        "rows": [
            {"id": "heading", "kind": "section", "title": "Sample concrete"},
            {
                "id": "earth",
                "kind": "item",
                "cells": {"description": {"text": "Sample excavation"}},
            },
            {
                "id": "plain",
                "kind": "item",
                "cells": {"description": {"text": "خرسانة عادية (عينة)"}},
            },
            {
                "id": "reinforced",
                "kind": "item",
                "cells": {"description": {"text": "خرسانة مسلحة (عينة)"}},
            },
        ]
    }


def changes(*rows):
    return {
        "changes": [
            {
                "status": "pending",
                "op": {"op": "set_number", "row": row, "name": "rate", "value": "105"},
            }
            for row in rows
        ]
    }


@pytest.mark.parametrize(
    "rows,passed",
    [
        (("plain", "reinforced"), True),
        (("plain",), False),
        (("plain", "reinforced", "earth"), False),
        (("plain", "reinforced", "plain"), False),
        ((), False),
    ],
)
def test_concrete_changes_cover_only_every_concrete_item(rows, passed):
    from qsone.cli.checks import changes_target

    assert (
        changes_target(concrete_sheet(), changes(*rows), {"description_contains": "خرسانة"})
        is passed
    )


@pytest.mark.parametrize("mutation", ["quantity", "accepted", "field"])
def test_concrete_changes_require_pending_rate_operations(mutation):
    from qsone.cli.checks import changes_target

    observed = changes("plain", "reinforced")
    change = observed["changes"][0]
    if mutation == "quantity":
        change["op"]["name"] = "quantity"
    elif mutation == "field":
        change["op"]["op"] = "set_field"
    else:
        change["status"] = mutation
    assert not changes_target(concrete_sheet(), observed, {"description_contains": "خرسانة"})


def pack():
    return {
        "pages": 4,
        "page_texts": [
            "Sample cover\nPage 1 of 4",
            "Sample divider\nPage 2 of 4",
            "Sample tender form\nPage 3 of 4",
            "Sample tender form\nPage 4 of 4",
        ],
        "bookmarks": [{"title": "Cover", "page": 1}, {"title": "Tender", "page": 3}],
        "signature_fields": [{"name": "ONEIntegritySeal", "type": "/Sig", "has_contents": True}],
    }


@pytest.mark.parametrize("language", ["en", "ar"])
def test_pack_checks_bookmarks_seal_and_unique_duplicate_page_numbers(language):
    from qsone.cli.checks import pack_integrity

    observed = pack()
    if language == "ar":
        observed["page_texts"] = [
            text.replace(f"Page {i} of 4", f"صفحة {i} من 4")
            for i, text in enumerate(observed["page_texts"], 1)
        ]
    assert pack_integrity(
        observed,
        {
            "bookmarks": [{"title": "Cover", "page": 1}, {"title": "Tender", "page": 3}],
            "duplicates": [[3, 4]],
            "seal": True,
            "page_numbers": True,
        },
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_bookmark",
        "wrong_bookmark_page",
        "missing_seal",
        "empty_seal",
        "wrong_page",
        "duplicate_footer",
        "different_body",
        "missing_text",
    ],
)
def test_pack_rejects_incomplete_or_corrupt_export_observations(mutation):
    from qsone.cli.checks import pack_integrity

    observed = pack()
    if mutation == "missing_bookmark":
        observed["bookmarks"].pop()
    elif mutation == "wrong_bookmark_page":
        observed["bookmarks"][1]["page"] = 4
    elif mutation == "missing_seal":
        observed["signature_fields"] = []
    elif mutation == "empty_seal":
        observed["signature_fields"][0]["has_contents"] = False
    elif mutation == "wrong_page":
        observed["page_texts"][3] = "Sample tender form\nPage 3 of 4"
    elif mutation == "duplicate_footer":
        observed["page_texts"][3] += "\nPage 3 of 4"
    elif mutation == "different_body":
        observed["page_texts"][3] = "Different form\nPage 4 of 4"
    else:
        observed["page_texts"].pop()
    assert not pack_integrity(
        observed,
        {
            "bookmarks": [{"title": "Tender", "page": 3}],
            "duplicates": [[3, 4]],
            "seal": True,
            "page_numbers": True,
        },
    )


def test_calculated_numbers_requires_calculation_source_for_every_expected_number():
    from qsone.cli.checks import calculated_numbers

    view = {
        "rows": [{"cells": {"amount": {"value": "1000", "source": "calc"}}}],
        "refs": {"num:n": {"value": "2000", "source": "calc"}},
        "sources": {"calc": {"kind": "calculation", "locator": {"calculation": "c"}}},
    }
    assert calculated_numbers(view, ["١٬٠٠٠", "2000.00"])
    assert not calculated_numbers(view, [100])
    changed = deepcopy(view)
    changed["sources"]["calc"]["kind"] = "file"
    assert not calculated_numbers(changed, [1000])
    assert not calculated_numbers(view, [1000, 3000])


@pytest.mark.parametrize("language", ["en", "ar"])
def test_pack_integrity_accepts_actual_core_sealed_duplicate_export(memory_keyring, language):
    from io import BytesIO

    import pypdfium2 as pdfium
    from pypdf import PdfReader

    from qsone.cli.checks import pack_integrity
    from qsone.deliverables.pack import build
    from tests.samples import sample_pdf

    data = sample_pdf([["SAMPLE FORM"]])
    steps = [
        {
            "kind": "file",
            "file_id": "f",
            "ranges": [[1, 1]],
            "title": {"en": "Form", "ar": "النموذج"},
        },
        {"kind": "file", "file_id": "f", "ranges": [[1, 1]]},
        {"kind": "page_numbers"},
        {"kind": "seal"},
    ]
    exported = build(steps, lambda _: data, language)
    reader = PdfReader(BytesIO(exported))
    page_texts = []
    with pdfium.PdfDocument(exported) as pdf:
        for index in range(len(pdf)):
            page = pdf[index]
            text = page.get_textpage()
            page_texts.append(text.get_text_range())
            text.close()
            page.close()
    fields = reader.get_fields()
    observed = {
        "pages": len(reader.pages),
        "page_texts": page_texts,
        "bookmarks": [
            {"title": node.title, "page": reader.get_destination_page_number(node) + 1}
            for node in reader.outline
        ],
        "signature_fields": [
            {
                "name": name,
                "type": str(field.get("/FT")),
                "has_contents": bool(field.get("/V", {}).get("/Contents")),
            }
            for name, field in fields.items()
        ],
    }
    title = "Form" if language == "en" else "النموذج"
    assert pack_integrity(
        observed,
        {
            "bookmarks": [{"title": title, "page": 1}],
            "duplicates": [[1, 2]],
            "seal": True,
            "page_numbers": True,
        },
    ), page_texts
