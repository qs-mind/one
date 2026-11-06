"""One-shot model calls for tools (Plan 5, Task 2): a page image read by the engineer's AI, and
the connected AI's own web search. Each goes through the AI-call checks and the Spending Caps.

PydanticAI `FunctionModel`s stand in for the Native Link, and the fake `claude` for the
Subscription Link; no test calls a real AI or the web. Synthetic «عينة» data only."""

import base64
import json
from dataclasses import replace
from decimal import Decimal

import pytest
from pydantic_ai import BinaryImage
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import ModelResponse, NativeToolCallPart, NativeToolReturnPart, TextPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import RequestUsage

from qsone import copy
from qsone.engine import costs, oneshot
from qsone.engine.connectors.claude_code import ID as CLAUDE_CODE
from qsone.engine.connectors.claude_code import ClaudeCodeConnector
from qsone.engine.costs import CallRefused, CapReached, Spending
from qsone.engine.oneshot import Models, OneShotFailed
from qsone.engine.store import CostBook
from qsone.engine.types import ModelChoice
from tests.engine_fakes import (
    DEEPSEEK,
    HAIKU,
    OPUS,
    SONNET,
    FakeHost,
    fake_claude_command,
    read_fake_log,
)
from tests.fakes_tools import fake_services
from tests.test_engine_runner import FakeLink

PNG = b"\x89PNG\r\n\x1a\n" + b"page-image-sample" * 8
SUBSCRIPTION = replace(
    SONNET,
    choice=ModelChoice(CLAUDE_CODE, "sonnet"),
    name="Claude Code: sonnet",
    images=False,
    subscription=True,
)


def costs_of(general) -> list[tuple]:
    with general.read() as c:
        return c.execute(
            "SELECT run_id, role, connector, model, input_tokens, output_tokens, usd, equivalent,"
            " basis FROM ai_costs ORDER BY id"
        ).fetchall()


@pytest.fixture
def host():
    return FakeHost(brief_id="b-sample")


@pytest.fixture
def make(general, host, fake_clock, data_dir):
    """`make(roles, connectors, sheet=…)`: the Brief's models for one tool run."""

    def build(roles: dict, found: list, *, sheet=None) -> Models:
        return Models(
            sheet=tuple(sheet if sheet is not None else (OPUS, SONNET, HAIKU, DEEPSEEK)),
            roles=roles,
            connectors={c.id: c for c in found},
            spending=Spending(CostBook(general), clock=fake_clock),
            host=host,
            brief_id=host.brief_id,
            project_id="p-sample",
            run_id="r-sample",
            work=data_dir / "claude-work",
        )

    return build


def reads_the_page(seen: list, text: str = "خرسانة ٥١٩٣ م.ط - عينة"):
    def answer(messages, info):
        seen.append((messages, info))
        return ModelResponse(
            parts=[TextPart(text)], usage=RequestUsage(input_tokens=1700, output_tokens=40)
        )

    return FunctionModel(answer)


# Which model reads a page image -----------------------------------------------------------------


def test_image_model_order(make):
    claude = FakeLink("anthropic", "Claude", "anthropic")
    deepseek = FakeLink("standard:deepseek", "DeepSeek", "deepseek")
    code = ClaudeCodeConnector(None, command_prefix=["sample"])
    blind = replace(SONNET, images=False)
    roles = {"lead": OPUS.choice, "specialist": SONNET.choice}
    assert oneshot.image_model(make(roles, [claude])) == SONNET  # the specialist tier first
    sheet = (OPUS, blind, HAIKU)
    assert oneshot.image_model(make(roles, [claude], sheet=sheet)) == OPUS  # then the Lead's
    no_eyes = (replace(OPUS, images=False), blind, SUBSCRIPTION)
    found = make(roles, [claude, code], sheet=no_eyes)
    assert oneshot.image_model(found) == SUBSCRIPTION  # then the Subscription Link
    assert oneshot.image_model(make(roles, [claude], sheet=no_eyes)) is None
    gone = make({"specialist": DEEPSEEK.choice, "lead": OPUS.choice}, [claude])  # no DeepSeek link
    assert oneshot.image_model(gone) == OPUS
    assert oneshot.image_model(make(roles, [deepseek])) is None


# Reading a page on the Native Link ---------------------------------------------------------------


