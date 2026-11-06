"""Scripted reproductions of 6 November real-walk failures; sample values only."""

from types import SimpleNamespace

import pytest

from qsone.cli.walk import Walk, execute_steps, make_revision


def walker(reply, evidence):
    walk = Walk(SimpleNamespace(client=None))
    walk.last = {"reply": reply}
    walk.evidence["cited"] = evidence
    return walk


@pytest.mark.parametrize(
    "reply",
    [
        "According to the contract (page 58):\n\n* Delay damages: 0.2% per day.",
        'Total: **100,912,880.78 L.E.**\n\n***\n*Source: sample.xls, Sheet: "ALL", Row: 23*',
        "العملة هي الريال السعودي، الفقرة رقم 293.",
    ],
)
def test_citation_in_heading_or_source_line(reply):
    if "0.2" in reply:
        evidence = {"pieces": [{"text": "0.2% per day"}]}
        expected = {"value": "0.2", "page": 58}
    elif "ALL" in reply:
        evidence = {
            "sheet": "ALL",
            "rows": [{"code": "23", "cells": {"F": {"text": "100912880.78"}}}],
        }
        expected = {"value": "100912880.78", "sheet": "ALL", "row": 23}
    else:
        evidence = {"pieces": [{"text": "الريال السعودي", "locator": {"paragraph": 293}}]}
        expected = {"value": "الريال السعودي", "paragraph": 293}
    assert walker(reply, evidence).check("cited", expected)


def test_heading_citation_does_not_override_another_page():
    walk = walker(
        "Source page 58:\nRetention 10%.\nSource page 26:\nSecurity 350,000 USD.",
        {"pieces": [{"text": "350,000 USD"}]},
    )
    assert not walk.check("cited", {"value": "350000", "page": 58})
    assert walk.check("cited", {"value": "350000", "page": 26})


def test_revision_is_visible_with_inherited_crop_and_transform(tmp_path):
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import DecodedStreamObject, NameObject, RectangleObject

    from qsone.records.render import page_png

    source = tmp_path / "sample.pdf"
    writer = PdfWriter()
    page = writer.add_blank_page(width=600, height=800)
    page[NameObject("/CropBox")] = RectangleObject([100, 200, 500, 700])
    stream = DecodedStreamObject()
    stream.set_data(b"0 g 0 0 0 rg 0 0 0 0 re f 10 0 0 10 0 0 cm")
    page[NameObject("/Contents")] = stream
    writer.write(source)
    revision = make_revision(source, tmp_path / "scratch", page=1)
    assert "SAMPLE REVISION" in PdfReader(revision).pages[0].extract_text()
    assert page_png(source.read_bytes(), 1, 600) != page_png(revision.read_bytes(), 1, 600)


def test_failed_brief_reports_its_recorded_error():
    client = SimpleNamespace(get=lambda *a, **kw: {})
    walk = Walk(SimpleNamespace(client=client))

    def fail(step):
        return {
            "state": "failed",
            "events": [{"type": "data-error", "data": {"en": "Sample failure", "ar": "فشل عينة"}}],
        }

    walk.step = fail
    [entry] = execute_steps(walk, [{"ask": "sample"}], lambda _: False)
    assert entry["status"] == "FAIL"
    assert entry["error"]["en"] == "Sample failure"


def test_scripted_only_file_is_skipped_in_real_mode(tmp_path):
    from qsone.cli.walk import run

    file = tmp_path / "sample.yaml"
    file.write_text("name: sample\nscripted:\n- project: Sample\n")
    commands = SimpleNamespace(client=None, saved={"mode": "real"}, lang="en")
    assert run(commands, file)["status"] == "SKIPPED"


@pytest.mark.parametrize("fixed", [False, True])
def test_close_fixed_review_requires_accepted_linked_change_and_fresh_check(fixed):
    from qsone.cli.texts import CliError

    calls = []

    def get(route, **kwargs):
        if route.endswith("/closeout"):
            return {"blocking": [{"id": "comment"}], "check": {"version_n": 2, "code": "A"}}
        if route.endswith("/changes"):
            return {"changes": [{"comment_id": "comment", "status": "accepted"}] if fixed else []}
        return {"version": 2}

    def post(route, body=None):
        calls.append(route)
        return {}

    walk = Walk(SimpleNamespace(client=SimpleNamespace(get=get, post=post)))
    walk.project = "sample"
    walk.variables["deliverable"] = "pack"
    if fixed:
        walk.step({"review": "close_fixed"})
        assert calls == ["/projects/sample/comments/comment/close"]
    else:
        with pytest.raises(CliError):
            walk.step({"review": "close_fixed"})
        assert not calls


def test_boq_sections_counts_work_groups_not_summary_lines():
    walk = walker("", {})
    walk.boq = {
        "sheets": [
            {
                "file_id": "sample",
                "sources": {"q": {"locator": {"sheet": "BOQ", "row": 4}}},
                "rows": [
                    {"kind": "item", "cells": {"quantity": {"source": "q"}}},
                    {"kind": "section", "title": "Health"},
                    {"kind": "section", "title": "Pipe sizes follow"},
                    {"kind": "section", "title": "Electrical"},
                    {"kind": "section", "title": "Total"},
                    {"kind": "section", "title": "Discount"},
                    {"kind": "section", "title": "New works"},
                ],
            }
        ]
    }
    walk.report = {
        "files": [
            {
                "id": "sample",
                "sheets": [
                    {
                        "sheet": "BOQ",
                        "sections": [
                            {"row": 29, "title": "Health"},
                            {"row": 43, "title": "Electrical"},
                            {"row": 53, "title": "New works"},
                        ],
                    }
                ],
            }
        ]
    }
    assert walk.check("boq_sections", 4)


def test_stream_discards_answer_retracted_by_truth_guard(tmp_path):
    import json

    import httpx

    from qsone.cli.client import Client
    from qsone.cli.follow import follow

    saved = {"port": 12345, "secret": "sample", "cards": {}}
    events = [
        {"type": "text-delta", "delta": "Wrong 😀 350000"},
        {
            "type": "data-redo",
            "data": {"from": 0, "to": len("Wrong 😀 350000".encode("utf-16-le")) // 2},
        },
        {"type": "text-delta", "delta": "Source not read."},
        {"type": "data-status", "id": "sample", "data": {"state": "done"}},
    ]

    def respond(request):
        if request.url.path.endswith("/stream"):
            return httpx.Response(
                200, text="".join("data: " + json.dumps(e) + "\n\n" for e in events)
            )
        return httpx.Response(200, json={})

    client = Client(saved)
    client.http.close()
    client.http = httpx.Client(base_url="http://localhost", transport=httpx.MockTransport(respond))
    try:
        assert (
            follow(client, saved, tmp_path / "session.json", "sample")["reply"]
            == "Source not read."
        )
    finally:
        client.close()
