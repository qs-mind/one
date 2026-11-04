"""Checkpoints, approvals, writes, the team, deliverables, reviews and costs in the encrypted
Records files (Plan 4, Task 2)."""

import json
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from qsone.engine.general import open_engineer_records
from qsone.engine.store import CostBook, Store
from qsone.engine.types import (
    AgentSpec,
    Card,
    DeliverableDraft,
    ModelChoice,
    Review,
    TeamMessage,
)
from qsone.projects import Projects
from qsone.records import audit, db, schema
from qsone.records.project import Records

CAIRO = timezone(timedelta(hours=2), "Cairo")  # Egypt's winter time, fixed for the test
OPUS = ModelChoice("anthropic", "claude-opus-5-5")
CHECKER = ModelChoice("standard:deepseek", "deepseek-chat")
LEAD = AgentSpec(
    id="lead",
    name={"en": "Lead QS", "ar": "كبير المساحين"},
    role="lead",
    instructions="Lead the Brief.",
    tools=("plan_brief", "delegate"),
    tier="lead",
)
SPECIALIST = AgentSpec(
    id="rates",
    name={"en": "Rates QS", "ar": "مساح الأسعار"},
    role="specialist",
    instructions="Price the items.",
    tools=("search_records",),
    tier="specialist",
)


def card(card_id="c1", title="أرسل جدول الكميات - عينة"):
    return Card(
        id=card_id,
        kind="outside",
        title={"en": "Send the BOQ - sample", "ar": title},
        detail={"en": "This leaves the computer.", "ar": "هذا يخرج من الجهاز."},
        options=("yes", "no"),
    )


def draft(draft_id, replaces=None):
    return DeliverableDraft(
        id=draft_id,
        kind="table",
        title="أسعار الخرسانة - عينة",
        body="| البند | السعر |",
        rows=({"item": "03/02", "rate": {"number_id": "n1"}},),
        sources=("s1",),
        replaces=replaces,
    )


def review(code, round_=1):
    return Review(
        code=code,
        comments=({"about": "03/02", "text": "السعر بلا مصدر"},),
        checker=CHECKER,
        same_provider=False,
        round=round_,
    )


def add_cost(book, *, usd, at, brief_id="b1", project_id="p1", equivalent=False, tokens=(1, 1)):
    book.add(
        brief_id=brief_id,
        project_id=project_id,
        run_id="r1",
        role="lead",
        choice=OPUS,
        input_tokens=tokens[0],
        output_tokens=tokens[1],
        usd=usd,
        equivalent=equivalent,
        basis="sample prices",
        at=at,
    )


def file_bytes(folder) -> bytes:
    return b"".join(p.read_bytes() for p in folder.rglob("*") if p.is_file())


# Briefs and runs ----------------------------------------------------------------------------


def test_history_and_results_round_trip(rec):
    s = Store(rec, project_id=rec.id)
    b = s.new_brief(rec.id, "سعّر بند الخرسانة - عينة")
    r = s.new_run(b, LEAD, OPUS, None)
    s.save_history(r, b"[1]")
    s.save_history(r, b"[1,2]")
    assert s.run(r)["history"] == b"[1,2]"
    s.save_result(r, "call-1", "done")
    assert s.results(r) == {"call-1": "done"}


def test_a_result_is_saved_once(rec):
    s = Store(rec, project_id=rec.id)
    r = s.new_run(s.new_brief(rec.id, "x"), LEAD, OPUS, None)
    s.save_result(r, "call-1", "done")
    with pytest.raises(db.IntegrityError):
        s.save_result(r, "call-1", "again")
    assert s.results(r) == {"call-1": "done"}


def test_a_brief_keeps_its_text_status_step_and_flags(rec):
    s = Store(rec, project_id=rec.id)
    b = s.new_brief(rec.id, "سعّر - عينة")
    brief = s.brief(b)
    assert brief["chat_id"] == rec.id and brief["text"] == "سعّر - عينة"
    assert brief["status"] == "queued" and brief["step"] is None
    assert brief["read_untrusted"] == 0 and brief["allowed"] == []
    step = {"en": "Pricing item 03/02", "ar": "تسعير البند 03/02"}
    s.set_status(b, "running", step)
    s.set_status(b, "waiting_engineer")  # no step given: the last step stays
    s.mark_untrusted(b)
    s.allow(b, "web_search")
    s.allow(b, "web_search")
    brief = s.brief(b)
    assert brief["status"] == "waiting_engineer" and brief["step"] == step
    assert brief["read_untrusted"] == 1
    assert s.allowed(b) == {"web_search"} and brief["allowed"] == ["web_search"]


