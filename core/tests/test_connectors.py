"""Connectors (Plan 5, Task 12): any MCP server the engineer adds, through Plan 4's `call`, with
the engineer's yes for anything that acts outside One, every call logged so it can be cited, and
the engineer's token only in the key store.

Each test starts `tests/fake_mcp_server.py` over stdio; no test starts a real third-party
Connector, reaches the internet or calls an AI model."""

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from qsone import copy, keys, settings
from qsone.app import create_app
from qsone.connectors import hub as hub_mod
from qsone.connectors.hub import ConnectorConfig, ConnectorHub
from qsone.engine.tools import REGISTRY, Denied, ModelRetry, call
from qsone.records import files
from qsone.tools import connectors as connector_tools  # noqa: F401 - registers the tools
from qsone.tools import web as web_tools  # noqa: F401 - registers web_search
from tests.conftest import AUTH, SECRET
from tests.engine_fakes import FakeHost
from tests.fakes_tools import fake_services, tool_ctx

pytestmark = pytest.mark.anyio

FAKE = Path(__file__).parent / "fake_mcp_server.py"
NAME = "mail-sample"


def mail(tmp_path, *, more: bool = False, name: str = NAME, **kw) -> ConnectorConfig:
    """The fake mail server as the engineer would add it; `--log` keeps what it sent and `--pid`
    its process id."""
    command = [sys.executable, "-I", str(FAKE), "--log", str(tmp_path / f"{name}-sent.jsonl")]
    command += ["--pid", str(tmp_path / f"{name}.pid")] + (["--more"] if more else [])
    return ConnectorConfig(name=name, transport="stdio", command=tuple(command), **kw)


def sent(tmp_path, name: str = NAME) -> list[dict]:
    log = tmp_path / f"{name}-sent.jsonl"
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


def answer(choice: str = "yes", *, read: bool = False, search: str = "none") -> str:
    """What the connector card settles with (`answer_value`'s JSON text)."""
    answers = {"read_without_asking": "yes" if read else "no", "search": search}
    return json.dumps({"choice": choice, "answers": answers, "rows_ok": []})


async def install(hub, tmp_path, *, read=False, more=False, search="none", name=NAME):
    host = FakeHost(answers={"connector": answer(read=read, search=search)})
    assert await hub.propose(mail(tmp_path, more=more, name=name), None, ask=host.ask)
    return host.cards[0]


@pytest.fixture
async def hub():
    found = ConnectorHub()
    found.start()
    yield found
    await found.close()


def ctx_for(rec, hub, general, *, answers=None, untrusted=False, on_device=False):
    services = fake_services(connectors=hub, engineer=lambda: general)
    return tool_ctx(
        rec, answers=answers or {}, untrusted=untrusted, on_device=on_device, services=services
    )


def calls_of(rec) -> list[dict]:
    with rec.read() as c:
        rows = c.execute(
            "SELECT id, connector, tool, args, ok, result_sha256, file_ids, brief_id"
            " FROM connector_calls ORDER BY rowid"
        ).fetchall()
    keys_ = ("id", "connector", "tool", "args", "ok", "result_sha256", "file_ids", "brief_id")
    found = [dict(zip(keys_, r, strict=True)) for r in rows]
    for row in found:
        row["args"], row["file_ids"] = json.loads(row["args"]), json.loads(row["file_ids"])
    return found


def alive(pid: int) -> bool:
    if sys.platform == "win32":
        out = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True
        ).stdout
        return str(pid) in out
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


# Adding a Connector ---------------------------------------------------------------------------


async def test_adding_shows_what_it_can_do_and_saves_on_yes(hub, tmp_path):
    card = await install(hub, tmp_path, read=True)
    assert card.kind == "connector" and card.options == ("yes", "no")
    assert NAME in card.title["en"] and NAME in card.title["ar"]
    assert str(FAKE) in card.detail["en"]  # what it runs
    tools = {t["name"]: t for t in card.payload["tools"]}
    assert sorted(tools) == ["attach", "read_inbox", "send_email"]
    assert tools["read_inbox"]["read_only"] is True and tools["send_email"]["read_only"] is False
    assert tools["read_inbox"]["purpose"] == "Read the inbox - sample."
    assert [q["id"] for q in card.payload["questions"]] == ["read_without_asking", "search"]
    saved = hub.config(NAME)
    assert saved.read_without_asking and saved.enabled and saved.search_tool is None
    assert {t["name"] for t in saved.tools} == {"attach", "read_inbox", "send_email"}
    assert settings.load()["connectors"][0]["name"] == NAME


