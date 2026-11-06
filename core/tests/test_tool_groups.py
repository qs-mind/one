"""What the Lead is sent: its tools in groups (`engine.tool_groups`), and the chat's earlier
Briefs as words and a note of their steps (`runner.heard`)."""

# ruff: noqa: F811 (the engine fixtures, imported)
import pytest
from pydantic_ai.messages import ModelRequest, RetryPromptPart, ToolReturnPart, UserPromptPart

from qsone.engine import tool_groups
from qsone.engine.runner import STEPS_NOTE
from tests.engine_fakes import call, scripted
from tests.engine_fakes import text as said
from tests.test_engine_runner import (  # noqa: F401 - fixtures
    finish,
    links,
    make_engine,
    project,
    registry,
    started,
)

pytestmark = pytest.mark.anyio


def _then(record, step):
    def both(messages, info):
        record(messages, info)
        return step

    return both


async def test_the_lead_is_sent_a_group_once_it_opens_it(make_engine, project):
    seen: list = []

    def tools(messages, info):
        seen.append([t.name for t in info.function_tools])

    lead = scripted(
        _then(tools, call(tool_groups.OPEN, {"open": ["numbers"]})),
        _then(tools, said("تمام - عينة")),
    )
    engine = await started(make_engine(links(lead=lead)))
    await finish(engine, await engine.start_brief(project, "احسب - عينة"))
    first, second = seen
    assert "search_records" in first and tool_groups.OPEN in first
    assert not set(first) & {t for group in tool_groups.GROUPS.values() for t in group}
    assert set(tool_groups.GROUPS["numbers"]) <= set(second)
    assert second[: len(first)] == first  # the start stays the same for the provider's cache
    assert "boq_import" not in second


async def test_a_tool_not_sent_can_still_be_called_and_opens_its_group(make_engine, project):
    seen: list = []
    found: list = []

    def tools(messages, info):
        seen.append({t.name for t in info.function_tools})
        found.extend(
            p
            for m in messages
            if isinstance(m, ModelRequest)
            for p in m.parts
            if isinstance(p, ToolReturnPart | RetryPromptPart)
        )

    lead = scripted(
        _then(tools, call("explain_number", {"number": "0" * 32})),
        _then(tools, said("تمام - عينة")),
    )
    engine = await started(make_engine(links(lead=lead)))
    await finish(engine, await engine.start_brief(project, "اشرح الرقم - عينة"))
    [result] = found
    assert result.tool_name == "explain_number"
    assert "Unknown tool" not in str(result.content)  # ONE ran it and answered
    assert "explain_number" not in seen[0] and "calculate" in seen[1]


async def test_an_earlier_brief_reaches_the_lead_as_words_and_a_note_of_its_steps(
    make_engine, project
):
    later: list = []

    def hears(messages, info):
        later.extend(messages)

    lead = scripted(
        call("files_list"),
        said("الملفات: لا شيء بعد - عينة"),
        _then(hears, said("تاني - عينة")),
    )
    engine = await started(make_engine(links(lead=lead)))
    await finish(engine, await engine.start_brief(project, "إيه الملفات؟ - عينة"))
    await finish(engine, await engine.start_brief(project, "تاني سؤال - عينة"))
    asked = [
        p.content
        for m in later
        if isinstance(m, ModelRequest)
        for p in m.parts
        if isinstance(p, UserPromptPart)
    ]
    assert "إيه الملفات؟ - عينة" in asked and "تاني سؤال - عينة" in asked
    [note] = [a for a in asked if isinstance(a, str) and a.startswith(STEPS_NOTE)]
    assert "- files_list" in note
    # the earlier tool call and its result are not sent again
    assert not [p for m in later for p in m.parts if p.part_kind in ("tool-call", "tool-return")]
    assert "الملفات: لا شيء بعد - عينة" in str(later)