async def test_transcribe_sends_the_image_and_records_the_cost(make, general):
    seen: list = []
    claude = FakeLink(
        "anthropic", "Claude", "anthropic", models={SONNET.choice.model: reads_the_page(seen)}
    )
    models = make({"lead": OPUS.choice, "specialist": SONNET.choice}, [claude])
    text, model_id = await oneshot.transcribe(PNG, page=2, models=models)
    assert (text, model_id) == ("خرسانة ٥١٩٣ م.ط - عينة", SONNET.choice.model)
    [(messages, info)] = seen
    content = messages[-1].parts[-1].content
    images = [c for c in content if isinstance(c, BinaryImage)]
    assert [i.data for i in images] == [PNG] and images[0].media_type == "image/png"
    assert len(info.instructions.split()) <= 60 and "exactly" in info.instructions
    assert info.function_tools == [] and info.model_request_parameters.native_tools == []
    [row] = costs_of(general)
    assert row[:6] == ("r-sample", "specialist", "anthropic", SONNET.choice.model, 1700, 40)
    assert Decimal(row[6]) == (1700 * SONNET.price_in + 40 * SONNET.price_out) / 1_000_000


async def test_transcribe_stops_at_the_cap(make, general, host):
    costs.save_caps({"brief": "0.01"})
    seen: list = []
    claude = FakeLink(
        "anthropic", "Claude", "anthropic", models={SONNET.choice.model: reads_the_page(seen)}
    )
    models = make({"specialist": SONNET.choice}, [claude])
    CostBook(general).add(
        brief_id=host.brief_id,
        project_id="p-sample",
        run_id="r0",
        role="lead",
        choice=OPUS.choice,
        input_tokens=1,
        output_tokens=1,
        usd=Decimal("0.02"),
        equivalent=False,
        basis="sample",
        at=models.spending.clock(),
    )
    with pytest.raises(CapReached):
        await oneshot.transcribe(PNG, page=1, models=models)
    assert seen == []  # nothing was sent past the cap


async def test_transcribe_passes_the_ai_call_checks(make, monkeypatch):
    refusal = {"en": "Not allowed - sample", "ar": "مش مسموح - عينة"}
    monkeypatch.setattr(costs, "AI_CALL_CHECKS", [lambda choice: refusal])
    seen: list = []
    claude = FakeLink(
        "anthropic", "Claude", "anthropic", models={SONNET.choice.model: reads_the_page(seen)}
    )
    with pytest.raises(CallRefused):
        await oneshot.transcribe(PNG, page=1, models=make({"specialist": SONNET.choice}, [claude]))
    assert seen == []


async def test_transcribe_without_an_image_model_says_so(make):
    blind = make({"specialist": DEEPSEEK.choice}, [], sheet=(replace(DEEPSEEK, images=False),))
    with pytest.raises(OneShotFailed) as failed:
        await oneshot.transcribe(PNG, page=1, models=blind)
    assert failed.value.text == copy.OCR_NEEDS_MODEL


def test_page_reader_and_its_expected_cost(make):
    claude = FakeLink("anthropic", "Claude", "anthropic")
    models = make({"specialist": SONNET.choice}, [claude])
    reader = oneshot.page_reader(models)
    assert reader.model_id == SONNET.choice.model and not reader.subscription
    assert reader.on_device is False  # a cloud model: an On-device Project may not use it
    local = make({"specialist": SONNET.choice}, [claude], sheet=(replace(SONNET, on_device=True),))
    assert oneshot.page_reader(local).on_device is True
    expected = oneshot.PAGE_TOKENS[0] * SONNET.price_in + oneshot.PAGE_TOKENS[1] * SONNET.price_out
    assert reader.expected_cost(30) == costs.usd_text(30 * expected / 1_000_000)
    assert oneshot.ASK_ABOVE_PAGES == 20
    blind = make({"specialist": DEEPSEEK.choice}, [], sheet=(replace(DEEPSEEK, images=False),))
    assert oneshot.page_reader(blind) is None


def test_for_run_binds_the_briefs_models_but_keeps_a_given_transcriber(make):
    claude = FakeLink("anthropic", "Claude", "anthropic")
    models = make({"specialist": SONNET.choice, "quick": HAIKU.choice}, [claude])
    bound = oneshot.for_run(fake_services(), models)
    assert isinstance(bound.transcriber, oneshot.PageReader)
    assert isinstance(bound.native_search, oneshot.NativeSearch)
    given = fake_services()
    given.transcriber = "the test's own"
    assert oneshot.for_run(given, models).transcriber == "the test's own"


