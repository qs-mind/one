"""The team a tender plan proposes is the tender's members (C2 with C5, joined by C11): the plan's
member ids are the ones route 15 lists, kept from version to version; approving the plan or a
change makes them join; a rejected change's new member goes. Synthetic «عينة» data only."""

from qsone.engine import identity
from qsone.engine.plan import store
from tests.test_tender_plan import draft, due_in, member, pair, stage

CONTRACTS = member(
    ref="contracts-qs",
    name=pair("Contracts QS"),
    title={"en": "Contracts Quantity Surveyor (sample)", "ar": "مهندس كميات العقود (عينة)"},
    speciality={"en": "Contract conditions agent (sample)", "ar": "وكيل شروط العقد (عينة)"},
)


def rows(rec) -> list[tuple[str, bool]]:
    """(id, only proposed) of the tender's members."""
    return [(i, proposed) for i, _, _, proposed in identity._rows(rec)]


def test_the_plans_team_is_the_tenders_members(rec):
    due_in(rec)
    first = store.propose(rec, draft(rec))
    pricing = first.team[2].id
    assert rows(rec) == [(pricing, True)]  # proposed, not joined
    renamed = member(style=pair("Names the source of each rate"))
    again = store.propose(rec, draft(rec, team=[renamed]))
    assert again.team[2].id == pricing and rows(rec) == [(pricing, True)]  # the same member
    assert identity.project_member(rec, pricing)[0]["style"] == pair(
        "Names the source of each rate"
    )  # with the card proposed last

    approved = store.approve(rec, version=2)
    assert approved.status == "approved" and rows(rec) == [(pricing, False)]  # it joined

    stages = [stage(rec, 0, id=s.id) for s in approved.stages]
    rejected = store.suggest(rec, draft(rec, stages=stages, team=[member(), CONTRACTS]), "عينة")
    contracts = rejected.change.team[3].id
    assert rejected.change.team[2].id == pricing  # who joined keeps its id
    assert rows(rec) == [(pricing, False), (contracts, True)]
    store.answer_change(rec, rejected.change.id, False)
    assert rows(rec) == [(pricing, False)]  # the member it proposed goes

    taken = store.suggest(rec, draft(rec, stages=stages, team=[member(), CONTRACTS]), "عينة")
    store.answer_change(rec, taken.change.id, True)
    assert [p for _, p in rows(rec)] == [False, False]  # accepted: it joins
    assert [m.id for m in store.current(rec).team][2:] == [i for i, _ in rows(rec)]