def test_runs_keep_spec_choice_parent_and_session(rec):
    s = Store(rec, project_id=rec.id)
    b = s.new_brief(rec.id, "x")
    lead = s.new_run(b, LEAD, OPUS, None)
    child = s.new_run(b, SPECIALIST, ModelChoice("claude-code", "sonnet"), lead)
    s.set_run(child, status="done", session_id="sess-1", choice=CHECKER)
    runs = s.runs(b)
    assert [r["id"] for r in runs] == [lead, child]
    got = s.run(child)
    assert got["spec"] == SPECIALIST and got["parent_id"] == lead
    assert got["choice"] == CHECKER and got["status"] == "done" and got["session_id"] == "sess-1"
    assert got["history"] is None
    assert s.run(lead)["spec"] == LEAD and s.run(lead)["choice"] == OPUS


def test_unfinished_lists_every_waiting_state(rec):
    s = Store(rec, project_id=rec.id)
    states = ["queued", "running", "waiting_engineer", "waiting_connection", "paused_cap"]
    ids = {}
    for state in [*states, "stopped", "done", "failed"]:
        ids[state] = s.new_brief(rec.id, state)
        s.set_status(ids[state], state)
    assert [b["id"] for b in s.unfinished()] == [ids[state] for state in states]


def test_lead_histories_of_earlier_briefs_in_the_chat(rec):
    s = Store(rec, project_id=rec.id)
    first = s.new_brief(rec.id, "one")
    lead_1 = s.new_run(first, LEAD, OPUS, None)
    s.save_history(lead_1, b"lead-1")
    s.save_history(s.new_run(first, SPECIALIST, OPUS, lead_1), b"specialist")
    other_chat = s.new_brief("general", "elsewhere")
    s.save_history(s.new_run(other_chat, LEAD, OPUS, None), b"other chat")
    second = s.new_brief(rec.id, "two")
    s.save_history(s.new_run(second, LEAD, OPUS, None), b"lead-2")
    third = s.new_brief(rec.id, "three")
    s.save_history(s.new_run(third, LEAD, OPUS, None), b"lead-3")
    assert s.lead_histories(rec.id, before=third) == [b"lead-1", b"lead-2"]
    assert s.lead_histories(rec.id, before=first) == []


# Approvals ----------------------------------------------------------------------------------


def test_approvals_are_stored_settled_and_audited(rec):
    s = Store(rec, project_id=rec.id)
    b = s.new_brief(rec.id, "x")
    s.add_approval(b, card("c1"), run_id="r1", call_id="call-1")
    s.add_approval(b, card("c2"))
    assert s.pending(b) == [card("c1"), card("c2")]
    with pytest.raises(ValueError):
        s.settle("c1", "maybe")  # not one of the card's options
    s.settle("c1", "yes")
    assert s.pending(b) == [card("c2")]
    with pytest.raises(LookupError):
        s.settle("c1", "no")  # already settled
    with rec.read() as c:
        actions = [row["action"] for row in audit.history(c, "c1")]
        row = c.execute("select status, choice, run_id, call_id from approvals where id = 'c1'")
        assert row.fetchone() == ("settled", "yes", "r1", "call-1")
    assert actions == ["ask", "settle"]


def test_withdraw_pending_approvals(rec):
    s = Store(rec, project_id=rec.id)
    b = s.new_brief(rec.id, "x")
    other = s.new_brief(rec.id, "y")
    s.add_approval(b, card("c1"))
    s.add_approval(b, card("c2"))
    s.add_approval(other, card("c3"))
    s.settle("c1", "no")
    s.withdraw_pending(b)
    assert s.pending(b) == [] and s.pending(other) == [card("c3")]
    with pytest.raises(LookupError):
        s.settle("c2", "yes")
    with rec.read() as c:
        rows = dict(c.execute("select id, status from approvals"))
        assert [r["action"] for r in audit.history(c, "c2")] == ["ask", "withdraw"]
    assert rows == {"c1": "settled", "c2": "withdrawn", "c3": "pending"}


# Writes, team, deliverables, reviews ---------------------------------------------------------


def test_write_is_remembered_once(rec):
    s = Store(rec, project_id=rec.id)
    b = s.new_brief(rec.id, "x")
    assert s.known_write(b, "k1") is None
    s.remember_write(b, "k1", "n1")
    s.remember_write(b, "k1", "n2")
    assert s.known_write(b, "k1") == "n1"
    with rec.read() as c:
        assert c.execute("select count(*) from brief_writes").fetchone()[0] == 1
    with pytest.raises(db.IntegrityError), rec.write("test") as c:
        c.execute("update brief_writes set result_id = 'n9'")


