"""A specialist the Lead builds as one of the tender's joined members works with that member's
approved card: its tools and its tier, whatever the Lead asks (spec §4: "each member has only
its own tools"). Synthetic «عينة» data only; no test calls a real AI."""

import json

import pytest

from qsone.engine import identity
from qsone.engine.team import specialists
from qsone.engine.tools import call
from tests.test_engine_team import SPECIALIST, ctx, host, planned  # noqa: F401 - fixtures
from tests.test_identity import CONTRACTS

pytestmark = pytest.mark.anyio


async def test_a_joined_member_has_only_its_cards_tools(ctx):  # noqa: F811
    [member] = identity.propose(ctx.rec, [CONTRACTS])
    identity.confirm(ctx.rec)
    await planned(ctx)
    asked = SPECIALIST | {
        "name_en": "Contracts QS",
        "name_ar": "مهندس العقود",
        "tools": ["search_records", "record_number", "files_read"],  # two not on its card
        "tier": "quick",
    }
    built = json.loads(await call("build_specialist", asked, ctx))
    [spec] = specialists(ctx.store, ctx.brief_id)
    assert spec.id == member == built["specialist_id"]
    assert spec.tools == tuple(CONTRACTS["tools"]) and spec.tier == "specialist"
    assert built["tools"] == CONTRACTS["tools"] and "card" in built["note"]


async def test_a_specialist_new_to_the_brief_has_the_tools_asked(ctx):  # noqa: F811
    await planned(ctx)
    built = json.loads(await call("build_specialist", SPECIALIST, ctx))
    assert built["tools"] == SPECIALIST["tools"] and "note" not in built
