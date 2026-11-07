import json
from types import SimpleNamespace

import pytest

from qsone.records import files
from qsone.records.mapping import store
from tests.samples import sample_pdf


@pytest.mark.anyio
async def test_overview_find_and_empty_facts(rec):
    from qsone.tools.project_map import MapArgs, read_map

    f = files.add_file(rec, "sample.pdf", sample_pdf([["sample"]]), actor="engineer")
    with rec.write("one") as c:
        store.write(
            c,
            rec,
            "map_files",
            {
                "file_id": f.id,
                "key_pages": [{"label": {"en": "Contract data", "ar": "بيانات العقد"}, "page": 1}],
            },
        )
    ctx = SimpleNamespace(rec=rec)
    found = json.loads(await read_map(ctx, MapArgs(mode="find", label="Contract")))
    assert found["files"][0]["file_id"] == f.id
    assert json.loads(await read_map(ctx, MapArgs(mode="facts")))["facts"] == []
    assert json.loads(await read_map(ctx, MapArgs(mode="links")))["links"] == []


def test_max_tool_steps():
    from qsone.cli.checks import max_tool_steps

    events = [
        {
            "type": "data-worklog",
            "data": {"steps": [{"tool": "project_map"}, {"tool": None}, {"tool": "files_read"}]},
        }
    ]
    assert max_tool_steps(events, 2)
    assert not max_tool_steps(events, 1)
    assert not max_tool_steps([], 5)


def test_walk_map_key_pages():
    from qsone.cli.walk import Walk

    walk = Walk(SimpleNamespace(client=None))
    walk.observed = {
        "map": {
            "files": [
                {
                    "file_id": "sample",
                    "key_pages": [
                        {"label": {"en": "Contract data", "ar": "بيانات العقد"}, "page": 58}
                    ],
                }
            ]
        }
    }
    assert walk.check("map_key_pages", [{"label": "Contract data", "page": 58}])
    assert not walk.check("map_key_pages", [{"label": "Bid data", "page": 26}])


@pytest.mark.anyio
async def test_file_detail_includes_fact_verification_and_links(rec):
    from qsone.records.mapping import facts, links
    from qsone.tools.project_map import MapArgs, read_map

    f = files.add_file(
        rec,
        "sample.pdf",
        sample_pdf([["Retention 10%. See Clause 14.3"], ["14.3 Payment 30 days"]]),
        actor="engineer",
    )
    ids = facts.accept(
        rec,
        [
            dict(
                name={"en": "Retention", "ar": "المحتجز"},
                value="10%",
                evidence="Retention 10%",
                file_id=f.id,
                locator={"page": 1},
            )
        ],
    )
    links.step(rec, f.id)
    result = json.loads(
        await read_map(SimpleNamespace(rec=rec), MapArgs(mode="file", file_id=f.id))
    )
    assert result["facts"][0]["verification"]["en"] == "Read by ONE, not checked"
    assert result["links"]
    facts.update(rec, ids[0], confirm=True)
    result = json.loads(await read_map(SimpleNamespace(rec=rec), MapArgs(mode="facts")))
    assert result["facts"][0]["verification"]["en"] == "Confirmed"


def test_walk_fact_states_sources_and_links():
    from qsone.cli.walk import Walk

    walk = Walk(SimpleNamespace(client=None))
    walk.observed = {
        "map_facts": [
            {"file_id": "sample", "locator": {"page": 58}, "state": "found", "confirmed_at": None}
        ],
        "map_links": [{"from_file_id": "sample", "to_file_id": "sample"}],
    }
    assert walk.check("map_fact_sources", True)
    assert walk.check("map_fact_states", ["found"])
    assert walk.check("map_links_min", 1)
    assert not walk.check("map_fact_states", ["blank"])