async def test_refused_install_saves_nothing(hub, tmp_path):
    host = FakeHost(answers={"connector": answer("no", read=True)})
    assert not await hub.propose(mail(tmp_path), "t-sample", ask=host.ask)
    assert hub.config(NAME) is None and "connectors" not in settings.load()
    assert keys.get_key(f"connector:{NAME}") is None


async def test_a_name_is_added_once(hub, tmp_path):
    await install(hub, tmp_path)
    with pytest.raises(hub_mod.ConnectorError) as taken:
        await hub.propose(mail(tmp_path), None, ask=FakeHost().ask)
    assert taken.value.text == copy.CONNECTOR_NAME_TAKEN


@pytest.mark.parametrize(
    "fields",
    [
        {"name": "X", "transport": "stdio", "command": ("python",)},
        {"name": "ok-name", "transport": "stdio", "command": ()},
        {"name": "ok-name", "transport": "http", "url": "ftp://sample.example/mcp"},
    ],
)
def test_a_bad_config_is_refused(fields):
    with pytest.raises(hub_mod.ConnectorError) as bad:
        ConnectorConfig(**fields)
    assert bad.value.text == copy.CONNECTOR_BAD


# Calls and the gate ---------------------------------------------------------------------------


async def test_send_always_asks_with_the_exact_arguments(rec, general, hub, tmp_path):
    await install(hub, tmp_path, read=True)  # reading tools without asking: sending still asks
    ctx = ctx_for(rec, hub, general, answers={"outside": "no"})
    args = {"to": "supplier@sample.example", "body": "طلب تسعير"}
    with pytest.raises(Denied):
        await call("connector_call", {"connector": NAME, "tool": "send_email", "args": args}, ctx)
    card = ctx.host.cards[0]
    assert card.kind == "outside" and "supplier@sample.example" in card.detail["en"]
    assert "طلب تسعير" in card.detail["ar"] and sent(tmp_path) == [] and calls_of(rec) == []


async def test_a_yes_sends_it_and_the_call_can_be_cited(rec, general, hub, tmp_path):
    await install(hub, tmp_path)
    never = json.dumps({"choice": "sent", "answers": {"keep": "never"}, "rows_ok": []})
    ctx = ctx_for(rec, hub, general, answers={"outside": "yes", "question": never})
    args = {"to": "supplier@sample.example", "body": "طلب تسعير"}
    out = await call("connector_call", {"connector": NAME, "tool": "send_email", "args": args}, ctx)
    assert sent(tmp_path) == [{"tool": "send_email"} | args]  # the server got it all
    row = calls_of(rec)[0]
    assert (row["connector"], row["tool"], row["ok"], row["brief_id"]) == (
        NAME,
        "send_email",
        1,
        ctx.brief_id,
    )
    assert "supplier@sample.example" not in json.dumps(row["args"])  # "never keep emails"
    assert row["args"]["body"] == "طلب تسعير" and row["result_sha256"]
    assert f"connector:{NAME}/{row['id']}" in out and "sent to supplier@sample.example" in out
    cited = await call(
        "add_source", {"kind": "connector", "call_id": row["id"], "title": "made up"}, ctx
    )
    assert "source_id" in cited


async def test_read_only_tool_is_online_only_when_allowed(rec, general, hub, tmp_path):
    await install(hub, tmp_path, read=True)
    assert hub.risk(NAME, "read_inbox") == "online" and hub.risk(NAME, "send_email") == "outside"
    ctx = ctx_for(rec, hub, general)
    await call("connector_call", {"connector": NAME, "tool": "read_inbox"}, ctx)
    assert ctx.host.cards == []  # nothing untrusted read before it: no card
    again = ctx_for(rec, hub, general, untrusted=True, answers={"online": "no"})
    with pytest.raises(Denied):
        await call("connector_call", {"connector": NAME, "tool": "read_inbox"}, again)
    assert again.host.cards[0].kind == "online"

    await hub.remove(NAME)
    await install(hub, tmp_path, read=False)
    assert hub.risk(NAME, "read_inbox") == "outside"
    asked = ctx_for(rec, hub, general, answers={"outside": "no"})
    with pytest.raises(Denied):
        await call("connector_call", {"connector": NAME, "tool": "read_inbox"}, asked)
    assert asked.host.cards[0].kind == "outside"


