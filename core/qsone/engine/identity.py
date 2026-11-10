"""The team's identities (Phase 1, C5): who is in a tender's team, and the record of each member's
real work in ONE.

- The two fixed members, `lead-qs` and `checking-qs`, are in every team. Every other member is
  proposed with a plan or a change (`propose`, which the plan tool calls with its `team`), joins
  when the engineer approves it (`confirm`), and starts temporary. Kept with the engineer's yes
  (the `keep_member` tool), it is permanent: its card is copied to Engineer Records and any later
  tender may bring it in by its id.
- A project file holds its tender's members (`project_members`); Engineer Records holds the
  permanent ones (`members`), the cost book and the checks tally.
- A run's member is its spec's id: `lead-qs`, `checking-qs`, or the member's id when the Lead
  builds a specialist with a joined member's name (`joined_named`, which `build_specialist`
  asks). The cost book, the room and the live status record it under that id.
- `record` counts from that real work: the projects with costs, the paid cost that is known (the
  Claude subscription's equivalent and unpriced use left out) and the Checking QS's results on
  the member's Deliverables. A new member has zeros.
- `Member.model` comes from the Model Data Sheet the engine listed last (`remember_sheet`), so no
  route here calls a provider."""

import json
from decimal import Decimal
from uuid import uuid4

from qsone import copy
from qsone import phase1_contract as c
from qsone.engine import agents, roles
from qsone.engine.costs import usd_text
from qsone.engine.team import MAX_SPECIALISTS
from qsone.engine.team.identity_card import MemberDraft, check_identity
from qsone.engine.tools import REGISTRY
from qsone.engine.types import ModelCard
from qsone.records.project import Records, RecordsError

LEAD, CHECKER = "lead-qs", "checking-qs"
FIXED_ROLES = {LEAD: "lead", CHECKER: "checker"}  # ai_costs.role of their rows from before
ACTOR = "engine"
_HIDDEN_TOOLS = ("open_tools",)  # machinery, not something a member is given

# The Model Data Sheet as the engine last listed it. A listing that fails changes nothing.
_sheet: tuple[ModelCard, ...] = ()


def remember_sheet(sheet) -> None:
    global _sheet
    if sheet:
        _sheet = tuple(sheet)


def forget_sheet() -> None:
    """For tests."""
    global _sheet
    _sheet = ()


def _model(tier: str) -> c.MemberModel | None:
    if not _sheet:
        return None
    chosen = roles.chosen(list(_sheet))
    choice = chosen.get(tier) or chosen.get("specialist")
    card = next((card for card in _sheet if card.choice == choice), None)
    if card is None:
        return None
    return c.MemberModel(name=card.name, provider=card.provider, on_device=card.on_device)


def _tools(names) -> list[c.MemberTool]:
    return [
        c.MemberTool(name=name, title=copy.TOOL_TITLES.get(name, {"en": name, "ar": name}))
        for name in names
        if name in REGISTRY and name not in _HIDDEN_TOOLS
    ]


def _fixed() -> list[tuple[str, str, dict]]:
    """(id, role, card) of the Lead QS and the Checking QS."""
    lead, checker = agents.lead_spec(), agents.checker_spec()
    return [
        (
            LEAD,
            "lead",
            {
                "name": copy.LEAD_NAME,
                "title": copy.LEAD_TITLE,
                "speciality": copy.LEAD_SPECIALITY,
                "style": copy.LEAD_STYLE,
                "tools": list(lead.tools),
                "tier": "lead",
            },
        ),
        (
            CHECKER,
            "checker",
            {
                "name": copy.CHECKER_NAME,
                "title": copy.CHECKER_TITLE,
                "speciality": copy.CHECKER_SPECIALITY,
                "style": copy.CHECKER_STYLE,
                "tools": list(checker.tools),
                "tier": "checker",
            },
        ),
    ]


def _member(engineer: Records, member_id: str, role: str, kind: str, card: dict) -> c.Member:
    return c.Member(
        id=member_id,
        role=role,
        kind=kind,
        name=card["name"],
        title=card["title"],
        speciality=card["speciality"],
        style=card["style"],
        model=_model(card["tier"]),
        tools=_tools(card["tools"]),
        record=record(engineer, member_id),
    )


# The record --------------------------------------------------------------------------------------


