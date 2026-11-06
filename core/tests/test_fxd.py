"""Synthetic regressions for the second walk; no live AI."""

import json

import pytest

from qsone.cli.__main__ import human_result
from qsone.engine.tools import ModelRetry, call
from tests.fakes_tools import tool_ctx


@pytest.mark.anyio
@pytest.mark.parametrize(
    "text",
    [
        "What is the submission deadline and project duration?",
        "اعرض اللوحات الكهربائية وعد قواطع MCCB",
    ],
)
async def test_brief_echo_refused(rec, text):
    ctx = tool_ctx(
        rec, answers={"question": json.dumps({"choice": "sent", "answers": {"q1": "sample"}})}
    )
    with rec.write("engineer") as c:
        c.execute("UPDATE briefs SET text=? WHERE id=?", (text, ctx.brief_id))
    with pytest.raises(ModelRetry, match="answer from the files"):
        await call(
            "ask_engineer", {"questions": [{"id": "q1", "text": text, "free_text": True}]}, ctx
        )
    assert not ctx.host.cards
    assert not ctx.store.pending(ctx.brief_id)


def test_upload_nonfailures():
    result = human_result(
        {
            "uploads": [
                {"status": "unreadable", "note": "FILE_SCANNED_PAGES"},
                {"status": "stored", "note": "FILE_NOT_READ_YET"},
                {"status": "failed"},
            ]
        }
    )
    assert result["failed"] == 1
    assert result["scanned"] == 1
    assert result["kept"] == 1


def test_map_wait_local_waiting_without_status(tmp_path, monkeypatch):
    from qsone.cli.commands import Commands

    class Client:
        n = 0

        def get(self, route, **kwargs):
            if "/messages" in route:
                return {"messages": []}
            self.n += 1
            return {
                "files": [{"local_state": "waiting" if self.n == 1 else "done", "ai_state": "done"}]
            }

    client = Client()
    monkeypatch.setattr("qsone.cli.commands.time.sleep", lambda _: None)
    result = Commands(client, {"cards": {}}, tmp_path / "session.json").map("p", wait=1)
    assert result["state"] == "done"
    assert client.n == 2


def test_map_digest(rec):
    from qsone.engine.map_digest import digest
    from qsone.records import files
    from qsone.records.mapping import store

    f = files.add_file(rec, "sample.txt", b"sample tender data", actor="engineer")
    with rec.write("one") as c:
        store.write(
            c,
            rec,
            "map_files",
            {
                "file_id": f.id,
                "key_pages": [
                    {"label": {"en": "Key Tender Data", "ar": "بيانات المناقصة"}, "page": 7}
                ],
            },
        )
    text = digest(rec)
    assert "Key Tender Data" in text and "7" in text and f.id in text
    assert len(text.encode()) <= 1200


@pytest.mark.anyio
@pytest.mark.parametrize(
    "brief,question",
    [
        (
            "List the electrical sheets and count MCCB.",
            "LIST the electrical sheets, and count mccb?",
        ),
        ("ما هو موعد التسليم ومدة المشروع؟", "ما هو موعد التسليم، ومدة المشروع"),
        (
            "What is the submission deadline and the project duration?",
            "What is the submission deadline?",
        ),
    ],
)
async def test_normalised_and_partial_echo_refused(rec, brief, question):
    ctx = tool_ctx(
        rec, answers={"question": json.dumps({"choice": "sent", "answers": {"q1": "sample"}})}
    )
    with rec.write("engineer") as c:
        c.execute("UPDATE briefs SET text=? WHERE id=?", (brief, ctx.brief_id))
    with pytest.raises(ModelRetry, match="answer from the files"):
        await call("ask_engineer", {"questions": [{"id": "q1", "text": question}]}, ctx)
    assert not ctx.host.cards


def test_upload_summary_uses_api_note_key():
    result = human_result(
        {
            "uploads": [
                {
                    "status": "unreadable",
                    "note_key": "FILE_SCANNED_PAGES",
                    "note": {"en": "Sample scan", "ar": "سكان عينة"},
                },
                {"status": "stored", "note_key": "FILE_NOT_READ_YET"},
                {"status": "unreadable", "note_key": "FILE_UNREADABLE"},
            ]
        }
    )
    assert result["scanned"] == 1
    assert result["kept"] == 1
    assert result["failed"] == 1


