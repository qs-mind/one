"""One's tools over MCP at /mcp, with a token for each run (Plan 4, Task 4).

The core runs on uvicorn on a free 127.0.0.1 port and the `mcp` client calls it: loopback only,
no real AI."""

import httpx
import pytest
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.shared._httpx_utils import create_mcp_http_client

from qsone.app import create_app
from qsone.engine.mcp_server import RunScope
from qsone.engine.tools import REGISTRY
from tests import test_engine_tools as tools_tests
from tests.conftest import AUTH, SECRET

# The same fixtures as the tool tests.
host = tools_tests.host
ctx = tools_tests.ctx
boq_ctx = tools_tests.boq_ctx
side_tools = tools_tests.side_tools

INIT = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "sample", "version": "0"},
    },
}
HEADERS = {"Accept": "application/json, text/event-stream"}


@pytest.fixture
def core_server(data_dir, serve_app):
    """The whole core app on a real port; `core_server.gate` issues run tokens."""
    app = create_app(SECRET, data_dir=data_dir)

    class Core:
        url = serve_app(app) + "/mcp"
        gate = app.state.mcp

    return Core


@pytest.fixture
def gate(core_server):
    return core_server.gate


async def session_call(url: str, token: str, fn):
    headers = {"Authorization": f"Bearer {token}"}
    async with create_mcp_http_client(headers=headers) as http:
        async with streamable_http_client(url, http_client=http) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                return await fn(session)


async def test_mcp_needs_its_run_token(core_server, ctx):
    async with httpx.AsyncClient() as http:
        for headers in ({}, AUTH, {"Authorization": "Bearer not-a-run-token"}):
            r = await http.post(core_server.url, json=INIT, headers=HEADERS | headers)
            assert r.status_code == 401
    token = core_server.gate.issue(RunScope(ctx, ("find_items",)))
    async with httpx.AsyncClient() as http:
        r = await http.post(
            core_server.url, json=INIT, headers=HEADERS | {"Authorization": f"Bearer {token}"}
        )
    assert r.status_code == 200


async def test_mcp_lists_only_the_runs_tools(core_server, gate, ctx):
    token = gate.issue(RunScope(ctx, ("find_items", "record_number")))
    listed = await session_call(core_server.url, token, lambda s: s.list_tools())
    by_name = {t.name: t for t in listed.tools}
    assert sorted(by_name) == ["find_items", "record_number"]
    record = by_name["record_number"]
    assert record.description == REGISTRY["record_number"].description
    assert record.input_schema == REGISTRY["record_number"].args.model_json_schema()


async def test_mcp_calls_go_through_the_same_gate(core_server, gate, ctx, host, side_tools):
    host.answers["outside"] = "no"
    token = gate.issue(RunScope(ctx, ("send_sample",)))
    result = await session_call(
        core_server.url, token, lambda s: s.call_tool("send_sample", {"to": "x@sample"})
    )
    assert result.is_error and "said no" in result.content[0].text
    assert side_tools == [] and [c.kind for c in host.cards] == ["outside"]


async def test_mcp_results_are_the_same_text(core_server, gate, boq_ctx):
    token = gate.issue(RunScope(boq_ctx, ("search_records",)))
    result = await session_call(
        core_server.url, token, lambda s: s.call_tool("search_records", {"query": "عزل"})
    )
    text = result.content[0].text
    assert not result.is_error and text.startswith(f"<<data id={boq_ctx.fence}")
    assert boq_ctx.store.brief(boq_ctx.brief_id)["read_untrusted"] == 1


async def test_mcp_refusals_say_what_to_send(core_server, gate, ctx):
    token = gate.issue(RunScope(ctx, ("record_number",)))
    result = await session_call(
        core_server.url,
        token,
        lambda s: s.call_tool("record_number", {"item": "03/02", "name": "rate", "value": 1.5}),
    )
    assert result.is_error and "value" in result.content[0].text
    assert "39850.50" in result.content[0].text


async def test_mcp_refuses_a_tool_outside_the_scope(core_server, gate, ctx, side_tools):
    token = gate.issue(RunScope(ctx, ("find_items",)))
    result = await session_call(
        core_server.url, token, lambda s: s.call_tool("send_sample", {"to": "x@sample"})
    )
    assert result.is_error and side_tools == []


async def test_a_revoked_token_is_refused(core_server, gate, ctx):
    token = gate.issue(RunScope(ctx, ("find_items",)))
    await session_call(core_server.url, token, lambda s: s.list_tools())
    gate.revoke(token)
    async with httpx.AsyncClient() as http:
        r = await http.post(
            core_server.url, json=INIT, headers=HEADERS | {"Authorization": f"Bearer {token}"}
        )
    assert r.status_code == 401


async def test_each_run_has_its_own_token(core_server, gate, ctx):
    a = gate.issue(RunScope(ctx, ("find_items",)))
    b = gate.issue(RunScope(ctx, ("ledger_numbers",)))
    assert a != b and len(a) >= 32
    names = [
        [t.name for t in (await session_call(core_server.url, tok, lambda s: s.list_tools())).tools]
        for tok in (a, b)
    ]
    assert names == [["find_items"], ["ledger_numbers"]]