def record(engineer: Records, member_id: str) -> c.MemberRecord:
    """Counted from Engineer Records: zeros for a member with no work yet."""
    where, args = "member_id = ?", [member_id]
    if member_id in FIXED_ROLES:
        where = "(member_id = ? OR (member_id IS NULL AND role = ?))"
        args.append(FIXED_ROLES[member_id])
    with engineer.read() as conn:
        costs = conn.execute(
            f"SELECT usd, equivalent, project_id FROM ai_costs WHERE {where}", args
        ).fetchall()
        total, passed = conn.execute(
            "SELECT count(*), coalesce(sum(code IN ('A', 'B')), 0) FROM member_checks"
            " WHERE member_id = ?",
            (member_id,),
        ).fetchone()
    paid = sum(
        (Decimal(usd) for usd, equivalent, _ in costs if usd is not None and not equivalent),
        Decimal(0),
    )
    return c.MemberRecord(
        tenders=len({project for *_, project in costs if project is not None}),
        checks_passed=passed,
        checks_total=total,
        cost_usd=usd_text(paid),
    )


def tally(
    engineer: Records,
    *,
    member_id: str,
    project_id: str | None,
    deliverable_id: str,
    version: int,
    code: str,
) -> None:
    """One Checking QS result on a version of the member's Deliverable; the same version
    checked again is counted once."""
    with engineer.write(ACTOR) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO member_checks(member_id, project_id, deliverable_id, version,"
            " code, at) VALUES (?, ?, ?, ?, ?, ?)",
            (member_id, project_id, deliverable_id, version, code, engineer.clock()),
        )


def engineer_of(host) -> Records | None:
    """The Engineer Records file of a Brief's host (its engine's), or None for a host with no
    engine (a test's) or when the file does not open."""
    engine = getattr(host, "engine", None)
    if engine is None:
        return None
    try:
        return engine.engineer_records()
    except RecordsError:
        return None


# A tender's team ----------------------------------------------------------------------------------


def _rows(rec: Records) -> list[tuple[str, dict, str, bool]]:
    """(id, card, kind, proposed) of the tender's members, as they joined."""
    with rec.read() as conn:
        rows = conn.execute(
            "SELECT id, card, kind, proposed FROM project_members ORDER BY joined_at, rowid"
        ).fetchall()
    return [(i, json.loads(card), kind, bool(proposed)) for i, card, kind, proposed in rows]


def project_member(rec: Records, member_id: str) -> tuple[dict, str, bool] | None:
    """(card, kind, proposed) of one member of the tender, or None."""
    found = [row for row in _rows(rec) if row[0] == member_id]
    return found[0][1:] if found else None


def joined_named(rec: Records, name: dict) -> str | None:
    """The id of the tender's joined member with this short name (English in any case, or
    Arabic; the team's names are unique), or None."""
    keys = {name["en"].casefold(), name["ar"]}
    for member_id, card, _, proposed in _rows(rec):
        if not proposed and keys & {card["name"]["en"].casefold(), card["name"]["ar"]}:
            return member_id
    return None


def _permanent_card(engineer: Records, member_id: str) -> dict | None:
    with engineer.read() as conn:
        row = conn.execute("SELECT card FROM members WHERE id = ?", (member_id,)).fetchone()
    return None if row is None else json.loads(row[0])


def members(rec: Records, engineer: Records) -> list[tuple[c.Member, bool]]:
    """The tender's team and whether each is only proposed: the Lead, the Checking QS, then the
    others as they joined."""
    found = [(_member(engineer, i, role, "fixed", card), False) for i, role, card in _fixed()]
    for member_id, card, kind, proposed in _rows(rec):
        found.append((_member(engineer, member_id, "specialist", kind, card), proposed))
    return found


def team(rec: Records, engineer: Records) -> list[c.Member]:
    """The team a plan shows: the fixed members and those proposed or working."""
    return [member for member, _ in members(rec, engineer)]


def permanent(engineer: Records) -> list[c.Member]:
    """Settings → Team: the Lead, the Checking QS, then the permanent members, oldest first."""
    found = [_member(engineer, i, role, "fixed", card) for i, role, card in _fixed()]
    with engineer.read() as conn:
        rows = conn.execute("SELECT id, card FROM members ORDER BY kept_at, rowid").fetchall()
    found += [_member(engineer, i, "specialist", "permanent", json.loads(card)) for i, card in rows]
    return found


def _names_unique(cards: list[tuple[str, dict]]) -> None:
    seen: set[str] = set()
    for at, card in cards:
        keys = {card["name"]["en"].casefold(), card["name"]["ar"]}
        if keys & seen:
            raise RecordsError(
                copy.fill(copy.IDENTITY_NAME_TAKEN, field=f"{at}.name"),
                status=422,
                field=f"{at}.name",
            )
        seen |= keys


