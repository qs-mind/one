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
