"""The team a plan proposes: the two fixed members and the ones the Lead builds for the tender.

Here only the shape of a proposed member is checked (`model.check`). The members' own rules (a
QS title, no personal name) come with the identities job, through `identity_check`, the one place
that calls it."""

from importlib.util import find_spec

from qsone import copy
from qsone.engine.plan.model import CHECKER, LEAD, MemberIn
from qsone.records.project import Records

IDENTITY = "qsone.engine.identity"


def identity_check(project: Records, team: list[MemberIn]) -> None:
    """The identities job's checks of the proposed members (`identity.propose(project, drafts)`,
    raising `RecordsError`), once that module exists; nothing before."""
    if find_spec(IDENTITY) is None:
        return
    from importlib import import_module

    import_module(IDENTITY).propose(project, [m.model_dump(exclude={"ref"}) for m in team])


def member_tools() -> set[str]:
    """The tools a proposed member may be given: those of a specialist."""
    from qsone.engine.team import specialist_tools

    return set(specialist_tools())


def _tools(names) -> list[dict]:
    return [{"name": n, "title": copy.tool_step(n)} for n in names]


def _record() -> dict:
    return {"tenders": 0, "checks_passed": 0, "checks_total": 0, "cost_usd": "0.00"}


def _fixed() -> list[dict]:
    from qsone.engine import agents
    from qsone.engine.tools import REGISTRY

    lead, checker = agents.lead_spec(), agents.checker_spec()
    found = []
    for spec, member_id, role, speciality, style in (
        (lead, LEAD, "lead", copy.PLAN_LEAD_SPECIALITY, copy.PLAN_LEAD_STYLE),
        (checker, CHECKER, "checker", copy.PLAN_CHECKER_SPECIALITY, copy.PLAN_CHECKER_STYLE),
    ):
        found.append(
            {
                "id": member_id,
                "role": role,
                "kind": "fixed",
                "name": dict(spec.name),
                "title": dict(spec.name),
                "speciality": speciality,
                "style": style,
                "model": None,
                "tools": _tools(t for t in spec.tools if t in REGISTRY),
                "record": _record(),
            }
        )
    return found


def members(team: list[MemberIn], refs: dict[str, str]) -> list[dict]:
    """The plan's team: the Lead, the Checking QS, then the proposed members in order. A new
    member is temporary, with no model listed yet and a record of zeros."""
    proposed = [
        {
            "id": refs[m.ref],
            "role": "specialist",
            "kind": "temporary",
            "name": {"en": m.name.en, "ar": m.name.ar},
            "title": {"en": m.title.en, "ar": m.title.ar},
            "speciality": {"en": m.speciality.en, "ar": m.speciality.ar},
            "style": {"en": m.style.en, "ar": m.style.ar},
            "model": None,
            "tools": _tools(m.tools),
            "record": _record(),
        }
        for m in team
    ]
    return [*_fixed(), *proposed]