# Reading a page on the Subscription Link --------------------------------------------------------


async def test_subscription_transcribe_uses_an_image_block(make, general, tmp_path):
    log = tmp_path / "claude.log"
    script = [
        "init",
        {"usage": [1500, 30]},
        {"text": "خرسانة ٥١٩٣ م.ط - عينة"},
        {"result": {"cost": "0.02"}},
    ]
    code = ClaudeCodeConnector(None, command_prefix=fake_claude_command(script=script, log=log))
    no_eyes = (replace(OPUS, images=False), SUBSCRIPTION)
    models = make({"lead": OPUS.choice, "specialist": OPUS.choice}, [code], sheet=no_eyes)
    text, model_id = await oneshot.transcribe(PNG, page=3, models=models)
    assert (text, model_id) == ("خرسانة ٥١٩٣ م.ط - عينة", "sonnet")
    [run] = read_fake_log(log)
    argv = run["argv"]
    assert argv[argv.index("--tools") + 1] == "" and "--allowedTools" not in argv
    assert json.loads(argv[argv.index("--mcp-config") + 1]) == {"mcpServers": {}}
    assert "--no-session-persistence" in argv and argv[argv.index("--model") + 1] == "sonnet"
    [line] = run["stdin"]
    blocks = line["message"]["content"]
    image = next(b for b in blocks if b["type"] == "image")
    assert image["source"] == {
        "type": "base64",
        "media_type": "image/png",
        "data": base64.b64encode(PNG).decode(),
    }
    folder = models.work
    assert not folder.exists() or not any(folder.iterdir())  # nothing left on disk
    [row] = costs_of(general)
    assert row[1:4] == ("specialist", CLAUDE_CODE, "sonnet") and row[6:8] == ("0.02", 1)


async def test_subscription_that_fails_is_a_plain_failure(make, tmp_path):
    code = ClaudeCodeConnector(None, command_prefix=fake_claude_command(script=["init", "drop"]))
    models = make({"specialist": SUBSCRIPTION.choice}, [code], sheet=(SUBSCRIPTION,))
    with pytest.raises(OneShotFailed) as failed:
        await oneshot.transcribe(PNG, page=1, models=models)
    assert failed.value.text == copy.OCR_FAILED


async def test_subscription_without_no_session_persistence_is_refused(make, tmp_path):
    log = tmp_path / "claude.log"
    command = fake_claude_command(
        script=["init", "result"], log=log, drop=("--no-session-persistence",)
    )
    code = ClaudeCodeConnector(None, command_prefix=command)
    models = make({"specialist": SUBSCRIPTION.choice}, [code], sheet=(SUBSCRIPTION,))
    with pytest.raises(OneShotFailed):
        await oneshot.transcribe(PNG, page=1, models=models)
    assert not log.exists() or read_fake_log(log) == []  # Claude Code never ran


# Native web search ------------------------------------------------------------------------------

HITS = [
    {
        "type": "web_search_result",
        "title": "Rebar prices - sample",
        "url": "https://steel-sample.example/p",
        "page_age": "October 30, 2026",
        "encrypted_content": "sample",
    },
    {
        "type": "web_search_result",
        "title": "Cement - sample",
        "url": "https://cement-sample.example/",
    },
]


def searches(seen: list, hits=HITS):
    def answer(messages, info):
        seen.append((messages, info))
        return ModelResponse(
            parts=[
                NativeToolCallPart(
                    "web_search", {"query": "x"}, tool_call_id="s1", provider_name="anthropic"
                ),
                NativeToolReturnPart(
                    "web_search", hits, tool_call_id="s1", provider_name="anthropic"
                ),
                TextPart("Found two - sample"),
            ],
            usage=RequestUsage(
                input_tokens=900, output_tokens=60, details={"web_search_requests": 1}
            ),
        )

    return FunctionModel(answer)