def test_digest_keeps_navigation_and_fact_states_within_budget(rec):
    from qsone.engine.map_digest import digest
    from qsone.records import files
    from qsone.records.mapping import store

    f = files.add_file(rec, "sample.txt", b"sample", actor="engineer")
    with rec.write("one") as c:
        store.write(
            c,
            rec,
            "map_files",
            {
                "file_id": f.id,
                "key_pages": [
                    {"label": {"en": "Key Tender Data", "ar": "بيانات المناقصة"}, "page": 7}
                ],
            },
        )
        for i, state in enumerate(("found", "blank", "conflict")):
            store.write(
                c,
                rec,
                "map_facts",
                {
                    "id": str(i),
                    "name": {"en": "Tender date", "ar": "تاريخ المناقصة"},
                    "file_id": f.id,
                    "locator": {"page": 7},
                    "value": "sample " * 100,
                    "state": state,
                },
            )
    text = digest(rec)
    assert "Key Tender Data" in text
    assert "found" in text and "blank" in text and "conflict" in text
    assert len(text.encode()) <= 1200


@pytest.mark.anyio
async def test_paused_state_precedes_card_but_waiting_step_follows_it():
    import asyncio
    from types import SimpleNamespace

    from qsone import copy
    from qsone.engine.runner import _Brief
    from qsone.engine.types import Asked, Card

    events = []
    card = Card(
        "sample-card",
        "question",
        {"en": "Sample", "ar": "عينة"},
        {"en": "Sample", "ar": "عينة"},
        ("sent",),
    )
    host = SimpleNamespace(
        store=SimpleNamespace(pending=lambda _: [card]),
        brief_id="sample",
        waiting={},
        step=None,
        lead_run_id=None,
        state="running",
        emit=lambda event: events.append(event),
        _waiting_count=lambda: None,
    )

    def state(value, step=None):
        host.state = value
        events.append((value, step))

    host.set_state = state
    task = asyncio.create_task(_Brief.ask(host, card))
    await asyncio.sleep(0)
    assert events[0] == ("waiting_engineer", None)
    assert isinstance(events[1], Asked)
    assert events[2] == ("waiting_engineer", copy.fill(copy.STEP_WAITING, title=card.title))
    host.waiting[card.id][1].set_result("sent")
    assert await task == "sent"
    from qsone.engine.tools import REGISTRY

    tool = REGISTRY["ask_engineer"]
    assert (
        tool.activity(tool.args.model_validate({"questions": [{"id": "q", "text": "Sample?"}]}))
        != copy.DOING_ASK
    )


@pytest.mark.anyio
async def test_short_echo_of_one_requested_fact_is_refused(rec):
    ctx = tool_ctx(
        rec, answers={"question": json.dumps({"choice": "sent", "answers": {"q1": "sample"}})}
    )
    with rec.write("engineer") as c:
        c.execute(
            "UPDATE briefs SET text=? WHERE id=?",
            ("What is the submission deadline and project duration?", ctx.brief_id),
        )
    with pytest.raises(ModelRetry, match="answer from the files"):
        await call("ask_engineer", {"questions": [{"id": "q1", "text": "Project duration?"}]}, ctx)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "brief,question",
    [
        ("What is the concrete rate?", "What is your concrete rate?"),
        ("سعر الخرسانة كام؟", "سعر الخرسانة عندك كام؟"),
        ("What is the concrete grade?", "What is the concrete rate?"),
    ],
)
async def test_shared_words_do_not_refuse_engineer_supplied_fact(rec, brief, question):
    ctx = tool_ctx(
        rec, answers={"question": json.dumps({"choice": "sent", "answers": {"q1": "sample"}})}
    )
    with rec.write("engineer") as c:
        c.execute("UPDATE briefs SET text=? WHERE id=?", (brief, ctx.brief_id))
    result = await call("ask_engineer", {"questions": [{"id": "q1", "text": question}]}, ctx)
    assert "sample" in result
    assert len(ctx.host.cards) == 1


@pytest.mark.anyio
@pytest.mark.parametrize(
    "question",
    [
        "Could you tell me the submission deadline please?",
        "Can you give me the project duration?",
    ],
)
async def test_polite_rewording_is_still_a_brief_echo(rec, question):
    ctx = tool_ctx(
        rec, answers={"question": json.dumps({"choice": "sent", "answers": {"q1": "sample"}})}
    )
    with rec.write("engineer") as c:
        c.execute(
            "UPDATE briefs SET text=? WHERE id=?",
            ("What is the submission deadline and project duration?", ctx.brief_id),
        )
    with pytest.raises(ModelRetry, match="answer from the files"):
        await call("ask_engineer", {"questions": [{"id": "q1", "text": question}]}, ctx)
    assert not ctx.host.cards


@pytest.mark.anyio
async def test_requested_pricing_can_ask_for_engineers_own_rate(rec):
    ctx = tool_ctx(
        rec, answers={"question": json.dumps({"choice": "sent", "answers": {"q1": "sample"}})}
    )
    with rec.write("engineer") as c:
        c.execute(
            "UPDATE briefs SET text=? WHERE id=?",
            ("Price concrete using your concrete rate", ctx.brief_id),
        )
    result = await call(
        "ask_engineer", {"questions": [{"id": "q1", "text": "Your concrete rate?"}]}, ctx
    )
    assert "sample" in result
