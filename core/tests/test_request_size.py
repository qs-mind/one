"""What a Brief sends the model, per request, by part (instructions, tool schemas, the chat's
earlier Briefs, the engineer's words, the model's own words and calls, tool results), against
ONE's targets: a typical request under 12,000 tokens, a whole Q&A Brief under 60,000.

The provider is a fake that speaks as Google's OpenAI-compatible endpoint does
(`tests/fake_openai.py`), behind a real Standard Link; the Lead is scripted. The Brief reads the
real Brissa tender (KFAED Brissa dam, Lebanon) and the Lahun priced BOQ when they are on this
computer (`docs/test-files`, the private docs repo), else small synthetic files of the same
kind. Tokens are ONE's own estimate (`engine.request_size`)."""

import json
import os
import re
from decimal import Decimal
from pathlib import Path

import pytest

from qsone.engine import costs
from qsone.engine.connectors.standard import StandardLink
from qsone.engine.runner import Engine
from qsone.projects import Projects
from qsone.records import files
from tests.fake_openai import FakeProvider, wire_parts

pytestmark = pytest.mark.anyio

STEP_TARGET = 12_000
BRIEF_TARGET = 60_000
BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"

BRISSA = "gulf-regional/kfaed-brissa-dam-lebanon"
LAHUN = "egypt/lahun-medical-center/boq-priced.xlsx"


def _real_files() -> Path | None:
    """`QSONE_TEST_FILES`, else the private docs repo's `docs/test-files` in the checkout (or
    above a worktree of it); None when neither is on this computer."""
    found = [Path(os.environ["QSONE_TEST_FILES"])] if "QSONE_TEST_FILES" in os.environ else []
    found += [p / "docs" / "test-files" for p in Path(__file__).resolve().parents]
    for root in found:
        if (root / BRISSA).is_dir() and (root / LAHUN).is_file():
            return root
    return None


@pytest.fixture
def registry(data_dir):
    found = Projects(data_dir)
    yield found
    found.close_all()


@pytest.fixture(autouse=True)
def no_budget_card():
    costs.save_caps({"budget_above": "100"})


_FILE = re.compile(r"file:([0-9a-f]{32}) \| ([^|]+?) \|")


def _last_tool(body: dict) -> str:
    for m in reversed(body["messages"]):
        if m["role"] == "tool":
            return str(m["content"])
    return ""


def _users(body: dict) -> int:
    return sum(1 for m in body["messages"] if m["role"] == "user")


def qa_script(question_words: str):
    """A Q&A Brief as a careful Lead does it: list the files, search, read the page of the best
    hit, then answer citing it."""

    def step(body: dict):
        tools_done = [m for m in body["messages"][_last_user(body) :] if m["role"] == "tool"]
        n = len(tools_done)
        if n == 0:
            return "calls", [("files_list", {})]
        if n == 1:
            return "calls", [("search_records", {"query": question_words, "k": 5})]
        if n == 2:
            hits = json.loads(_unfenced(_last_tool(body)))["hits"]
            hit = next((h for h in hits if "page" in h["locator"]), hits[0])
            args = {"file_id": hit["file_id"]}
            if "page" in hit["locator"]:
                args["pages"] = str(hit["locator"]["page"])
            return "calls", [("files_read", args)]
        return "text", (
            "The bid security is stated in the bidding conditions; the page is cited above. " * 6
        )

    return step


def _last_user(body: dict) -> int:
    return max(i for i, m in enumerate(body["messages"]) if m["role"] == "user")


def _unfenced(text: str) -> str:
    """A fenced data result's inner text (`data_text.as_data`)."""
    start, end = text.find("{"), text.rfind("}")
    return text[start : end + 1]


async def _engine(registry, data_dir, provider, fake_clock, fake_sleep):
    link = StandardLink("gemini", "Gemini", BASE_URL, "google", http_client=provider.client())
    engine = Engine(
        projects=registry,
        data_dir=data_dir,
        connectors=lambda: [link],
        clock=fake_clock,
        sleep=fake_sleep,
    )
    await engine.start()
    return engine