def test_team_messages_in_order_and_append_only(rec):
    s = Store(rec, project_id=rec.id)
    b = s.new_brief(rec.id, "x")
    lead, rates = LEAD.name, SPECIALIST.name
    s.add_team_message(TeamMessage(b, "m1", lead, rates, "سعّر البند 03/02"))
    s.add_team_message(TeamMessage(b, "m2", rates, lead, "تم"))
    team = s.team(b)
    assert [(m["id"], m["sender"], m["recipient"], m["text"]) for m in team] == [
        ("m1", lead, rates, "سعّر البند 03/02"),
        ("m2", rates, lead, "تم"),
    ]
    assert team[0]["at"]
    for sql in ["update team_messages set text = 'x'", "delete from team_messages"]:
        with pytest.raises(db.IntegrityError), rec.write("test") as c:
            c.execute(sql)


def test_deliverables_round_trip_and_unchecked(rec):
    s = Store(rec, project_id=rec.id)
    b = s.new_brief(rec.id, "x")
    r = s.new_run(b, LEAD, OPUS, None)
    s.save_deliverable(b, r, draft("d1"))
    s.save_deliverable(b, r, draft("d2", replaces="d1"))  # d1 is replaced, so not unchecked
    s.save_deliverable(b, r, draft("d3"))
    assert s.deliverable("d2") == draft("d2", replaces="d1")
    assert s.unchecked(b) == [draft("d2", replaces="d1"), draft("d3")]
    s.save_review("d3", review("A"))
    assert s.unchecked(b) == [draft("d2", replaces="d1")]


def test_reviews_follow_the_replaces_chain(rec):
    s = Store(rec, project_id=rec.id)
    b = s.new_brief(rec.id, "x")
    r = s.new_run(b, LEAD, OPUS, None)
    s.save_deliverable(b, r, draft("v1"))
    s.save_review("v1", review("C", 1))
    s.save_deliverable(b, r, draft("v2", replaces="v1"))
    s.save_review("v2", review("C", 2))
    assert s.reviews("v2") == [review("C", 1), review("C", 2)]
    assert s.reviews("v1") == [review("C", 1)]
    with rec.read() as c:
        (review_id,) = c.execute("select id from reviews where deliverable_id = 'v2'").fetchone()
        assert [row["action"] for row in audit.history(c, review_id)] == ["review"]
    for sql in ["update reviews set code = 'A'", "delete from reviews"]:
        with pytest.raises(db.IntegrityError), rec.write("test") as c:
            c.execute(sql)


# The file itself ----------------------------------------------------------------------------


def test_engine_tables_are_encrypted_on_disk(rec):
    s = Store(rec, project_id=rec.id)
    b = s.new_brief(rec.id, "سعّر بند الخرسانة السرية - عينة")
    r = s.new_run(b, LEAD, OPUS, None)
    s.save_history(r, b"secret-history-canary")
    s.add_team_message(TeamMessage(b, "m1", LEAD.name, SPECIALIST.name, "رسالة الفريق السرية"))
    s.add_approval(b, card("c1", title="بطاقة الموافقة السرية"))
    for phase in ("open", "closed"):
        blob = file_bytes(rec.folder)
        for word in [
            "الخرسانة السرية",
            "رسالة الفريق السرية",
            "بطاقة الموافقة السرية",
            "secret-history-canary",
        ]:
            assert word.encode() not in blob, (phase, word)
        rec.close()


def test_project_file_from_plan_2_upgrades(tmp_path, monkeypatch):
    monkeypatch.setattr(schema, "MIGRATIONS", schema.MIGRATIONS[:1])
    old = Records.create(tmp_path / "p", name="x", actor="engineer")
    with old.write("engineer") as c:
        c.execute(
            "insert into items(id,kind,code,fields,created_at,created_by,updated_at,updated_by)"
            " values ('i1','boq_item','03/02','{}','t','e','t','e')"
        )
    old.close()
    monkeypatch.undo()
    rec = Records.open(tmp_path / "p")
    try:
        with rec.read() as c:
            assert c.execute("PRAGMA user_version").fetchone()[0] == len(schema.MIGRATIONS)
            assert c.execute("select code from items").fetchall() == [("03/02",)]
        s = Store(rec, project_id=rec.id)
        assert s.brief(s.new_brief(rec.id, "x"))["status"] == "queued"
    finally:
        rec.close()


