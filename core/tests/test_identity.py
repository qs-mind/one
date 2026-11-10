"""The team's identities (Phase 1, C5): a member's identity card, its record counted from real
work, keeping a member for later tenders, and the two team routes.

Scripted models only; no test calls a real AI. Synthetic «عينة» data only."""

import asyncio
import json
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from qsone import activity, copy
from qsone import phase1_contract as c
from qsone.app import create_app
from qsone.engine import identity, identity_live
from qsone.engine.store import CostBook
from qsone.engine.team.identity_card import names_a_person
from qsone.engine.tools import Denied, call
from qsone.records.project import RecordsError
from tests.conftest import AUTH, SECRET
from tests.engine_fakes import OPUS, SAMPLE_SHEET, FakeHost
from tests.team_samples import lead_ctx

AT = datetime(2026, 11, 10, 8, tzinfo=UTC)
CONTRACTS = {
    "name": {"en": "Contracts QS", "ar": "مهندس العقود"},
    "title": {"en": "Contracts quantity surveyor", "ar": "مهندس كميات العقود"},
    "speciality": {"en": "Contract conditions agent", "ar": "وكيل شروط التعاقد"},
    "style": {
        "en": "Reads every clause, quotes it, flags what costs money.",
        "ar": "بيقرا كل بند، بيقتبسه، وبينبّه على اللي بيكلّف فلوس.",
    },
    "tools": ["search_records", "read_chunk", "send_message"],
}


@pytest.fixture(autouse=True)
def no_sheet():
    identity.forget_sheet()
    yield
    identity.forget_sheet()


def refused(rec, draft, **more) -> RecordsError:
    with pytest.raises(RecordsError) as e:
        identity.propose(rec, [draft], **more)
    return e.value


def cost(book, *, member_id, project_id, usd, role="specialist", equivalent=False):
    book.add(
        brief_id="b1",
        project_id=project_id,
        run_id="r1",
        role=role,
        choice=OPUS.choice,
        input_tokens=10,
        output_tokens=5,
        usd=None if usd is None else Decimal(usd),
        equivalent=equivalent,
        basis="sample",
        at=AT,
        member_id=member_id,
    )


# The identity card ----------------------------------------------------------------------------


def test_identity_fields_required(rec):
    """Title, speciality and style in both languages; the title joins a QS term with a role;
    a person's name is refused."""
    no_ar = CONTRACTS | {"title": {"en": "Contracts quantity surveyor", "ar": ""}}
    e = refused(rec, no_ar)
    assert e.status == 422 and e.field == "team[0].title" and e.text["en"].startswith("team[0]")
    assert refused(rec, CONTRACTS | {"style": None}).field == "team[0].style"

    no_role = CONTRACTS | {"title": {"en": "Contracts", "ar": "العقود"}}
    assert refused(rec, no_role).text == copy.fill(
        copy.IDENTITY_TITLE_NO_ROLE, field="team[0].title"
    )
    bare_role = CONTRACTS | {"title": {"en": "Quantity surveyor", "ar": "مهندس كميات العقود"}}
    assert refused(rec, bare_role).field == "team[0].title"
    no_agent = CONTRACTS | {"speciality": {"en": "Contract conditions", "ar": "شروط التعاقد"}}
    assert refused(rec, no_agent).field == "team[0].speciality"

    for field, pair in (
        ("name", {"en": "Eng. Contracts QS", "ar": "مهندس العقود"}),
        ("name", {"en": "Contracts QS", "ar": "م/ أحمد"}),
        ("name", {"en": "Sarah, Contracts QS", "ar": "مهندس العقود"}),
        ("style", {"en": "Reads every clause.", "ar": "زي الأستاذ محمد، بيقرا كل بند."}),
    ):
        e = refused(rec, CONTRACTS | {field: pair})
        assert e.text == copy.IDENTITY_NO_PERSON_NAME and e.field.startswith(f"team[0].{field}.")

    [member_id] = identity.propose(rec, [CONTRACTS])
    assert len(member_id) == 32
    card, kind, proposed = identity.project_member(rec, member_id)
    assert (card["title"], kind, proposed) == (CONTRACTS["title"], "temporary", True)