def _add_tender(rec) -> None:
    root = _real_files()
    if root is None:
        pytest.skip("the real test files are not on this computer")
    for path in sorted((root / BRISSA).glob("*.pdf")):
        files.add_file(rec, path.name, path.read_bytes(), actor="engineer")
    files.add_file(rec, "boq-priced.xlsx", (root / LAHUN).read_bytes(), actor="engineer")


async def _run(engine, chat_id, text):
    brief = await engine.start_brief(chat_id, text)
    async for _ in engine.events(brief):
        pass
    await engine.result(brief)
    return brief


# What the cost book records ------------------------------------------------------------------


async def test_a_streamed_answer_counts_its_prompt_once(registry, data_dir, fake_clock, fake_sleep):
    """Google repeats the whole prompt's count in every chunk of a streamed answer: the real walk
    of 6 Nov recorded 228,382 input tokens for a 28,000-token request (Lahun, Brief ee08b678)."""
    long_answer = " ".join(["word"] * 120)  # 40 chunks of 3 words
    provider = FakeProvider(lambda body: ("text", long_answer))
    engine = await _engine(registry, data_dir, provider, fake_clock, fake_sleep)
    try:
        brief = await _run(engine, "general", "Hello")
        sent = wire_parts(provider.bodies[-1])["total"]
        assert engine.book.tokens(brief_id=brief)["input"] == sent
    finally:
        await engine.shutdown()


async def test_cached_tokens_are_recorded_and_priced_as_cached(
    registry, data_dir, fake_clock, fake_sleep
):
    provider = FakeProvider(lambda body: ("text", "Hello back"), cached=lambda body: 1000)
    engine = await _engine(registry, data_dir, provider, fake_clock, fake_sleep)
    try:
        brief = await _run(engine, "general", "Hello")
        sent = wire_parts(provider.bodies[-1])["total"]
        found = engine.book.tokens(brief_id=brief)
        assert (found["input"], found["cached"]) == (sent, 1000)
        # Gemini 3.1 Flash Lite (genai-prices): 0.25 USD per million in, 0.025 cached, 1.5 out
        out = found["output"]
        expected = (Decimal(sent - 1000) * Decimal("0.25") + 1000 * Decimal("0.025")) / 10**6
        expected += Decimal(out) * Decimal("1.5") / 10**6
        assert engine.book.spent(brief_id=brief, count_equivalent=False) == expected
        summary = costs.summary(engine.book, brief_id=brief, now=fake_clock())
        assert summary["tokens"]["brief"]["cached"] == 1000
    finally:
        await engine.shutdown()


# A whole Brief ---------------------------------------------------------------------------------


async def test_measure_a_brissa_qa_brief(registry, data_dir, fake_clock, fake_sleep):
    project = registry.create("Brissa - measure", "engineer")["id"]
    _add_tender(registry.get(project))
    questions = [
        ("What is the bid security amount and its validity?", "bid security"),
        ("ما هي نسبة المحتجز من المستخلصات؟", "retention"),
    ]
    provider = FakeProvider(qa_script(questions[0][1]))
    engine = await _engine(registry, data_dir, provider, fake_clock, fake_sleep)
    try:
        for text, words in questions:
            provider.script = qa_script(words)
            start = len(provider.bodies)
            await _run(engine, project, text)
            print(f"\n== Brief: {text}")
            total = 0
            for body in provider.bodies[start:]:
                found = wire_parts(body, brief=text)
                total += found["total"]
                print(found)
            print("Brief total", total)
            if os.environ.get("DUMP_BODY"):
                Path(os.environ["DUMP_BODY"]).write_text(
                    json.dumps(provider.bodies[-1], ensure_ascii=False, indent=1)
                )
    finally:
        await engine.shutdown()