@pytest.mark.anyio
async def test_local_evidence_is_available_without_ai_and_drawings_are_paged(rec):
    from qsone.tools.project_map import MapArgs, read_map

    f = files.add_file(rec, "electrical sample.pdf", sample_pdf([["sample"]]), actor="engineer")
    with rec.write("one") as c:
        c.execute("UPDATE files SET folder='Tender/Electrical' WHERE id=?", (f.id,))
        store.write(
            c,
            rec,
            "map_files",
            {
                "file_id": f.id,
                "read_how": "text",
                "structure": {"headings": [{"text": "Electrical schedules", "page": 1}]},
            },
        )
        store.write(
            c,
            rec,
            "map_tables",
            {
                "file_id": f.id,
                "locator": {"page": 1},
                "header": ["Item", "Quantity"],
                "looks_like_boq": 1,
                "row_count": 2,
                "column_guess": {},
            },
        )
        for i in range(3):
            store.write(
                c,
                rec,
                "map_sheets",
                {
                    "file_id": f.id,
                    "sheet": str(i),
                    "number": f"E-{i}",
                    "title": "Main single line diagram" if i == 0 else "Electrical lighting",
                    "revision": "A",
                    "scale": "1:100",
                    "discipline": "electrical",
                    "counts": {"BREAKER": 7, "LIGHT": 2, "SOCKET": 1},
                    "source": {"page": 1},
                    "state": "local",
                },
            )
    ctx = SimpleNamespace(rec=rec)
    for mode in ("overview", "file", "find"):
        result = json.loads(
            await read_map(ctx, MapArgs(mode=mode, file_id=f.id, label="E-0", limit=2))
        )
        row = result if mode == "file" else result["files"][0]
        assert row["name"] == "electrical sample.pdf"
        assert row["folder"] == "Tender/Electrical"
        assert row["kind"] == "pdf" and row["pages"] == 1 and row["read_how"] == "text"
        assert row["headings"][0]["text"] == "Electrical schedules"
        assert row["boq_tables"][0]["locator"] == {"page": 1}
        assert len(row["sheets"]) == 2 and row["sheets_next_page"] == 2
        assert row["sheets"][0]["number"] == "E-0"
        assert row["sheets"][0]["counts"]["BREAKER"] == 7
        assert row["sheets"][0]["file_id"] == f.id
        assert row["sheets"][0]["counts_next_page"] == 2
    second = json.loads(await read_map(ctx, MapArgs(mode="file", file_id=f.id, page=2, limit=2)))
    assert [s["number"] for s in second["sheets"]] == ["E-2"]
    for query in ("electrical sample", "Electrical schedules", "E-0", "Main single line"):
        found = json.loads(await read_map(ctx, MapArgs(mode="find", label=query)))
        assert found["files"][0]["file_id"] == f.id

    blocks = json.loads(
        await read_map(ctx, MapArgs(mode="file", file_id=f.id, counts_page=2, limit=2))
    )
    assert blocks["sheets"][0]["counts"] == {"SOCKET": 1}
    assert blocks["sheets"][0]["counts_next_page"] is None


@pytest.mark.anyio
async def test_tool_call_keeps_its_own_sheet_pagination(rec):
    from qsone.engine.tools import call
    from tests.fakes_tools import tool_ctx

    f = files.add_file(rec, "sample.pdf", sample_pdf([["sample"]]), actor="engineer")
    with rec.write("one") as c:
        for i in range(3):
            store.write(
                c, rec, "map_sheets", {"file_id": f.id, "sheet": str(i), "number": f"E-{i}"}
            )
    answer = await call(
        "project_map", {"mode": "file", "file_id": f.id, "page": 2, "limit": 2}, tool_ctx(rec)
    )
    assert '"number": "E-2"' in answer


@pytest.mark.anyio
async def test_sheet_default_lists_thirty_sheets_across_ten_files(rec):
    from qsone.tools.project_map import MapArgs, read_map

    for file in range(10):
        f = files.add_file(rec, f"sample {file}.txt", f"sample {file}".encode(), actor="engineer")
        with rec.write("one") as c:
            for sheet in range(3):
                store.write(
                    c,
                    rec,
                    "map_sheets",
                    {
                        "file_id": f.id,
                        "sheet": str(sheet),
                        "number": f"EL-{file * 3 + sheet:03}",
                        "title": "Sample electrical",
                    },
                )
    result = json.loads(await read_map(SimpleNamespace(rec=rec), MapArgs(mode="sheets")))
    assert len(result["sheets"]) == 30 and result["next_page"] is None
    assert set(result["sheets"][0]) == {"number", "title", "file", "layout"}
    assert MapArgs(mode="sheets", limit=100).limit == 100
