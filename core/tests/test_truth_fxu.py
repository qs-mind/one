"""Retest 11: synthetic tender evidence, scripted models only."""

# ruff: noqa: F811
import json

import pytest

from qsone.engine import agents, truth
from qsone.records import files
from qsone.records.mapping import store
from tests.engine_fakes import call, scripted, text
from tests.test_truth_runner import (  # noqa: F401
    finish,
    links,
    make_engine,
    no_budget_card,
    project,
    registry,
    started,
    team_steps,
)


async def test_retest_11_read_sequence():
    main = "كراسة الشروط والمواصفات.pdf"
    other = "شروط تقديم العطاء.pdf"
    returns = []
    sequence = [
        ("project_search", None),
        ("project_search", None),
        ("read_chunk", "1-4"),
        ("files_read", "19-20"),
        ("project_search", None),
        ("read_chunk", "6-8"),
        ("files_read", "15-17"),
        ("project_search", None),
        ("read_chunk", "19-20"),
        ("project_search", None),
        ("files_read", "8,18"),
        ("read_chunk", "7"),
        ("files_read", "7"),
        ("project_search", None),
        ("read_chunk", "7,17"),
        ("files_read", "3"),
    ]
    for i, (tool, pages) in enumerate(sequence):
        if pages is None:
            returns.append((tool, "No sample search hits"))
            continue
        nums = [int(n) for n in pages.replace("-", ",").split(",")]
        if "-" in pages:
            nums = list(range(nums[0], nums[-1] + 1))
        filename = other if i == len(sequence) - 1 else main
        body = f"file_id: {filename} | file: {filename}\n" if tool == "files_read" else ""
        for n in nums:
            loc = {"page": n}
            header = (
                loc
                if tool == "files_read"
                else {"file_id": filename, "file": filename, "locator": loc}
            )
            body += json.dumps(header, ensure_ascii=False) + "\n"
            body += (
                "عينة فتح العروض ١٦/\u200f٠٤/١٤٤٨ الترسية ٢٩/٠٦/١٤٤٨\n"
                if n == 7
                else "سريان العرض ٩٠ يوم\n"
                if n == 17 or filename == other
                else "عينة شروط المناقصة\n"
            )
        returns.append((tool, body))
    reply = (
        f"Opening of offers: 16/04/1448. Source: {main}, page 7.\n"
        "Award: 29/06/1448. Source: same, page 7.\n"
        f"Bid validity: 90 days. Source: {main}, page 17 (article 9), "
        f"and {other}, page 3 (article 11)."
    )

    from types import SimpleNamespace

    from pydantic_ai import Agent, Tool
    from pydantic_ai.messages import ModelMessagesTypeAdapter

    from qsone.engine.runner import _Brief

    def read_result(index: int) -> str:
        return returns[index][1]

    model = scripted(
        *(call(name, {"index": i}) for i, (name, _) in enumerate(returns)), text(reply)
    )
    agent = Agent(
        model,
        tools=[
            Tool(read_result, name=name) for name in ("project_search", "files_read", "read_chunk")
        ],
    )
    result = await agent.run("Sample opening/award/works start dates, bid security, duration")
    original = result.all_messages()
    saved = ModelMessagesTypeAdapter.dump_json(original)
    # The request's compact stubs never replace the saved full returns used by truth.
    trimmed = agents.trim_history(original, limit_tokens=1)
    assert trimmed != original
    assert ModelMessagesTypeAdapter.dump_json(original) == saved
    host = SimpleNamespace(
        store=SimpleNamespace(runs=lambda _: [{"history": saved}]), brief_id="sample"
    )
    reads = _Brief._read_returns(host)
    assert truth.unread_citations(result.output, reads) == []
    assert model.calls == len(sequence) + 1
    assert truth.unread_citations(reply.replace("16/04/1448", "17/04/1448"), reads)
    # "same" binds to the preceding filename; another file at page 7 is insufficient.
    assert truth.unread_citations(reply, [(n, r) for n, r in reads if main not in r])


@pytest.mark.parametrize("reply", ["Bid security: not found.", "الضمان الابتدائي غير موجود."])
@pytest.mark.parametrize(
    "state,matching,value",
    [
        ("found", True, "1 بالمائة من القيمة الإجمالية للعرض"),
        ("blank", True, "1 بالمائة من القيمة الإجمالية للعرض"),
        ("found", False, "1 بالمائة من القيمة الإجمالية للعرض"),
        ("found", True, "   "),
    ],
)
async def test_summary_absence_one_retry(
    make_engine, project, registry, reply, state, matching, value
):
    rec = registry.get(project)
    f = files.add_file(rec, "sample.pdf", b"sample tender", actor="engineer")
    with rec.write("one") as c:
        store.write(
            c,
            rec,
            "map_facts",
            {
                "name": {
                    "en": "Sample term",
                    "ar": "الضمان الابتدائي" if matching else "مدة التنفيذ",
                },
                "file_id": f.id,
                "locator": {"page": 20},
                "value": value,
                "state": state,
            },
        )
    lead = scripted(text(reply), text(reply))  # Even an unchanged absence gets only one retry.
    engine = await started(make_engine(links(lead=lead, quick=lead)))
    await finish(engine, await engine.start_brief(project, "What is the bid security?"))
    expected = state != "blank" and matching and bool(value.strip())
    assert lead.calls == (2 if expected else 1)
    if expected:
        fix = str(lead.seen[1])
        assert "The Tender summary has" in fix and "sample.pdf, page 20" in fix
        assert "files_read" in fix and "1 بالمائة" in fix


def test_absence_matches_source_label_without_other_answered_facts(rec):
    f = files.add_file(rec, "sample.txt", b"sample", actor="engineer")
    with rec.write("one") as c:
        store.write(
            c,
            rec,
            "map_facts",
            {
                "name": {"en": "Sample field", "ar": "حقل عينة"},
                "source_label": "الضمان الابتدائي",
                "file_id": f.id,
                "locator": {"page": 20},
                "value": "1 بالمائة",
                "state": "found",
            },
        )
    [problem] = truth.tender_search_problem("Bid security: missing.", "Tender terms", True, rec=rec)
    assert "sample.txt, page 20" in problem.fix
    assert not truth.tender_search_problem(
        "Bid security is specified.\nDuration: not found.", "Tender terms", True, rec=rec
    )