async def test_allow_for_this_brief_covers_that_connectors_tool_only(rec, general, hub, tmp_path):
    await install(hub, tmp_path, read=True)
    await install(hub, tmp_path, read=True, name="drive-sample")
    ctx = ctx_for(rec, hub, general, untrusted=True, answers={"online": "brief"})
    inbox = {"connector": NAME, "tool": "read_inbox"}
    await call("connector_call", inbox, ctx)
    await call("connector_call", inbox, ctx)
    assert len(ctx.host.cards) == 1  # allowed for this Brief: the same tool asks once
    await call("connector_call", {"connector": "drive-sample", "tool": "read_inbox"}, ctx)
    assert len(ctx.host.cards) == 2  # another Connector's reading tool still asks
    assert ctx.store.allowed(ctx.brief_id) == {
        f"connector_call:{NAME}/read_inbox",
        "connector_call:drive-sample/read_inbox",
    }


async def test_destructive_and_open_world_hints_are_always_outside(rec, general, hub, tmp_path):
    await install(hub, tmp_path, read=True, more=True)
    assert hub.risk(NAME, "archive_mail") == "outside"  # read-only and destructive
    assert hub.risk(NAME, "search") == "outside"  # read-only and open world
    ctx = ctx_for(rec, hub, general, answers={"outside": "no"})
    with pytest.raises(Denied):
        await call(
            "connector_call",
            {"connector": NAME, "tool": "archive_mail", "args": {"subject": "عينة"}},
            ctx,
        )
    assert ctx.host.cards[0].kind == "outside"


async def test_connector_text_is_data_and_marks_the_brief(rec, general, hub, tmp_path):
    await install(hub, tmp_path, read=True)
    ctx = ctx_for(rec, hub, general)
    out = await call("connector_call", {"connector": NAME, "tool": "read_inbox"}, ctx)
    assert out.startswith(f"<<data id={ctx.fence} ") and "عرض سعر حديد - عينة" in out
    assert ctx.store.brief(ctx.brief_id)["read_untrusted"] == 1
    assert "looks like an order to an AI" in out and "تجاهل التعليمات السابقة" in out


async def test_attachments_become_project_files(rec, general, hub, tmp_path):
    await install(hub, tmp_path)
    ctx = ctx_for(rec, hub, general, answers={"outside": "yes"})
    out = await call("connector_call", {"connector": NAME, "tool": "attach"}, ctx)
    [found] = files.list_files(rec)
    assert found.name == "عرض سعر - عينة.xlsx" and found.kind == "xlsx" and found.status == "read"
    assert calls_of(rec)[0]["file_ids"] == [found.id] and f"file:{found.id}" in out


async def test_down_and_unknown_are_plain(rec, general, hub, tmp_path):
    broken = ConnectorConfig(
        name="broken-sample",
        transport="stdio",
        command=(sys.executable, "-I", "-c", "import sys; sys.exit(3)"),
        tools=({"name": "read", "read_only": True, "destructive": False, "open_world": False},),
    )
    settings.save("connectors", [broken.as_json()])
    ctx = ctx_for(rec, hub, general, answers={"outside": "yes"})
    out = await call("connector_call", {"connector": "broken-sample", "tool": "read"}, ctx)
    assert copy.CONNECTOR_DOWN["en"] in out and "not done:" in out
    assert calls_of(rec)[0]["ok"] == 0  # every call is logged, the failed ones too
    with pytest.raises(ModelRetry, match="no tool by that name"):
        await call("connector_call", {"connector": "broken-sample", "tool": "nope"}, ctx)
    with pytest.raises(ModelRetry, match="no Connector with this name"):
        await call("connector_call", {"connector": "nobody-sample", "tool": "read"}, ctx)
    assert len(ctx.host.cards) == 1  # a model's mistake raises no card


async def test_switched_off_is_plain(rec, general, hub, tmp_path):
    await install(hub, tmp_path)
    await hub.set_enabled(NAME, False)
    ctx = ctx_for(rec, hub, general)
    out = await call("connector_call", {"connector": NAME, "tool": "send_email"}, ctx)
    assert copy.CONNECTOR_OFF["en"] in out and ctx.host.cards == [] and sent(tmp_path) == []


