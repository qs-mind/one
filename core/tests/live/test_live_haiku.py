"""The one opt-in live test (Plan 4, Task 10): a real Brief on Claude Haiku 5.5.

Skipped unless QSONE_LIVE=1 and ANTHROPIC_API_KEY are set; CI never sets QSONE_LIVE. Run it by
hand, once:

    QSONE_LIVE=1 ANTHROPIC_API_KEY=… node scripts/python.mjs -m pytest core/tests/live -m live -v

The key goes only into this test's in-memory key store. Every role runs on claude-haiku-5-5,
the Brief cap is 0.10 USD, and the only file is a synthetic sample BOQ («عينة»)."""

import asyncio
import os
import re
import time
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from qsone import keys
from qsone.engine import costs, roles
from qsone.engine.runner import Engine
from qsone.engine.types import Asked, ModelChoice, Reviewed, Status, TextDelta, Unsourced
from qsone.projects import Projects
from qsone.records.files import add_file
from tests.samples import sample_xlsx

HAIKU = ModelChoice("anthropic", "claude-haiku-5-5")
CAP = Decimal("0.10")
DATED = "2026-11-02"  # the sample BOQ's own date: the Source Ledger needs one for each number
BRIEF = (
    f"جدول الكميات - عينة بتاريخ {DATED}. ابني مهندس متخصص واحد بس يطلع كمية البند 03/02 منه "
    "ويسجّلها بمصدرها، وبعدين اعمل بيها جدول صغير وابعته للمراجعة، وقولّي الكمية في ردّك."
)
# What the test answers on the engineer's behalf: start, carry on to the cap, never go outside.
ANSWERS = {"budget": "yes", "disagreement": "yes"}
TIMEOUT = 600  # seconds for the whole Brief

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        os.environ.get("QSONE_LIVE") != "1" or not os.environ.get("ANTHROPIC_API_KEY"),
        reason="live: needs QSONE_LIVE=1 and ANTHROPIC_API_KEY",
    ),
]


@pytest.fixture
def no_internet():
    """This test alone reaches Anthropic: it replaces the autouse guard of the same name."""


@pytest.fixture
async def engine(data_dir, memory_keyring):
    keys.set_key("anthropic", os.environ["ANTHROPIC_API_KEY"])  # the in-memory store only
    for role in roles.ROLES:
        roles.choose(role, HAIKU)
    costs.save_caps({"brief": format(CAP, "f")})
    registry = Projects(data_dir)
    found = Engine(projects=registry, data_dir=data_dir)
    await found.start()
    yield found
    await found.shutdown()
    registry.close_all()


def answer(card) -> str:
    if card.kind == "cap" and "continue" in card.options:
        return "continue"  # the hard stop at the cap still holds
    return ANSWERS.get(card.kind, "no")


async def drive(engine: Engine, brief_id: str) -> list:
    seen = []
    async for event in engine.events(brief_id):
        seen.append(event)
        if isinstance(event, Asked):
            await engine.answer(event.card.id, answer(event.card))
    await engine.result(brief_id)
    return seen


def western(text: str) -> str:
    return text.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))


async def test_one_cheap_brief_on_haiku(engine, capsys):
    project = engine.projects.create("تجربة - عينة", "engineer")["id"]
    boq = sample_xlsx(
        {
            "BOQ": [
                [f"جدول الكميات - عينة، بتاريخ {DATED}"],
                ["البند", "الوصف", "الوحدة", "الكمية"],
                ["03/01", "خرسانة عادية للأساسات - عينة", "م3", 45],
                ["03/02", "خرسانة مسلحة للأسقف - عينة", "م3", 120],
            ]
        }
    )
    add_file(engine.projects.get(project), "جدول الكميات - عينة.xlsx", boq, actor="engineer")

    began = time.monotonic()
    brief = await engine.start_brief(project, BRIEF)
    events = await asyncio.wait_for(drive(engine, brief), TIMEOUT)
    seconds = round(time.monotonic() - began)

    reply = "".join(e.text for e in events if isinstance(e, TextDelta))
    spent = costs.summary(engine.cost_book(), brief_id=brief, now=datetime.now(UTC))["brief"]
    store = engine._place(project).store
    runs = store.runs(brief)
    specialists = {r["spec"].id for r in runs if r["spec"].role == "specialist"}
    reviews = [e.review for e in events if isinstance(e, Reviewed)]
    unsourced = [v for e in events if isinstance(e, Unsourced) for v in e.values]
    with capsys.disabled():
        print(f"\nlive Brief: {spent} USD in {seconds} s, {len(runs)} agent runs")
        print(f"models: {sorted({r['choice'].model for r in runs})}")
        print(f"reviews: {[(r.code, r.checker.model, r.same_provider) for r in reviews]}")
        print(f"unsourced: {unsourced}")
        print(f"reply: {reply}")

    assert [e.state for e in events if isinstance(e, Status)][-1] == "done"
    assert len(re.findall(r"[؀-ۿ]", reply)) > len(re.findall(r"[A-Za-z]", reply))
    assert len(specialists) == 1
    assert reviews and reviews[-1].code in ("A", "B", "C")
    assert all(r.same_provider for r in reviews)  # every role on Anthropic
    assert "120" in western(reply) and "120" not in [western(v) for v in unsourced]
    assert Decimal(spent) < CAP
