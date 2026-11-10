"""A kept (permanent) member in a later tender's plan (spec §4: "available to every later
tender"): the Lead brings it in by its `member_id`, the plan shows its card and its record, a
new card with its name is refused with its id, and keeping it again adds no second row.
Scripted tools only, never a real AI. Synthetic «عينة» data only."""

import json
import uuid
from dataclasses import replace
from types import SimpleNamespace

import pytest

from qsone import copy
from qsone.engine import identity
from qsone.engine.plan import members, store
from qsone.engine.store import CostBook
from qsone.engine.tools import call
from qsone.records.project import Records, RecordsError
from tests.test_identity import cost
from tests.test_tender_plan import draft, due_in, lead_ctx, member, plan_args


@pytest.fixture
def later(data_dir):
    """A second sample tender."""
    found = Records.create(
        data_dir / "projects" / uuid.uuid4().hex, name="عطاء 2 - عينة", actor="engineer"
    )
    yield found
    found.close()


def kept_pricing(rec, general) -> str:
    """Tender A's Pricing QS, approved, with a cost, then kept; its id."""
    due_in(rec)
    plan = store.propose(rec, replace(draft(rec), engineer=general))
    store.approve(rec, version=1)
    pricing = plan.team[2].id
    cost(CostBook(general), member_id=pricing, project_id=rec.id, usd="1.37")
    identity.keep(general, rec, pricing)
    return pricing


def test_a_kept_member_joins_a_later_tender_by_its_id(rec, later, general):
    pricing = kept_pricing(rec, general)
    due_in(later)
    team = [{"ref": "pricing-qs", "member_id": pricing}]
    plan = store.propose(later, replace(draft(later, team=team), engineer=general))
    brought = plan.team[2]
    assert (brought.id, brought.kind, brought.name.en) == (
        pricing,
        "permanent",
        "Pricing QS (sample)",
    )
    assert [t.name for t in brought.tools] == ["prices_lookup"]  # its own card's tools
    assert (brought.record.tenders, brought.record.cost_usd) == (1, "1.37")  # its record goes on
    assert plan.stages[1].owner_member_id == pricing
    store.approve(later, version=1)
    identity.keep(general, later, pricing)  # kept again: still one row
    kept = [m for m in identity.permanent(general) if m.kind == "permanent"]
    assert [m.id for m in kept] == [pricing]


def test_a_new_card_with_a_kept_members_name_is_refused_with_its_id(rec, later, general):
    pricing = kept_pricing(rec, general)
    due_in(later)
    with pytest.raises(RecordsError) as e:
        store.propose(later, replace(draft(later), engineer=general))
    assert (e.value.status, e.value.field) == (422, "team[0].name")
    name = {"en": "Pricing QS (sample)", "ar": "Pricing QS - عينة"}
    assert e.value.text == copy.fill(copy.PLAN_MEMBER_PERMANENT, n=1, name=name, member_id=pricing)
    assert store.current(later) is None


def test_a_new_member_needs_its_whole_card(later, general):
    due_in(later)
    with pytest.raises(RecordsError) as e:
        store.propose(later, replace(draft(later, team=[member(style=None)]), engineer=general))
    assert e.value.field == "team[0].style"


async def test_the_lead_brings_a_kept_member_in_with_the_plan_tool(rec, later, general):
    pricing = kept_pricing(rec, general)
    due_in(later)
    ctx = lead_ctx(later)
    ctx.host.engine = SimpleNamespace(engineer_records=lambda: general)
    args = plan_args(later, team=[{"ref": "pricing-qs", "member_id": pricing}])
    done = json.loads(await call("tender_plan_write", args, ctx))
    assert done["proposed"] is True
    assert store.current(later).team[2].id == pricing


def test_the_plan_request_lists_the_kept_members(rec, general):
    pricing = kept_pricing(rec, general)
    line = members.permanent_line(general)
    assert pricing in line and "Pricing QS (sample)" in line
    assert members.permanent_line(None) == ""