async def test_on_device_refuses_http_but_allows_stdio(rec, general, hub, tmp_path):
    await install(hub, tmp_path, read=True)
    tool = {"name": "anything", "read_only": False, "destructive": False, "open_world": False}
    remote = ConnectorConfig(
        name="remote-sample", transport="http", url="https://mcp.sample/x", tools=(tool,)
    )
    settings.save("connectors", [*settings.load()["connectors"], remote.as_json()])
    answers = {"outside": "yes", "online": "yes"}
    ctx = ctx_for(rec, hub, general, on_device=True, answers=answers)
    out = await call("connector_call", {"connector": "remote-sample", "tool": "anything"}, ctx)
    assert copy.ON_DEVICE_NO_ONLINE["en"] in out and calls_of(rec) == []
    inbox = await call("connector_call", {"connector": NAME, "tool": "read_inbox"}, ctx)
    assert "عرض سعر حديد - عينة" in inbox


async def test_connector_tools_lists_and_describes(rec, general, hub, tmp_path):
    await install(hub, tmp_path, read=True)
    ctx = ctx_for(rec, hub, general)
    listed = await call("connector_tools", {}, ctx)
    assert NAME in listed and "3 tools" in listed
    tools = await call("connector_tools", {"connector": NAME}, ctx)
    assert "read_inbox" in tools and "asks every time" in tools and "to (string" in tools
    assert tools.startswith(f"<<data id={ctx.fence} ")  # the server wrote these words


async def test_a_search_connector_serves_web_search(rec, general, hub, tmp_path):
    await install(hub, tmp_path, more=True, search="search")
    assert hub.config(NAME).search_tool == "search"
    ctx = ctx_for(rec, hub, general)
    out = await call("web_search", {"query": "سعر حديد التسليح"}, ctx)
    assert "https://steel-sample.example/p" in out and "dated 2026-10-30" in out
    with rec.read() as c:
        provider = c.execute("SELECT provider FROM web_log").fetchone()[0]
    assert provider == f"connector:{NAME}"


async def test_stdio_server_stops_with_the_core(rec, general, tmp_path):
    hub = ConnectorHub()
    hub.start()
    await install(hub, tmp_path, read=True)
    ctx = ctx_for(rec, hub, general)
    await call("connector_call", {"connector": NAME, "tool": "read_inbox"}, ctx)
    pid = int((tmp_path / f"{NAME}.pid").read_text())
    assert alive(pid)
    await hub.close()
    deadline = time.monotonic() + 10
    while alive(pid) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not alive(pid) and hub_mod.active() is None


async def test_a_server_that_died_is_down_once_then_started_again(rec, general, hub, tmp_path):
    await install(hub, tmp_path, read=True)
    ctx = ctx_for(rec, hub, general, answers={"online": "yes"})
    await call("connector_call", {"connector": NAME, "tool": "read_inbox"}, ctx)
    os.kill(int((tmp_path / f"{NAME}.pid").read_text()), signal.SIGTERM)
    time.sleep(0.5)
    out = await call("connector_call", {"connector": NAME, "tool": "read_inbox"}, ctx)
    if "not done:" not in out:  # the kill may land after the call; the next one is down then
        out = await call("connector_call", {"connector": NAME, "tool": "read_inbox"}, ctx)
    assert copy.CONNECTOR_DOWN["en"] in out
    again = await call("connector_call", {"connector": NAME, "tool": "read_inbox"}, ctx)
    assert "عرض سعر حديد - عينة" in again  # a new server was started


async def test_http_connector_gets_its_token_as_bearer(rec, general, hub, serve_app):
    from tests import fake_mcp_server

    seen: list[str | None] = []
    inner = fake_mcp_server.server.streamable_http_app()

    async def app(scope, receive, send):  # records the Authorization header of each request
        if scope["type"] == "http":
            headers = dict(scope["headers"])
            seen.append(headers.get(b"authorization", b"").decode() or None)
        await inner(scope, receive, send)

    url = serve_app(app) + "/mcp"
    remote = ConnectorConfig(name="remote-sample", transport="http", url=url)
    host = FakeHost(answers={"connector": answer(read=True)})
    assert await hub.propose(remote, "tok-sample-123", ask=host.ask)
    assert hub.config("remote-sample").transport == "http"
    ctx = ctx_for(rec, hub, general)
    out = await call("connector_call", {"connector": "remote-sample", "tool": "read_inbox"}, ctx)
    assert "عرض سعر حديد - عينة" in out and seen and set(seen) == {"Bearer tok-sample-123"}
    await hub.close()  # before the server stops: it waits for open streams