@pytest.mark.parametrize(
    "text",
    [
        "Contracts quantity surveyor",
        "Senior quantity surveyor",
        "مهندس كميات العقود",
        "بيراجع البنود والمباني وشروط الدفعة المقدمة",
        "Checks every rate against the market, e.g. steel.",
    ],
)
def test_a_qs_identity_is_not_taken_for_a_person(text):
    assert not names_a_person(text)


def test_lead_cannot_build_checker(rec):
    """The existing rule, for a proposed member: the check stays blind."""
    for change in (
        {"name": {"en": "Checking QS 2", "ar": "مراجع العقود"}},
        {"title": {"en": "Reviewing quantity surveyor", "ar": "مهندس كميات مراجع"}},
    ):
        assert refused(rec, CONTRACTS | change).text == copy.IDENTITY_NO_CHECKER
    assert refused(rec, {"member_id": identity.CHECKER}).text == copy.IDENTITY_FIXED_MEMBER
    assert refused(rec, CONTRACTS | {"tools": ["delegate"]}).field == "team[0].tools"
    assert refused(rec, {"member_id": "5a" + "0" * 30}).text == copy.IDENTITY_MEMBER_NOT_FOUND


def test_a_new_proposal_replaces_the_one_before_and_keeps_who_joined(rec):
    [first] = identity.propose(rec, [CONTRACTS])
    identity.confirm(rec)
    pricing = CONTRACTS | {
        "name": {"en": "Pricing QS", "ar": "مهندس التسعير"},
        "title": {"en": "Pricing quantity surveyor", "ar": "مهندس كميات التسعير"},
    }
    [_, gone] = identity.propose(rec, [{"member_id": first}, pricing])
    [_, kept] = identity.propose(rec, [{"member_id": first}, pricing])
    assert identity.project_member(rec, gone) is None and identity.project_member(rec, kept)
    assert identity.project_member(rec, first)[2] is False  # joined, not proposed again
    assert refused(rec, CONTRACTS).field == "team[0].name"  # a name the team has already
    identity.withdraw(rec)
    assert identity.project_member(rec, kept) is None and identity.project_member(rec, first)


# The record -----------------------------------------------------------------------------------


def test_record_is_computed(rec, general):
    """The record counts the member's costs and the Checking QS's results on its work."""
    assert identity.record(general, "5a" + "1" * 30) == c.MemberRecord(
        tenders=0, checks_passed=0, checks_total=0, cost_usd="0.00"
    )
    book, member = CostBook(general), "5a" + "2" * 30
    cost(book, member_id=member, project_id="p1", usd="0.40")
    cost(book, member_id=member, project_id="p1", usd="0.15")
    cost(book, member_id=member, project_id="p2", usd=None)  # no known price: not counted
    cost(book, member_id=member, project_id="p3", usd="2.00", equivalent=True)  # subscription
    cost(book, member_id="someone-else", project_id="p4", usd="9.00")
    for version, code in ((1, "C"), (2, "B"), (2, "A")):  # the same version is counted once
        identity.tally(
            general,
            member_id=member,
            project_id="p1",
            deliverable_id="d1",
            version=version,
            code=code,
        )
    assert identity.record(general, member) == c.MemberRecord(
        tenders=3, checks_passed=1, checks_total=2, cost_usd="0.55"
    )
    # rows from before `member_id` count for the fixed members by their role
    cost(book, member_id=None, project_id="p1", usd="1.00", role="lead")
    cost(book, member_id=identity.LEAD, project_id="p5", usd="0.25", role="lead")
    lead = identity.record(general, identity.LEAD)
    assert (lead.tenders, lead.cost_usd) == (2, "1.25")


