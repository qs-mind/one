"""The Lead can answer drawing questions from local evidence, with scripted AI only."""

# ruff: noqa: F811 (imported runner fixtures)

import asyncio
import json

from pydantic_ai.messages import ModelRequest, ToolReturnPart

from qsone.engine.types import Asked, Unsourced
from qsone.records import files
from qsone.records.mapping import store
from tests.engine_fakes import call, scripted
from tests.samples import sample_pdf
from tests.test_engine_runner import (  # noqa: F401
    finish,
    links,
    make_engine,
    no_budget_card,
    project,
    registry,
    started,
)
from tests.test_truth_runner import reply


async def test_lead_answers_electrical_sheets_and_mccb_from_local_map(
    make_engine, project, registry
):
    rec = registry.get(project)
    file = files.add_file(rec, "sample-electrical.pdf", sample_pdf([["sample"]]), actor="t")
    with rec.write("one") as c:
        store.write(
            c,
            rec,
            "map_sheets",
            {
                "file_id": file.id,
                "sheet": "Model",
                "number": "E-101",
                "title": "Main single line diagram",
                "discipline": "electrical",
                "counts": {"MCCB": 7},
                "source": {"page": 1},
                "state": "local",
            },
        )

    def answer(messages, info):
        results = [
            part.content
            for message in messages
            if isinstance(message, ModelRequest)
            for part in message.parts
            if isinstance(part, ToolReturnPart) and part.tool_name == "project_map"
        ]
        result = results[-1]
        data = json.loads(result[result.index("{") : result.rindex("}") + 1])
        sheet = data["files"][0]["sheets"][0]
        return (
            f"{sheet['number']}: {sheet['title']}; MCCB: "
            f"{sheet['counts']['MCCB']} pcs "
            f"(source: {data['files'][0]['name']}, drawing {sheet['number']})."
        )

    lead = scripted(call("project_map", {"mode": "find", "label": "electrical"}), answer)
    engine = await started(make_engine(links(lead=lead)))
    brief = await engine.start_brief(project, "List electrical sheets and MCCB counts.")
    events = await asyncio.wait_for(finish(engine, brief), 10)
    assert lead.calls == 2
    assert "E-101: Main single line diagram; MCCB: 7 pcs" in reply(events)
    assert "source: sample-electrical.pdf" in reply(events)
    assert not [event for event in events if isinstance(event, (Asked, Unsourced))]
