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