async def test_a_brief_books_its_costs_to_the_lead(data_dir):
    from qsone.engine.runner import Engine
    from qsone.projects import Projects
    from tests.engine_fakes import scripted, text
    from tests.test_engine_runner import finish, links, started

    registry = Projects(data_dir)
    project = registry.create("مشروع - عينة", "engineer")["id"]
    engine = await started(
        Engine(
            projects=registry,
            data_dir=data_dir,
            connectors=lambda: links(lead=scripted(text("تمام - عينة"))),
        )
    )
    try:
        await finish(engine, await engine.start_brief(project, "سؤال - عينة"))
        with engine.engineer_records().read() as conn:
            found = conn.execute("SELECT DISTINCT member_id FROM ai_costs").fetchall()
        assert found == [(identity.LEAD,)]
        assert identity.record(engine.engineer_records(), identity.LEAD).tenders == 1
        assert identity._model("lead").name == OPUS.name  # the sheet the Brief listed
    finally:
        await engine.shutdown()
        registry.close_all()


# Keeping a member -----------------------------------------------------------------------------


def keeping_ctx(rec, general, answer: str, engine=None):
    host = FakeHost(answers={"keep_member": answer})
    host.engine = engine or SimpleNamespace(engineer_records=lambda: general, projects=None)
    return lead_ctx(rec, host), host


async def test_keep_member_asks_and_says_no(rec, general):
    [member] = identity.propose(rec, [CONTRACTS])
    ctx, host = keeping_ctx(rec, general, "no")
    with pytest.raises(Exception, match="keep_member"):  # proposed only: not in the team yet
        await call("keep_member", {"member_id": member}, ctx)
    identity.confirm(rec)
    with pytest.raises(Denied):
        await call("keep_member", {"member_id": member}, ctx)
    [card] = host.cards
    assert (card.kind, card.options, card.payload) == (
        "keep_member",
        ("yes", "no"),
        {"member_id": member},
    )
    assert card.title == copy.fill(copy.KEEP_MEMBER_TITLE, name=CONTRACTS["name"])
    assert identity.project_member(rec, member)[1] == "temporary"
    assert [m.id for m in identity.permanent(general)] == [identity.LEAD, identity.CHECKER]


async def test_keep_member_is_never_asked_in_a_confidential_project(rec, general):
    [member] = identity.propose(rec, [CONTRACTS])
    identity.confirm(rec)
    with rec.write("engineer") as conn:
        rec.set_meta(conn, "confidential", "1")
    ctx, host = keeping_ctx(rec, general, "yes")
    with pytest.raises(Exception, match="Confidential Project"):
        await call("keep_member", {"member_id": member}, ctx)
    assert host.cards == [] and identity.project_member(rec, member)[1] == "temporary"


async def test_keep_member_makes_permanent(data_dir):
    """After the engineer's yes the member is in a second project's choices with its record."""
    app = create_app(SECRET, data_dir=data_dir)
    client = TestClient(app)
    registry, engine = app.state.projects, app.state.engine
    first, second = (registry.create(f"عطاء {n} - عينة", "engineer")["id"] for n in (1, 2))
    rec, general = registry.get(first), engine.engineer_records()
    [member] = identity.propose(rec, [CONTRACTS])
    identity.confirm(rec)
    cost(CostBook(general), member_id=member, project_id=first, usd="1.37")

    ctx, _ = keeping_ctx(rec, general, "yes", engine)
    kept = json.loads(await call("keep_member", {"member_id": member}, ctx))
    assert kept == {"member_id": member, "kind": "permanent"}

    team = client.get("/team/members", headers=AUTH)
    assert team.status_code == 200 and team.headers["cache-control"] == "no-store"
    members = c.Members.model_validate_json(team.text, strict=True).members
    assert [(m.id, m.kind) for m in members] == [
        (identity.LEAD, "fixed"),
        (identity.CHECKER, "fixed"),
        (member, "permanent"),
    ]
    assert members[2].record == c.MemberRecord(
        tenders=1, checks_passed=0, checks_total=0, cost_usd="1.37"
    )

    identity.propose(registry.get(second), [{"member_id": member}], engineer=general)
    there = client.get(f"/projects/{second}/members", headers=AUTH)
    found = c.TeamMembers.model_validate_json(there.text, strict=True).members[2]
    assert (found.id, found.kind, found.proposed, found.state) == (
        member,
        "permanent",
        True,
        "idle",
    )
    assert found.record == members[2].record and found.title == c.Text(**CONTRACTS["title"])
    registry.close_all()


