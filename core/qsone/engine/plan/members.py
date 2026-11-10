"""The team a plan proposes: the two fixed members and the ones the Lead builds for the tender.

Here only the shape of a proposed member is checked (`model.check`). The members' own rules (a
QS title, no personal name) come with the identities job, through `identity_check`, the one place
that calls it."""

from importlib import import_module
from importlib.util import find_spec
from uuid import uuid4

from qsone import copy
from qsone.engine.plan.model import CHECKER, LEAD, MemberIn
from qsone.records.project import Records, RecordsError

IDENTITY = "qsone.engine.identity"


def identity_check(
    project: Records, team: list[MemberIn], refs: dict[str, str], engineer: Records | None = None
) -> list[str]:
    """The identities job's checks of the proposed members (`identity.propose`, raising
    `RecordsError`), once that module exists, and each member's id in order: the one the
    tender's members are stored under, so the plan's team and route 15 name the same ids. A
    member `refs` already holds keeps its id: proposed again with its new card, or, once it
    joined, as it is. A member with `member_id` is a permanent one from `engineer`; a new card
    with a permanent member's name is refused with that member's id."""
    if find_spec(IDENTITY) is None:
        return [refs.get(m.ref) or uuid4().hex for m in team]
    identity = import_module(IDENTITY)
    kept = _kept(identity, engineer)
    drafts = []
    for n, m in enumerate(team):
        draft, known = m.model_dump(exclude={"ref"}), refs.get(m.ref)
        if m.member_id is None and known is not None:
            if identity.project_member(project, known) is not None:
                draft["member_id"] = known
        if draft["member_id"] is None and m.name is not None:
            _not_kept(kept, m.name, n)
        drafts.append(draft)
    return identity.propose(project, drafts, engineer=engineer)


def _kept(identity, engineer: Records | None) -> list:
    """The permanent members in Engineer Records (Settings → Team), oldest first."""
    if engineer is None:
        return []
    return [m for m in identity.permanent(engineer) if m.kind == "permanent"]


def _not_kept(kept: list, name, n: int) -> None:
    keys = {name.en.casefold(), name.ar}
    for found in kept:
        if keys & {found.name.en.casefold(), found.name.ar}:
            text = copy.fill(
                copy.PLAN_MEMBER_PERMANENT,
                n=n + 1,
                name=found.name.model_dump(),
                member_id=found.id,
            )
            raise RecordsError(text, status=422, field=f"team[{n}].name")


def permanent_line(engineer: Records | None) -> str:
    """For the Lead that writes a plan: the permanent members it may bring in by member_id."""
    if engineer is None or find_spec(IDENTITY) is None:
        return ""
    kept = _kept(import_module(IDENTITY), engineer)
    if not kept:
        return ""
    listed = "; ".join(
        f"{m.id}: {m.name.en} / {m.name.ar}, {m.title.en}, tools "
        + ", ".join(t.name for t in m.tools)
        for m in kept
    )
    return (
        "The engineer's permanent members, kept from earlier tenders. To bring one into the team, "
        f"give its member_id and a ref, without a card: {listed}."
    )


def answered(project: Records, *, accepted: bool) -> None:
    """Inside the engineer's write on the plan or a change: its proposed members join the
    tender, or go when the change is rejected."""
    if find_spec(IDENTITY) is not None:
        identity = import_module(IDENTITY)
        (identity.confirm if accepted else identity.withdraw)(project)


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


def members(
    project: Records, team: list[MemberIn], refs: dict[str, str], engineer: Records | None = None
) -> list[dict]:
    """The plan's team: the Lead, the Checking QS, then the proposed members in order, each with
    the card it is stored under (a permanent member's own) and its record (zeros for a new
    one); no model is listed yet."""
    identity = import_module(IDENTITY) if find_spec(IDENTITY) is not None else None
    proposed = []
    for m in team:
        member_id = refs[m.ref]
        stored = None if identity is None else identity.project_member(project, member_id)
        card, kind = (stored[0], stored[1]) if stored else (m.model_dump(), "temporary")
        record = _record()
        if engineer is not None and identity is not None:
            record = identity.record(engineer, member_id).model_dump(mode="json")
        proposed.append(
            {
                "id": member_id,
                "role": "specialist",
                "kind": kind,
                **{k: dict(card[k]) for k in ("name", "title", "speciality", "style")},
                "model": None,
                "tools": _tools(card["tools"]),
                "record": record,
            }
        )
    return [*_fixed(), *proposed]
