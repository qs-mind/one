"""The blind Checking QS (Plan 4, Task 7): a fresh run every time, given only its Check Packet.

Synthetic «عينة» data only; no test calls a real AI."""

import json

import pytest
from pydantic_ai.messages import (
    ModelMessagesTypeAdapter,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

from qsone import copy
from qsone.engine import checker
from qsone.engine.checker import has_numbers, packet_for, packet_text
from qsone.engine.team import specialist_run
from qsone.engine.tools import call
from qsone.engine.types import DeliverableDraft, Review, TeamMessage
from tests.engine_fakes import DEEPSEEK, OPUS, SONNET, scripted
from tests.engine_fakes import call as tool_call
from tests.team_samples import BRIEF, TeamFakeHost, lead_ctx, sample_ledger

CANARY = "LEAD-REASONING-7f3a"
TITLE = "جدول أسعار - عينة"


@pytest.fixture
def host():
    return TeamFakeHost(answers={"budget": "yes"})


@pytest.fixture
def ctx(rec, host):
    return lead_ctx(rec, host)


def scripted_checker(seen: list, *, code: str = "B", times: int = 1):
    """A checker model that records every message and tool definition it is given."""

    def answer(messages, info):
        seen.append(
            {
                "messages": json.loads(ModelMessagesTypeAdapter.dump_json(messages)),
                "instructions": info.instructions,
                "tools": [t.__dict__ for t in [*info.function_tools, *info.output_tools]],
            }
        )
        comments = [{"about": "03/02", "text": "الهالك غير مذكور - عينة"}]
        return tool_call("final_result", {"code": code, "comments": comments})

    return scripted(*[answer] * times)


def history(*texts: str) -> bytes:
    """A saved history whose reasoning, tool call and tool result carry `texts`."""
    words = " ".join(texts)
    return ModelMessagesTypeAdapter.dump_json(
        [
            ModelRequest(parts=[UserPromptPart(BRIEF)]),
            ModelResponse(
                parts=[
                    TextPart(f"I think {words}"),
                    ToolCallPart("search_records", {"query": words}, tool_call_id="t1"),
                ]
            ),
            ModelRequest(parts=[ToolReturnPart("search_records", words, tool_call_id="t1")]),
        ]
    )


async def deliverable(ctx, ids: dict, **changes) -> str:
    rows = [{"code": "03/02", "amount": {"calc_id": ids["calc"]}}]
    args = {"kind": "table", "title": TITLE, "body": "Section 03 - sample.", "rows": rows}
    args |= {"sources": [ids["source"]]} | changes
    return json.loads(await call("make_deliverable", args, ctx))["deliverable_id"]


async def test_the_checker_is_blind(ctx):
    ids = await sample_ledger(ctx)
    store = ctx.store
    store.save_history(ctx.run_id, history(CANARY))  # the Lead's reasoning and tool arguments
    await call("plan_brief", {"steps": [{"specialist": "Estimator", "task": "x"}]}, ctx)
    specialist = json.loads(
        await call(
            "build_specialist",
            {
                "name_en": "Estimator",
                "name_ar": "مهندس التسعير",
                "instructions": f"Price section 03. {CANARY}",
                "tools": ["send_message"],
            },
            ctx,
        )
    )["specialist_id"]
    store.save_history(specialist_run(store, ctx.brief_id, specialist), history(CANARY))
    store.add_team_message(
        TeamMessage(ctx.brief_id, "m1", copy.ROLE_LEAD, copy.ROLE_LEAD, f"note {CANARY}")
    )
    await call("send_message", {"to": specialist, "text": f"start {CANARY}"}, ctx)
    draft = store.deliverable(await deliverable(ctx, ids))

    packet = packet_for(draft, brief_text=BRIEF, store=store, rec=ctx.rec, unsourced=())
    seen: list = []
    review = await checker.review(packet, scripted_checker(seen), checker=DEEPSEEK, maker=OPUS)
    flat = json.dumps(seen, ensure_ascii=False)
    assert CANARY not in flat and CANARY not in json.dumps(packet.__dict__, default=str)
    assert TITLE in flat and BRIEF in flat and ids["amount_value"] in flat
    assert "39850.50" in flat and "عرض سعر - عينة" in flat  # its inputs and their source
    assert review.code == "B" and review.comments == (
        {"about": "03/02", "text": "الهالك غير مذكور - عينة"},
    )
    assert review.checker == DEEPSEEK.choice and review.same_provider is False


async def test_each_check_starts_fresh(ctx):
    ids = await sample_ledger(ctx)
    draft = ctx.store.deliverable(await deliverable(ctx, ids))
    packet = packet_for(draft, brief_text=BRIEF, store=ctx.store, rec=ctx.rec, unsourced=())
    seen: list = []
    model = scripted_checker(seen, times=2)
    for _ in range(2):
        await checker.review(packet, model, checker=DEEPSEEK, maker=OPUS)
    assert [len(s["messages"]) for s in seen] == [1, 1]  # one request, no earlier messages
    assert seen[1]["instructions"] == seen[0]["instructions"]
    assert seen[0]["instructions"].startswith("You are the Checking QS")


async def test_same_provider_check_is_marked(ctx):
    draft = DeliverableDraft("d1", "answer", "عينة", "Answer - sample.")
    packet = packet_for(draft, brief_text=BRIEF, store=ctx.store, rec=None, unsourced=())
    seen: list = []
    review = await checker.review(packet, scripted_checker(seen), checker=SONNET, maker=OPUS)
    assert review.same_provider is True and review.checker == SONNET.choice


async def test_the_packet_holds_numbers_formulas_sources_and_marks(ctx):
    ids = await sample_ledger(ctx)
    draft = ctx.store.deliverable(await deliverable(ctx, ids, body="Transport 7,500 EGP - sample."))
    packet = packet_for(draft, brief_text=BRIEF, store=ctx.store, rec=ctx.rec, unsourced=("7,500",))
    [formula] = packet.formulas
    assert formula["calc_id"] == ids["calc"] and formula["formula"] == "quantity * rate"
    assert {i["number_id"] for i in formula["inputs"]} == {ids["quantity"], ids["rate"]}
    assert [n["id"] for n in packet.numbers] == [ids["amount"]]
    # the quote, and the calculation the amount comes from
    assert [s["id"] for s in packet.sources][0] == ids["source"]
    assert [s["kind"] for s in packet.sources] == ["quote", "calculation"]
    text = packet_text(packet, "f00d")
    assert '"7,500"' in text and "Off-Desk" in text
    assert text.count("<<data id=f00d") == text.count("<</data id=f00d>>") == 5


async def test_unsourced_numbers_go_to_the_checker(ctx, host):
    ids = await sample_ledger(ctx)
    got = []

    async def checker_fn(packet, maker):
        got.append((packet, maker))
        return Review("A", (), DEEPSEEK.choice, False, 1)

    host.checker = checker_fn
    body = "Rate 39,850.50 EGP; transport 7,500 EGP - sample."
    draft = await deliverable(ctx, ids, body=body)
    out = json.loads(await call("submit_for_check", {"deliverable_id": draft}, ctx))
    [(packet, maker)] = got
    assert packet.unsourced == ("7,500",) and maker == OPUS.choice
    assert out["code"] == "A" and out["round"] == 1
    [event] = [e for e in host.events if type(e).__name__ == "Reviewed"]
    assert event.deliverable_id == draft and ctx.store.unchecked(ctx.brief_id) == []
    with pytest.raises(Exception, match="already checked"):
        await call("submit_for_check", {"deliverable_id": draft}, ctx)


async def test_two_rounds_then_the_engineer_decides(ctx, host):
    ids = await sample_ledger(ctx)
    packets = []

    async def checker_fn(packet, maker):
        packets.append(packet)
        comment = {"about": "03/02", "text": f"round {len(packets)}: waste is missing"}
        return Review("C", (comment,), DEEPSEEK.choice, False, 0)

    host.checker = checker_fn
    v1 = await deliverable(ctx, ids)
    first = json.loads(await call("submit_for_check", {"deliverable_id": v1}, ctx))
    assert first["code"] == "C" and first["rounds_left"] == 1 and first["round"] == 1
    v2 = await deliverable(ctx, ids, replaces=v1, body="Revised - sample.")
    second = json.loads(await call("submit_for_check", {"deliverable_id": v2}, ctx))
    assert second["rounds_left"] == 0 and second["round"] == 2
    assert packets[1].previous_comments == (
        {"round": 1, "code": "C", "about": "03/02", "text": "round 1: waste is missing"},
    )

    v3 = await deliverable(ctx, ids, replaces=v2, body="Revised again - sample.")
    host.answers["disagreement"] = "yes"
    third = json.loads(await call("submit_for_check", {"deliverable_id": v3}, ctx))
    assert len(packets) == 2  # the checker did not run a third time
    assert third["code"] == "C" and third["rounds_left"] == 0 and third["engineer_decides"]
    [card] = [c for c in host.cards if c.kind == "disagreement"]
    for lang in ("en", "ar"):
        assert copy.fill(copy.DISAGREEMENT, agent=copy.ROLE_LEAD)[lang] in card.detail[lang]
    assert "round 1: waste" in card.detail["en"] and "round 2: waste" in card.detail["ar"]
    assert "Revised again - sample." in card.detail["en"] and "4782060.00 EGP" in card.detail["en"]
    assert card.options == ("yes", "no") and ctx.store.pending(ctx.brief_id) == []
    assert [r.round for r in ctx.store.reviews(v3)] == [1, 2]


def test_has_numbers():
    assert has_numbers(DeliverableDraft("d", "table", "t", "", ({"q": {"number_id": "n"}},)))
    assert has_numbers(DeliverableDraft("d", "answer", "t", "about 120 m3"))
    assert not has_numbers(DeliverableDraft("d", "answer", "t", "see clause 14.2, page 3"))