# The routes -----------------------------------------------------------------------------------


def test_a_tender_team_before_a_plan_is_the_two_fixed_members(data_dir):
    app = create_app(SECRET, data_dir=data_dir)
    client = TestClient(app)
    project = app.state.projects.create("عطاء - عينة", "engineer")["id"]
    answer = client.get(f"/projects/{project}/members", headers=AUTH)
    members = c.TeamMembers.model_validate_json(answer.text, strict=True).members
    lead, checker = members
    assert (lead.id, lead.role, lead.kind, lead.name) == (
        "lead-qs",
        "lead",
        "fixed",
        c.Text(**copy.LEAD_NAME),
    )
    assert (checker.id, checker.role, checker.state, checker.proposed) == (
        "checking-qs",
        "checker",
        "idle",
        False,
    )
    assert lead.model is None  # no sheet listed yet
    assert "files_read" in [t.name for t in lead.tools] and "open_tools" not in [
        t.name for t in lead.tools
    ]
    assert all(t.title.en and t.title.ar for m in members for t in m.tools)

    identity.remember_sheet(SAMPLE_SHEET)
    again = client.get(f"/projects/{project}/members", headers=AUTH).json()
    assert again["members"][0]["model"] == {
        "name": OPUS.name,
        "provider": OPUS.provider,
        "on_device": False,
    }

    for path, status in (
        (f"/projects/{'5a' + '0' * 30}/members", 404),
        ("/projects/nope/members", 404),
    ):
        refusal = client.get(path, headers=AUTH)
        assert refusal.status_code == status
        c.Refusal.model_validate_json(refusal.text, strict=True)
    app.state.projects.close_all()


# Member events --------------------------------------------------------------------------------


async def test_member_events_at_most_once_a_second_and_the_last_one_sent(monkeypatch):
    sent: list[dict] = []
    monkeypatch.setattr(activity, "publish", lambda channel, event: sent.append(event))
    now = [0.0]
    throttle = identity_live.Throttle(clock=lambda: now[0], gap=0.05)
    for state in ("one", "two", "three"):
        throttle.send("p1", "m1", lambda state=state: {"state": state})
    throttle.send("p1", "m2", lambda: {"state": "other"})
    assert sent == [{"state": "one"}, {"state": "other"}]
    now[0] = 0.05
    await asyncio.sleep(0.1)
    assert sent == [{"state": "one"}, {"state": "other"}, {"state": "three"}]
    throttle.send("p1", "m1", lambda: None)  # no event to send: nothing is published
    assert len(sent) == 3


async def test_each_checked_version_counts_in_its_makers_record(rec, general):
    """Code C then B on two versions of the Lead's Deliverable: two checks, one passed."""
    from qsone.engine.types import Review
    from tests.engine_fakes import DEEPSEEK
    from tests.team_samples import TeamFakeHost, sample_ledger
    from tests.test_engine_checker import deliverable

    host = TeamFakeHost(answers={"budget": "yes"})
    host.engine = SimpleNamespace(engineer_records=lambda: general)
    ctx = lead_ctx(rec, host)
    codes = iter("CB")

    async def checker(packet, maker):
        return Review(next(codes), (), DEEPSEEK.choice, False, 0)

    host.checker = checker
    ids = await sample_ledger(ctx)
    first = await deliverable(ctx, ids)
    await call("submit_for_check", {"deliverable_id": first}, ctx)
    second = await deliverable(ctx, ids, replaces=first, body="Revised - sample.")
    await call("submit_for_check", {"deliverable_id": second}, ctx)
    found = identity.record(general, identity.LEAD)
    assert (found.checks_passed, found.checks_total) == (1, 2)
