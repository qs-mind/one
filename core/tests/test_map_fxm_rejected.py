import json
from types import SimpleNamespace

import pytest

from qsone.records import files
from qsone.records.mapping import facts, store


@pytest.mark.parametrize("value", ["1% - 2%", "1%–2%"])
def test_bracketed_rtl_percent_range(value):
    text = "ضمان ابتدائي بقيمة تتراوح من )2%( إلى )1%("
    assert facts.grounded(text, {"value": value, "evidence": text})


@pytest.mark.anyio
async def test_rejected_proposals_stay_separate_and_visible(rec):
    from qsone.tools.project_map import MapArgs, read_map

    f = files.add_file(rec, "sample.txt", b"Bid security 1%", actor="engineer")
    p = {
        "name": {"en": "Security", "ar": "الضمان"},
        "value": "9%",
        "file_id": f.id,
        "locator": {},
        "state": "found",
        "evidence": "Invented requirement 9%",
    }
    assert facts.accept(rec, [p], picture_fallback=False) == []
    assert store.entries(rec, "facts")["facts"] == []
    rejected = store.rejected_entries(rec)["rejected"]
    assert rejected[0]["proposal"] == p
    assert rejected[0]["reason"] == "not_grounded"
    result = json.loads(await read_map(SimpleNamespace(rec=rec), MapArgs(mode="facts")))
    assert result["facts"] == []
    assert result["rejected"][0]["verification"]["en"] == "Found but not verified"


def test_cli_rejected_argument():
    from qsone.cli.__main__ import parser

    args = parser().parse_args(["facts", "sample", "--rejected"])
    assert args.rejected


@pytest.mark.anyio
async def test_approved_pass_keeps_rejected_before_no_facts_error(rec):
    f = files.add_file(rec, "sample.txt", b"Bid security 1%", actor="engineer")

    async def read(fid, locator):
        return "Bid security 1%"

    async def request(prompt, schema, instructions):
        return schema(
            facts=[
                {
                    "name": {"en": "Security", "ar": "الضمان"},
                    "value": "9%",
                    "file_id": f.id,
                    "locator": {},
                    "state": "found",
                    "evidence": "Invented requirement 9%",
                }
            ]
        )

    with pytest.raises(facts.NoTenderFacts):
        await facts.run_approved(rec, read=read, request=request, file_ids=[f.id])
    assert store.rejected_entries(rec)["rejected"][0]["reason"] == "not_grounded"


def test_cli_rejected_pages_are_all_loaded():
    from qsone.cli.commands import Commands

    calls = []

    def get(route, **params):
        calls.append((route, params))
        return {
            "rejected": [{"id": "b" if params.get("cursor") else "a"}],
            "next_cursor": None if params.get("cursor") else "a",
        }

    command = Commands(SimpleNamespace(get=get), {}, None)
    result = command.map_entries("sample", "facts", rejected=True)
    assert [r["id"] for r in result["rejected"]] == ["a", "b"]
    assert all(p["rejected"] for _, p in calls)


def test_rejected_cli_text_is_bilingual():
    from qsone.cli.__main__ import plain

    row = {"rejected": [{"reason": "not_grounded"}]}
    assert "not_grounded" not in plain(row, "en")
    assert "not_grounded" not in plain(row, "ar")
    assert "rejected" not in plain(row, "ar")


def test_scripted_pass_retains_proposal_for_unread_page(rec):
    from tests.samples import sample_pdf

    f = files.add_file(
        rec, "sample.pdf", sample_pdf([["Bid security 1%"], ["Cover"]]), actor="engineer"
    )
    p = {
        "name": {"en": "Security", "ar": "الضمان"},
        "value": "9%",
        "file_id": f.id,
        "locator": {"page": 2},
        "state": "found",
        "evidence": "Invented 9%",
    }
    assert facts.run(rec, read=lambda *_: "Bid security 1%", propose=lambda _: [p]) == []
    assert store.rejected_entries(rec)["rejected"][0]["proposal"] == p