async def test_native_search_returns_hits_from_the_tool_parts(make, general):
    seen: list = []
    claude = FakeLink(
        "anthropic", "Claude", "anthropic", models={HAIKU.choice.model: searches(seen)}
    )
    models = make(
        {"lead": OPUS.choice, "specialist": SONNET.choice, "quick": HAIKU.choice}, [claude]
    )
    hits = await oneshot.native_search("سعر حديد التسليح", country="EG", lang="ar", models=models)
    assert hits == [
        {
            "title": "Rebar prices - sample",
            "url": "https://steel-sample.example/p",
            "snippet": "",
            "page_age": "October 30, 2026",
        },
        {
            "title": "Cement - sample",
            "url": "https://cement-sample.example/",
            "snippet": "",
            "page_age": None,
        },
    ]
    [(messages, info)] = seen
    [tool] = info.model_request_parameters.native_tools
    assert tool.max_uses == 1 and tool.user_location == {"country": "EG"}
    assert messages[-1].parts[-1].content == "سعر حديد التسليح"  # only the query goes in
    tokens, fee = costs_of(general)
    assert tokens[1:4] == ("quick", "anthropic", HAIKU.choice.model)
    assert fee[4:7] == (0, 0, "0.01") and fee[8] == oneshot.SEARCH_FEE_BASIS


async def test_native_search_with_no_search_model_finds_nothing(make):
    deepseek = FakeLink("standard:deepseek", "DeepSeek", "deepseek")
    models = make({"lead": DEEPSEEK.choice, "quick": DEEPSEEK.choice}, [deepseek])
    assert oneshot.native_searcher(models) is None
    assert await oneshot.native_search("rebar", country=None, lang=None, models=models) == []


async def test_native_search_on_subscription_allows_only_websearch(make, general, tmp_path):
    log = tmp_path / "claude.log"
    answer = [
        {
            "title": "Rebar - sample",
            "url": "https://steel-sample.example/p",
            "snippet": "39850 EGP",
            "page_age": None,
        },
        {"title": "not a web link", "url": "file:///etc/passwd"},
    ]
    script = [
        "init",
        {"tool_use": {"name": "WebSearch", "input": {"query": "rebar price Cairo"}}},
        {"text": json.dumps(answer)},
        {"result": {"cost": "0.03"}},
    ]
    code = ClaudeCodeConnector(None, command_prefix=fake_claude_command(script=script, log=log))
    models = make(
        {"lead": SUBSCRIPTION.choice, "quick": SUBSCRIPTION.choice}, [code], sheet=(SUBSCRIPTION,)
    )
    searcher = oneshot.native_searcher(models)
    hits = await searcher.search("rebar price Cairo", country="EG", lang="en", count=5)
    assert hits == [answer[0]]
    [run] = read_fake_log(log)
    argv = run["argv"]
    assert argv[argv.index("--tools") + 1] == "WebSearch"
    assert argv[argv.index("--allowedTools") + 1] == "WebSearch"
    assert "WebSearch" not in argv[argv.index("--disallowedTools") + 1].split(",")
    assert json.loads(argv[argv.index("--mcp-config") + 1]) == {"mcpServers": {}}
    [line] = run["stdin"]
    assert [b["text"] for b in line["message"]["content"]] == ["rebar price Cairo"]
    [row] = costs_of(general)
    assert row[1:3] == ("quick", CLAUDE_CODE) and row[6] == "0.03"


async def test_native_search_failure_is_plain(make):
    def refused(messages, info):
        raise ModelHTTPError(503, "claude-haiku-5-5", "overloaded - sample")

    claude = FakeLink(
        "anthropic", "Claude", "anthropic", models={HAIKU.choice.model: FunctionModel(refused)}
    )
    models = make({"quick": HAIKU.choice}, [claude])
    with pytest.raises(OneShotFailed) as failed:
        await oneshot.native_search("rebar", country=None, lang=None, models=models)
    assert failed.value.text == copy.fill(copy.AI_BUSY, provider="Claude")


@pytest.mark.parametrize("role", ["lead", "checker", "specialist", "quick"])
@pytest.mark.parametrize("status", [404, 400, 403, 429, 503])
async def test_retired_quick_retries_only_unbilled_404(make, status, role):
    from qsone.engine import connectors

    seen = []

    def gone(messages, info):
        seen.append("gone")
        raise ModelHTTPError(status, HAIKU.choice.model, "no longer available - sample")

    def answer(messages, info):
        seen.append("next")
        return ModelResponse([TextPart("sample result")])

    link = FakeLink(
        "anthropic",
        "Claude",
        "anthropic",
        models={
            HAIKU.choice.model: FunctionModel(gone),
            SONNET.choice.model: FunctionModel(answer),
        },
    )
    models = make({role: HAIKU.choice}, [link], sheet=[HAIKU, SONNET])
    agent = oneshot.Agent(oneshot._costed(models, HAIKU, role))
    if status == 404:
        result = await oneshot._once(models, HAIKU, role, agent, "sample")
        assert result.output == "sample result"
        assert seen == ["gone", "next"]
        assert connectors.refused(HAIKU.choice)
    else:
        with pytest.raises(OneShotFailed):
            await oneshot._once(models, HAIKU, role, agent, "sample")
        assert seen == ["gone"]
        assert not connectors.refused(HAIKU.choice)