def test_tools_are_registered_with_their_risks():
    assert REGISTRY["connector_tools"].risk == "read"
    assert REGISTRY["connector_call"].risk_for is not None
    assert REGISTRY["connector_call"].untrusted and REGISTRY["connector_tools"].untrusted
    assert "checker" not in REGISTRY["connector_call"].roles
    for name in ("connector_tools", "connector_call"):
        doc = REGISTRY[name].description
        assert len(doc.split()) <= 120 and "Example:" in doc.splitlines()[-2]


# The Settings screen's routes ------------------------------------------------------------------


@pytest.fixture
def client(data_dir):
    with TestClient(create_app(SECRET, data_dir=data_dir), headers=AUTH) as c:
        yield c


def body(tmp_path, **more) -> dict:
    command = [sys.executable, "-I", str(FAKE), "--log", str(tmp_path / f"{NAME}-sent.jsonl")]
    return {"name": NAME, "transport": "stdio", "command": command} | more


def test_tokens_live_only_in_the_key_store(client, memory_keyring, data_dir, tmp_path):
    r = client.post("/connectors", json=body(tmp_path, token="tok-sample-123", token_env="T"))
    assert r.status_code == 200
    card = r.json()["card"]
    assert card["kind"] == "connector" and len(card["payload"]["tools"]) == 3
    done = client.post(
        f"/connectors/cards/{card['id']}",
        json={"choice": "yes", "answers": {"read_without_asking": "yes", "search": "none"}},
    )
    assert done.status_code == 200 and done.json()["connector"]["name"] == NAME
    assert "tok-sample-123" not in (data_dir / "settings.json").read_text(encoding="utf-8")
    assert memory_keyring.store[(keys.SERVICE, f"connector:{NAME}")] == "tok-sample-123"
    listed = client.get("/connectors").json()["connectors"]
    assert listed == [
        {
            "name": NAME,
            "transport": "stdio",
            "runs": listed[0]["runs"],
            "enabled": True,
            "tools": 3,
            "read_without_asking": True,
            "search_tool": None,
            "token": True,
        }
    ]
    assert "tok-sample-123" not in json.dumps(listed)
    assert client.delete(f"/connectors/{NAME}").status_code == 204
    assert client.get("/connectors").json() == {"connectors": []}
    assert (keys.SERVICE, f"connector:{NAME}") not in memory_keyring.store


def test_refusing_the_card_saves_nothing(client, tmp_path):
    card = client.post("/connectors", json=body(tmp_path, token="tok-sample")).json()["card"]
    bad = client.post(f"/connectors/cards/{card['id']}", json={"choice": "yes", "answers": {}})
    assert bad.status_code == 422 and bad.json()["error"] == copy.CARD_BAD_ANSWER
    r = client.post(f"/connectors/cards/{card['id']}", json={"choice": "no"})
    assert r.status_code == 200 and r.json() == {"connector": None}
    assert client.get("/connectors").json() == {"connectors": []}
    gone = client.post(f"/connectors/cards/{card['id']}", json={"choice": "yes"})
    assert gone.status_code == 404 and gone.json()["error"] == copy.CONNECTOR_CARD_GONE


def test_routes_refuse_plainly(client, tmp_path):
    bad = client.post("/connectors", json={"name": "X", "transport": "stdio", "command": ["x"]})
    assert bad.status_code == 422 and bad.json()["error"] == copy.CONNECTOR_BAD
    down = client.post(
        "/connectors", json=body(tmp_path) | {"command": [sys.executable, "-I", "-c", "pass"]}
    )
    assert down.status_code == 502 and down.json()["error"] == copy.CONNECTOR_DOWN
    assert client.delete("/connectors/nobody-sample").status_code == 404
    off = client.put("/connectors/nobody-sample/enabled", json={"enabled": False})
    assert off.status_code == 404 and off.json()["error"] == copy.CONNECTOR_NOT_FOUND


def test_switching_a_connector_off_and_on(client, tmp_path):
    card = client.post("/connectors", json=body(tmp_path)).json()["card"]
    client.post(
        f"/connectors/cards/{card['id']}",
        json={"choice": "yes", "answers": {"read_without_asking": "no", "search": "none"}},
    )
    r = client.put(f"/connectors/{NAME}/enabled", json={"enabled": False})
    assert r.status_code == 200 and r.json()["connector"]["enabled"] is False
    assert client.get("/connectors").json()["connectors"][0]["enabled"] is False