def test_engineer_records_is_not_a_project(data_dir):
    engineer = open_engineer_records(data_dir)
    try:
        assert engineer.folder == data_dir / "engineer"
        assert engineer.meta()["name"] == "Engineer Records"
        Store(engineer, project_id=None).new_brief("general", "x")
    finally:
        engineer.close()
    again = open_engineer_records(data_dir)  # opens the same file the second time
    try:
        assert len(Store(again, project_id=None).unfinished()) == 1
    finally:
        again.close()
    assert Projects(data_dir).list() == []


# Costs --------------------------------------------------------------------------------------


def test_costs_are_append_only(general):
    add_cost(CostBook(general), usd=Decimal("0.10"), at=datetime(2026, 11, 5, 8, tzinfo=UTC))
    for sql in ["update ai_costs set usd = '0'", "delete from ai_costs"]:
        with pytest.raises(db.IntegrityError), general.write("test") as c:
            c.execute(sql)


def test_spent_by_brief_day_and_month(general):
    book = CostBook(general, local_tz=CAIRO)
    add_cost(book, usd=Decimal("1.20"), at=datetime(2026, 11, 5, 23, 30, tzinfo=CAIRO))
    add_cost(book, usd=Decimal("0.80"), at=datetime(2026, 11, 6, 0, 10, tzinfo=CAIRO))
    add_cost(book, usd=Decimal("0.05"), at=datetime(2026, 10, 31, 23, tzinfo=CAIRO), brief_id="b0")
    assert book.spent(day=date(2026, 11, 5), count_equivalent=False) == Decimal("1.20")
    assert book.spent(day=date(2026, 11, 6), count_equivalent=False) == Decimal("0.80")
    assert book.spent(month=(2026, 11), count_equivalent=False) == Decimal("2.00")
    assert book.spent(brief_id="b1", count_equivalent=False) == Decimal("2.00")
    assert book.spent(count_equivalent=False) == Decimal("2.05")
    with general.read() as c:
        rows = c.execute("select at, local_day, usd from ai_costs order by id").fetchall()
    assert rows[0] == ("2026-11-05T21:30:00.000000+00:00", "2026-11-05", "1.20")


def test_equivalent_cost_counted_only_when_asked(general):
    book = CostBook(general)
    at = datetime(2026, 11, 5, 8, tzinfo=UTC)
    add_cost(book, usd=Decimal("0.30"), at=at)
    add_cost(book, usd=Decimal("0.70"), at=at, equivalent=True)
    assert book.spent(brief_id="b1", count_equivalent=False) == Decimal("0.30")
    assert book.spent(brief_id="b1", count_equivalent=True) == Decimal("1.00")


def test_unknown_cost_is_null_not_zero(general):
    book = CostBook(general)
    at = datetime(2026, 11, 5, 8, tzinfo=UTC)
    add_cost(book, usd=None, at=at)
    add_cost(book, usd=Decimal("0.25"), at=at)
    with general.read() as c:
        assert [u for (u,) in c.execute("select usd from ai_costs order by id")] == [None, "0.25"]
    assert book.spent(brief_id="b1", count_equivalent=True) == Decimal("0.25")
    assert book.spent(brief_id="nothing", count_equivalent=True) == Decimal("0")


def test_money_is_never_a_float(general):
    with pytest.raises(TypeError):
        add_cost(CostBook(general), usd=0.1, at=datetime(2026, 11, 5, 8, tzinfo=UTC))
    with pytest.raises(ValueError):  # the time must say its zone
        add_cost(CostBook(general), usd=Decimal("0.1"), at=datetime(2026, 11, 5, 8))


def test_tokens_per_request_from_past_runs(general):
    book = CostBook(general)
    at = datetime(2026, 11, 5, 8, tzinfo=UTC)
    assert book.tokens_per_request("p1") is None
    add_cost(book, usd=None, at=at, tokens=(1000, 100))
    add_cost(book, usd=None, at=at, tokens=(2001, 201))
    add_cost(book, usd=None, at=at, project_id=None, tokens=(9, 9))
    assert book.tokens_per_request("p1") == (1501, 151, 2)
    assert book.tokens_per_request(None) == (9, 9, 1)


def test_json_is_kept_as_written(rec):
    s = Store(rec, project_id=rec.id)
    b = s.new_brief(rec.id, "x")
    s.set_status(b, "running", {"en": "step", "ar": "خطوة"})
    with rec.read() as c:
        (step,) = c.execute("select step from briefs").fetchone()
    assert "خطوة" in step and json.loads(step)["ar"] == "خطوة"
