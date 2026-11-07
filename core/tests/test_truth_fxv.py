"""Full read evidence survives request compaction and resuming a saved checkpoint."""

# ruff: noqa: F811

from dataclasses import replace

import pytest
from pydantic import BaseModel
from pydantic_ai import Agent

from qsone.engine import agents, truth
from qsone.engine.runner import _Brief, _dump, _load
from qsone.engine.tools import Tool, toolset
from tests.engine_fakes import FakeHost, call, scripted, text
from tests.team_samples import lead_ctx
from tests.test_engine_runner import (  # noqa: F401
    make_engine,
    no_budget_card,
    project,
    registry,
)


@pytest.mark.parametrize("resume", [False, True])
async def test_large_reads_stay_whole_in_saved_brief(rec, monkeypatch, resume):
    from types import SimpleNamespace

    import qsone.tools  # noqa: F401
    from qsone.engine.tools import REGISTRY

    results = [
        f'file_id: sample | file: sample.pdf\n{{"page": {page}}}\n'
        + f"Sample clause for page {page}. " * 150
        for page in range(1, 7)
    ]

    results[0] += "\nSample bid validity: 90 days.\n"

    class Args(BaseModel):
        page: int

    async def read(ctx, args):
        return results[args.page - 1]

    # Exercise the production toolset and agent builder, with synthetic tool results.
    monkeypatch.setitem(
        REGISTRY,
        "files_read",
        Tool(
            "files_read",
            "Read a sample page",
            Args,
            "read",
            read,
            lambda _: {"en": "Read sample", "ar": "قراءة عينة"},
            self_paged=True,
        ),
    )
    ctx = lead_ctx(rec, FakeHost())
    spec = replace(agents.lead_spec(), tools=("files_read",))
    store = ctx.store
    run_id = ctx.run_id
    host = SimpleNamespace(store=store, cancel_mode=None, brief_id=ctx.brief_id)
    reply = "Sample bid validity: 90 days. Source: sample.pdf, page 1."
    lead = scripted(*(call("files_read", {"page": p}) for p in range(1, 7)), text(reply))
    agent = agents.build_agent(spec, lead, toolset(("files_read",), ctx))
    checkpoint = None
    async with agent.iter("Read sample clauses") as run:
        async for node in run:
            _Brief._save(host, run_id, run.all_messages())
            assert all(
                "[earlier " not in body
                for _, body in agents.tool_returns(store.run(run_id)["history"])
            )
            if resume and Agent.is_model_request_node(node) and lead.calls == 6:
                checkpoint = store.run(run_id)["history"]
                break  # Simulate losing the agent before the final model request.
    if not resume:
        assert run.result.output == reply
    if resume:
        assert checkpoint is not None
        lead = scripted(text(reply))
        agent = agents.build_agent(spec, lead, toolset(("files_read",), ctx))
        result = await agent.run(message_history=_load(checkpoint))
        _Brief._save(host, run_id, result.all_messages())
        assert lead.calls == 1
        assert result.output == reply
    saved = store.run(run_id)["history"]
    full = [body for name, body in agents.tool_returns(saved) if name == "files_read"]
    assert full == results
    assert not truth.unread_citations(reply, _Brief._read_returns(host))
    sent = [
        body for name, body in agents.tool_returns(_dump(lead.seen[-1])) if name == "files_read"
    ]
    assert any("[earlier files_read result" in body for body in sent)
    assert sum(map(len, sent)) < sum(map(len, full)) * 0.6


async def test_stream_trims_request_without_changing_checkpoint():
    from pydantic_ai.messages import ModelRequest, ModelResponse, ToolCallPart, ToolReturnPart
    from pydantic_ai.models import ModelRequestParameters

    messages = []
    for page in range(6):
        messages += [
            ModelResponse(
                parts=[ToolCallPart("files_read", {"page": page}, tool_call_id=str(page))]
            ),
            ModelRequest(
                parts=[ToolReturnPart("files_read", "sample " * 400, tool_call_id=str(page))]
            ),
        ]
    saved = _dump(messages)
    model = scripted(text("Sample reply"))
    async with agents.RequestHistory(model).request_stream(
        messages, None, ModelRequestParameters()
    ) as stream:
        async for _ in stream:
            pass
    assert _dump(messages) == saved
    assert "[earlier files_read result" in str(model.seen[-1])
    assert agents._results(model.seen[-1]) <= agents.RESULTS_TOKENS


async def test_engine_crash_after_trimmed_request_resumes_full_reads(
    make_engine, project, registry, monkeypatch
):
    import asyncio

    import qsone.tools  # noqa: F401
    from qsone.engine.tools import REGISTRY
    from qsone.records import files
    from tests.samples import sample_pdf
    from tests.test_engine_runner import finish, links, started, store_of

    file = files.add_file(
        registry.get(project),
        "sample.pdf",
        sample_pdf([["Sample bid validity: 90 days."]] * 6),
        actor="engineer",
    )

    returned = [
        f'file_id: {file.id} | file: sample.pdf\n{{"page": {page}}}\n'
        + "Sample tender clause. " * 200
        for page in range(1, 7)
    ]
    returned[0] += "\nSample bid validity: 90 days.\n"

    async def read(ctx, args):
        return returned[int(args.pages) - 1]

    monkeypatch.setitem(REGISTRY, "files_read", replace(REGISTRY["files_read"], run=read))
    entered = asyncio.Event()

    async def interrupted(messages, info):
        entered.set()
        await asyncio.Event().wait()

    lead = scripted(
        *(call("files_read", {"file_id": file.id, "pages": str(p)}) for p in range(1, 7)),
        interrupted,
    )
    first = await started(make_engine(links(lead=lead)))
    brief = await first.start_brief(project, "Read the sample tender clauses.")
    await asyncio.wait_for(entered.wait(), 10)
    await first.crash()
    saved = store_of(first, project).runs(brief)[0]["history"]
    full = [body for _, body in agents.tool_returns(saved)]
    # The in-flight sixth request has not checkpointed its tool result yet.
    assert len(full) == 5
    assert all(expected in body for expected, body in zip(returned[:5], full, strict=True))
    assert "[earlier files_read result" in str(lead.seen[-1])

    reply = "Sample bid validity: 90 days. Source: sample.pdf, page 1."
    continued = scripted(text(reply))
    second = await started(make_engine(links(lead=continued)))
    await second.continue_brief(brief)
    await asyncio.wait_for(finish(second, brief), 10)
    assert continued.calls == 1, str(continued.seen[-1])[-4500:]
    after = [
        body for _, body in agents.tool_returns(store_of(second, project).runs(brief)[0]["history"])
    ]
    assert after == full
    assert await second.result(brief) == reply
    assert not truth.unread_citations(reply, [("files_read", body) for body in after])
