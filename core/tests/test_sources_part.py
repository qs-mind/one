"""`data-sources` (contract 3.1, rules 6 and 7): the ledger sources of the reply's figures, then the
places the Lead's own tool results named, each once; live at the reply's end and the same when
the chat is read again. Scripted models only; synthetic «عينة» data only."""

import pytest
from pydantic import BaseModel

from qsone import phase1_contract as c
from qsone.deliverables.store import sources_of
from qsone.engine import agents, sources_part
from qsone.engine.tools import REGISTRY, Tool, register
from qsone.engine.types import Data
from qsone.tools.cite import SourceRef, render, source_line
from tests.engine_fakes import call, scripted
from tests.engine_fakes import text as said
from tests.team_samples import TeamFakeHost, lead_ctx, sample_ledger
from tests.test_engine_runner import (  # noqa: F401 - fixtures
    finish,
    links,
    make_engine,
    no_budget_card,
    project,
    registry,
    started,
)

pytestmark = pytest.mark.anyio
FILE = "5a" + "0" * 29 + "f"
READ = "2026-11-09 08:00"


def test_a_sources_line_becomes_a_source():
    page = SourceRef(f"file:{FILE}#page=48", "03 المواصفات.pdf - عينة", READ)
    boxed = SourceRef(
        f"file:{FILE}#page=3",
        "03 المواصفات.pdf - عينة",
        READ,
        locator={"page": 3, "box": [72, 310.5, 523, 342]},
    )
    web = SourceRef("web:7f2c#1", "Rebar | prices - sample", READ, "2026-10-30", "https://x.test/a")
    lines = [source_line(s) for s in (page, boxed, web)]
    found = [sources_part._line(line) for line in lines]
    assert found[0] == {
        "kind": "file",
        "title": "03 المواصفات.pdf - عينة",
        "file_name": "03 المواصفات.pdf - عينة",
        "file_id": FILE,
        "locator": {"page": 48},
        "url": None,
        "dated": None,
        "quote": None,
    }
    assert found[1]["locator"] == {"page": 3, "box": [72, 310.5, 523, 342]}
    assert found[2] | {"locator": {}} == {
        "kind": "web",
        "title": "Rebar / prices - sample",
        "file_name": None,
        "file_id": None,
        "locator": {},
        "url": "https://x.test/a",
        "dated": "2026-10-30",
        "quote": None,
    }
    for source in found:
        c.Source.model_validate(source)
    assert sources_part._line("- not a source line") is None


@pytest.fixture
def ledger_tool():
    """A read for the Lead whose result names a ledger number and a place in a file."""
    made: dict = {}

    class NoArgs(BaseModel):
        pass

    async def read(ctx, args):
        place = SourceRef(f"file:{FILE}#page=48", "03 المواصفات.pdf - عينة", READ)
        again = SourceRef(f"file:{FILE}#page=48", "03 المواصفات.pdf - عينة", READ)
        data = {"number_id": made["quantity"], "value": "120"}
        return render("The quantity (sample).", data=data, sources=[place, again])

    words = {"en": "read the ledger", "ar": "قرا الدفتر"}
    register(Tool("ledger_sample", "Read - sample.", NoArgs, "read", read, lambda a: words))
    before = agents.LEAD_TOOLS
    agents.LEAD_TOOLS = (*before, "ledger_sample")
    yield made
    agents.LEAD_TOOLS = before
    REGISTRY.pop("ledger_sample")


async def test_sources_live_and_stored(make_engine, registry, project, ledger_tool):  # noqa: F811
    rec = registry.get(project)
    ledger_tool.update(await sample_ledger(lead_ctx(rec, TeamFakeHost())))
    lead = scripted(call("ledger_sample", {}), said("الكمية 120 م3 - عينة"))
    engine = await started(make_engine(links(lead=lead)))
    brief = await engine.start_brief(project, "كام الكمية؟ - عينة")
    live = [e for e in await finish(engine, brief) if isinstance(e, Data) and e.name == "sources"]
    ledger = sources_of(rec, [ledger_tool["source"]])[ledger_tool["source"]]
    place = sources_part._line(
        source_line(SourceRef(f"file:{FILE}#page=48", "03 المواصفات.pdf - عينة", READ))
    )
    assert [e.data for e in live] == [{"sources": [ledger, place]}]  # the figure's, then the read
    engine._briefs.pop(brief, None)  # read from the store, as after a restart
    reply = engine.chat_messages(project)[-1]
    stored = [p for p in reply["parts"] if p["type"] == "data-sources"]
    assert stored == [{"type": "data-sources", "id": brief, "data": live[0].data}]
    c.SourcesPart.model_validate(stored[0]["data"])


async def test_a_reply_with_nothing_to_prove_has_no_sources(make_engine, project):  # noqa: F811
    engine = await started(make_engine(links(lead=scripted(said("تمام - عينة")))))
    brief = await engine.start_brief(project, "ابدأ - عينة")
    events = await finish(engine, brief)
    assert not [e for e in events if isinstance(e, Data) and e.name == "sources"]