def propose(
    rec: Records, drafts: list[MemberDraft | dict], *, engineer: Records | None = None
) -> list[str]:
    """Stores the members a plan or a change proposes (its whole `team`, the fixed members left
    out) and gives their ids, in order. Members who already joined stay; members proposed
    before and not now are dropped. A draft with `member_id` brings in a member of this team
    (one only proposed takes the draft's card) or a permanent one (`engineer` is needed for
    that). Raises `RecordsError` (422) naming the field, e.g. "team[0].title.ar"."""
    drafts = [d if isinstance(d, MemberDraft) else MemberDraft.model_validate(d) for d in drafts]
    if len(drafts) > MAX_SPECIALISTS:
        text = copy.fill(copy.IDENTITY_TOO_MANY, limit=MAX_SPECIALISTS)
        raise RecordsError(text, status=422, field="team")
    current = {i: (card, kind, proposed) for i, card, kind, proposed in _rows(rec)}
    chosen: list[tuple[str, dict, str]] = []
    for n, draft in enumerate(drafts):
        at = f"team[{n}]"
        if draft.member_id is None:
            chosen.append((uuid4().hex, check_identity(draft, at), "temporary"))
            continue
        if draft.member_id in FIXED_ROLES:
            raise RecordsError(copy.IDENTITY_FIXED_MEMBER, status=422, field=f"{at}.member_id")
        if draft.member_id in current:
            card, kind, proposed = current[draft.member_id]
            if proposed and draft.name is not None:  # proposed again: the same id, its new card
                card = check_identity(draft, at)
            chosen.append((draft.member_id, card, kind))
            continue
        card = None if engineer is None else _permanent_card(engineer, draft.member_id)
        if card is None:
            raise RecordsError(copy.IDENTITY_MEMBER_NOT_FOUND, status=422, field=f"{at}.member_id")
        chosen.append((draft.member_id, card, "permanent"))
    ids = [member_id for member_id, _, _ in chosen]
    staying = [
        ("team", card)
        for i, (card, _, proposed) in current.items()
        if not proposed and i not in ids
    ]
    fixed = [("team", card) for _, _, card in _fixed()]
    _names_unique([*fixed, *staying, *((f"team[{n}]", ch[1]) for n, ch in enumerate(chosen))])
    with rec.write(ACTOR) as conn:
        dropped = [i for i, (_, _, proposed) in current.items() if proposed and i not in ids]
        conn.executemany("DELETE FROM project_members WHERE id = ?", [(i,) for i in dropped])
        for member_id, card, kind in chosen:
            if member_id in current:
                conn.execute(
                    "UPDATE project_members SET card = ? WHERE id = ? AND proposed = 1",
                    (json.dumps(card, ensure_ascii=False), member_id),
                )
                continue
            conn.execute(
                "INSERT INTO project_members(id, card, kind, proposed, joined_at)"
                " VALUES (?, ?, ?, 1, ?)",
                (member_id, json.dumps(card, ensure_ascii=False), kind, rec.clock()),
            )
    return ids


def confirm(rec: Records) -> None:
    """The engineer approved the plan or the change: its proposed members join."""
    with rec.write(ACTOR) as conn:
        conn.execute("UPDATE project_members SET proposed = 0 WHERE proposed = 1")


def withdraw(rec: Records) -> None:
    """The change was rejected: the members it proposed go."""
    with rec.write(ACTOR) as conn:
        conn.execute("DELETE FROM project_members WHERE proposed = 1")


def keep(engineer: Records, rec: Records, member_id: str) -> None:
    """After the engineer's yes: the member is permanent, here and for every later tender.
    Safe to repeat."""
    found = project_member(rec, member_id)
    if found is None:
        raise RecordsError(copy.IDENTITY_MEMBER_NOT_FOUND, status=404, field="member_id")
    card = json.dumps(found[0], ensure_ascii=False)
    with engineer.write("engineer") as conn:
        conn.execute(
            "INSERT OR IGNORE INTO members(id, card, kept_at, kept_from) VALUES (?, ?, ?, ?)",
            (member_id, card, engineer.clock(), rec.id),
        )
    with rec.write("engineer") as conn:
        conn.execute("UPDATE project_members SET kind = 'permanent' WHERE id = ?", (member_id,))