async def test_map_recomputes_quick_for_next_file_and_records_only_success(make, general):
    from pydantic import BaseModel
    from pydantic_ai.messages import ToolCallPart

    from qsone import settings
    from qsone.engine import roles

    class Result(BaseModel):
        title: str

    seen = []
    cheap = replace(HAIKU, choice=ModelChoice("standard:sample", "sample-cheapest"))
    next_card = replace(SONNET, choice=ModelChoice("standard:sample", "sample-next"))
    typed = replace(OPUS, choice=ModelChoice("standard:sample", "sample-typed"))
    settings.save_ai(
        "standard",
        [
            {
                "id": "sample",
                "name": "Sample",
                "provider": "sample",
                "base_url": "https://sample.invalid",
                "model": "sample-typed",
            }
        ],
    )

    async def gone(messages, info):
        seen.append("gone")
        raise ModelHTTPError(404, cheap.choice.model, "not supported for this account - sample")

    async def answer(messages, info):
        seen.append("next")
        return ModelResponse([ToolCallPart(info.output_tools[0].name, {"title": "sample"})])

    link = FakeLink(
        "standard:sample",
        "Sample",
        "sample",
        models={
            cheap.choice.model: FunctionModel(gone),
            next_card.choice.model: FunctionModel(answer),
        },
    )
    sheet = [cheap, next_card, typed]
    models = make(roles.defaults(sheet), [link], sheet=sheet)
    assert oneshot.map_model(models) == cheap
    for _ in range(2):
        assert (
            await oneshot.map_text(models, "sample file", Result, "sample mapping")
        ).title == "sample"
    assert seen == ["gone", "next", "next"]
    assert oneshot.map_model(models) == next_card
    assert [row[3] for row in costs_of(general)] == [next_card.choice.model] * 2


async def test_retirement_retries_once_and_marks_both_failed_models(make):
    from qsone.engine import connectors

    seen = []

    async def gone(messages, info):
        seen.append("gone")
        raise ModelHTTPError(404, "sample", "model not found - sample")

    link = FakeLink(
        "anthropic",
        "Claude",
        "anthropic",
        models={
            HAIKU.choice.model: FunctionModel(gone),
            SONNET.choice.model: FunctionModel(gone),
        },
    )
    models = make({"quick": HAIKU.choice}, [link], sheet=[HAIKU, SONNET])
    agent = oneshot.Agent(oneshot._costed(models, HAIKU, "quick"))
    with pytest.raises(OneShotFailed):
        await oneshot._once(models, HAIKU, "quick", agent, "sample")
    assert seen == ["gone", "gone"]
    assert connectors.refused(HAIKU.choice) and connectors.refused(SONNET.choice)
    assert oneshot.map_model(models) is None


@pytest.mark.anyio
@pytest.mark.parametrize("always_invalid", [False, True])
async def test_structured_one_validation_retry_is_costed(make, general, always_invalid):
    from pydantic import BaseModel
    from pydantic_ai.messages import ToolCallPart

    class Output(BaseModel):
        value: int

    seen = []

    async def answer(messages, info):
        seen.append(messages)
        args = {"value": "invalid"} if always_invalid or len(seen) == 1 else {"value": 1}
        return ModelResponse(
            parts=[ToolCallPart(info.output_tools[0].name, args)],
            usage=RequestUsage(input_tokens=100, output_tokens=50),
        )

    link = FakeLink(
        "anthropic", "Sample AI", "anthropic", models={HAIKU.choice.model: FunctionModel(answer)}
    )
    costs.save_caps({"budget_above": "100"})
    models = make({"quick": HAIKU.choice}, [link], sheet=(HAIKU,))
    if always_invalid:
        with pytest.raises(OneShotFailed) as error:
            await oneshot.map_text(models, "Sample", Output, "Return sample")
        assert error.value.text == copy.MAP_AI_INVALID_OUTPUT
    else:
        assert (await oneshot.map_text(models, "Sample", Output, "Return sample")).value == 1
    assert len(seen) == 2
    assert sum(r[4] for r in costs_of(general)) == 200
    assert sum(r[5] for r in costs_of(general)) == 100
