"""What each team tool does: the function its `Tool` runs, with the checks it makes first.

Every id the team makes (a card, a specialist, a message, a Deliverable draft) comes from this
module's `uuid4`, so one patch of `handlers.uuid4` fixes them all: every caller of it stays here."""

import asyncio
import re
from dataclasses import replace
from uuid import uuid4

from qsone import copy, settings
from qsone.clientfile import imported
from qsone.deliverables import review as deliverable_review
from qsone.deliverables import tools as outputs
from qsone.engine import agents, checker, desks, numbers_guard, truth
from qsone.engine.costs import brief_budget, caps, usd_text
from qsone.engine.store import Store
from qsone.engine.tools import REGISTRY, Denied, ModelRetry, ToolContext
from qsone.engine.types import (
    AgentSpec,
    Card,
    CheckPacket,
    DeliverableDraft,
    Review,
    Reviewed,
    Role,
    TeamMessage,
    Text,
)
from qsone.records.project import RecordsError

from .common import (
    MAX_SPECIALISTS,
    PLANNED,
    READY,
    SPECIALIST_TEAM_TOOLS,
    TEAM_TOOLS,
    _ask,
    _join,
    _json,
    _setup,
)
from .schemas import (
    CheckArgs,
    DelegateArgs,
    DeliverableArgs,
    Kit,
    MessageArgs,
    PlanArgs,
    SaveDeskArgs,
    SpecialistArgs,
    UseDeskArgs,
)
from .stored import _maker, _specialist, _unsourced, specialists

# plan_brief -----------------------------------------------------------------------------------


async def _plan_brief(ctx: ToolContext, args: PlanArgs) -> str:
    setup = _setup(ctx)
    items = [{"tier": s.tier, "requests": s.requests} for s in args.steps]
    items.append({"tier": "lead", "requests": len(args.steps) + 1})  # a hand-over each, an end
    items.append({"tier": "checker", "requests": len(args.deliverables)})
    budget = brief_budget(
        items, list(setup.sheet), setup.roles, setup.measured, setup.lead_measured
    )
    approved = getattr(ctx.host, "budget_approved", False)  # said yes once this Brief
    if not approved and (budget.usd is None or budget.usd > caps().budget_above):
        detail = (
            copy.fill(copy.BUDGET_UNKNOWN, minutes=budget.minutes)
            if budget.usd is None
            else copy.fill(
                copy.BUDGET_ASK,
                usd=usd_text(budget.usd),
                minutes=budget.minutes,
                basis=budget.basis,
            )
        )
        card = Card(uuid4().hex, "budget", copy.BUDGET_TITLE, detail, ("yes", "no"))
        if await _ask(ctx, card) != "yes":
            raise Denied("plan_brief")
        if hasattr(ctx.host, "budget_approved"):  # the Spending Caps ask no budget card again
            ctx.host.budget_approved = True
    result = _json({"planned": True, "steps": len(args.steps), "deliverables": args.deliverables})
    ctx.store.remember_write(ctx.brief_id, PLANNED, result)
    return result


# build_specialist -----------------------------------------------------------------------------

_CHECKER_EN = re.compile(r"\b(check|review|audit)", re.IGNORECASE)
_CHECKER_AR = ("مراجع", "مدقق", "تدقيق")


def _is_checker(name: Text) -> bool:
    return bool(_CHECKER_EN.search(name["en"])) or any(w in name["ar"] for w in _CHECKER_AR)


def specialist_tools() -> list[str]:
    """Every tool a specialist may be given."""
    return sorted(n for n, t in REGISTRY.items() if "specialist" in t.roles and not t.lead_only)


def _member_of(ctx: ToolContext, name: Text) -> str | None:
    """The tender's joined member this specialist is, by its name, so its work counts as that
    member's (route 15's id); a specialist with any other name is new to this Brief."""
    if ctx.rec is None:
        return None
    from qsone.engine import identity  # it imports the team package

    return identity.joined_named(ctx.rec, name)


def _build(
    ctx: ToolContext,
    *,
    name: Text,
    instructions: str,
    tools: list[str],
    tier: Role,
    desk: str | None = None,
    tool: str = "build_specialist",
) -> AgentSpec:
    if ctx.store.known_write(ctx.brief_id, PLANNED) is None:
        raise ModelRetry(
            f"{tool}: call plan_brief first, with every step and the Deliverables, then build "
            "the specialists it names."
        )
    if _is_checker(name):
        raise ModelRetry(
            f"{tool}: «{name['en']}» / «{name['ar']}» is a checker. The Checking QS is part of "
            "ONE's fixed team and checks every Deliverable on its own; you never build it. Name "
            "the specialist for its own work, e.g. Take-off QS / مهندس الحصر."
        )
    count = agents.words(instructions)
    if count > agents.SPECIALIST_WORDS:
        raise ModelRetry(
            f"{tool}: instructions are {count} words; at most {agents.SPECIALIST_WORDS}: keep "
            "the principles, move steps into the task or a Procedure."
        )
    team_only = [t for t in tools if t in TEAM_TOOLS and t not in SPECIALIST_TEAM_TOOLS]
    if team_only:
        raise ModelRetry(
            f"{tool}: {', '.join(team_only)} only the Lead QS uses. Of the team tools a "
            f"specialist may have {' and '.join(SPECIALIST_TEAM_TOOLS)}."
        )
    allowed = specialist_tools()
    unknown = [t for t in tools if t not in allowed]
    if unknown:
        raise ModelRetry(
            f"{tool}: no tool named {', '.join(unknown)} for a specialist. Choose from: "
            f"{', '.join(allowed)}."
        )
    team = specialists(ctx.store, ctx.brief_id)
    if len(team) >= MAX_SPECIALISTS:
        names = ", ".join(f"{s.id} ({s.name['en']})" for s in team)
        raise ModelRetry(
            f"{tool}: a Brief has at most {MAX_SPECIALISTS} specialists, and this one has "
            f"{len(team)}: {names}. Give the work to one of them with delegate."
        )
    member_id = _member_of(ctx, name)
    if member_id is not None and any(s.id == member_id for s in team):
        raise ModelRetry(
            f"{tool}: {name['en']} is built in this Brief already, as {member_id}. Give it the "
            "work with delegate."
        )
    spec = AgentSpec(
        id=member_id or uuid4().hex,
        name=name,
        role="specialist",
        instructions=instructions,
        tools=tuple(dict.fromkeys(tools)),
        tier=tier,
        desk=desk,
    )
    roles = _setup(ctx).roles
    choice = roles.get(tier) or roles.get("specialist") or ctx.store.run(ctx.run_id)["choice"]
    run_id = ctx.store.new_run(ctx.brief_id, spec, choice, ctx.run_id)
    ctx.store.set_run(run_id, status=READY)
    return spec


async def _build_specialist(ctx: ToolContext, args: SpecialistArgs) -> str:
    spec = _build(
        ctx,
        name={"en": args.name_en, "ar": args.name_ar},
        instructions=args.instructions,
        tools=args.tools,
        tier=args.tier,
    )
    return _json(
        {"specialist_id": spec.id, "name": spec.name, "tier": spec.tier, "tools": spec.tools}
    )


# delegate -------------------------------------------------------------------------------------


def _check_kit(ctx: ToolContext, kit: Kit) -> None:
    if ctx.rec is None or not (kit.file_ids or kit.item_ids):
        return
    with ctx.rec.read() as c:
        files = [
            f
            for f in kit.file_ids
            if not c.execute("SELECT 1 FROM files WHERE id = ?", (f,)).fetchone()
        ]
        items = [
            i
            for i in kit.item_ids
            if not c.execute("SELECT 1 FROM items WHERE id = ? OR code = ?", (i, i)).fetchone()
        ]
    if files or items:
        missing = [*(f"file {f}" for f in files), *(f"item {i}" for i in items)]
        raise ModelRetry(
            f"delegate: the kit names what the project does not have: {', '.join(missing)}. "
            "Use ids from search_records and find_items."
        )


async def _delegate(ctx: ToolContext, args: DelegateArgs) -> str:
    spec = _specialist(ctx, args.specialist_id, "delegate")
    _check_kit(ctx, args.kit)
    return await ctx.host.run_specialist(spec, args.task, args.kit.model_dump())


# send_message ---------------------------------------------------------------------------------


async def _send_message(ctx: ToolContext, args: MessageArgs) -> str:
    if args.to in ("lead", "lead-qs"):
        recipient = copy.ROLE_LEAD
    elif args.to in ("checker", "checking-qs"):
        raise ModelRetry(
            "send_message: the Checking QS takes no messages; it sees only the Deliverables "
            "sent with submit_for_check."
        )
    else:
        recipient = _specialist(ctx, args.to, "send_message").name
    from qsone.engine import room  # the team room (Phase 1, C6)

    message_id = uuid4().hex
    to_id = "lead-qs" if args.to in ("lead", "lead-qs") else args.to
    raised = await room.member_says(ctx, args, message_id, to_id)
    if raised is not None:  # it went up to the engineer, whose answer this is
        return _json(raised)
    message = TeamMessage(
        brief_id=ctx.brief_id,
        id=message_id,
        sender=ctx.agent.name,
        recipient=recipient,
        text=args.text,
    )
    ctx.store.add_team_message(message)
    ctx.host.post(message)
    return _json({"sent": message.id, "to": recipient["en"]})


# make_deliverable -----------------------------------------------------------------------------


def _cells(rows: list[dict]) -> tuple[list[str], list[str]]:
    """Refuses a typed number or a bad cell; gives the number and calculation ids used."""
    for r, row in enumerate(rows, 1):
        for column, cell in row.items():
            if isinstance(cell, dict):
                if len(cell) != 1 or not any(
                    isinstance(cell.get(k), str) for k in ("number_id", "calc_id")
                ):
                    raise ModelRetry(
                        f"make_deliverable: row {r}, «{column}»: a number cell is "
                        '{"number_id": "<id>"} or {"calc_id": "<id>"}.'
                    )
            elif cell is None or isinstance(cell, bool):
                continue
            elif isinstance(cell, str | int | float):
                if numbers_guard.numbers_in(str(cell)):
                    raise ModelRetry(
                        f"make_deliverable: row {r}, «{column}» holds the typed number {cell}. "
                        'A cell holds a ledger number as {"number_id": "<id>"} or a calculation '
                        'as {"calc_id": "<id>"}: record it with record_number, or work it out '
                        "with calculate, then use its id."
                    )
            else:
                raise ModelRetry(
                    f"make_deliverable: row {r}, «{column}»: a cell is text, "
                    '{"number_id": "<id>"} or {"calc_id": "<id>"}.'
                )
    return checker.refs(DeliverableDraft("", "table", "", "", tuple(rows)))


def _check_refs(ctx: ToolContext, args: DeliverableArgs) -> None:
    number_ids, calc_ids = _cells(args.rows)
    wanted = [
        *(("numbers", "number", i) for i in number_ids),
        *(("calculations", "calculation", i) for i in calc_ids),
        *(("sources", "source", i) for i in args.sources),
    ]
    if wanted:
        if ctx.rec is None:
            raise RecordsError(copy.PROJECT_NOT_OPEN)
        with ctx.rec.read() as c:
            missing = [
                f"{what} {i}"
                for table, what, i in wanted
                if c.execute(f"SELECT 1 FROM {table} WHERE id = ?", (i,)).fetchone() is None
            ]
        if missing:
            raise ModelRetry(
                f"make_deliverable: the project has no {', '.join(missing)}. Use the ids "
                "ledger_numbers, calculate and add_source gave."
            )
    if args.replaces is not None:
        try:
            ctx.store.deliverable(args.replaces)
        except LookupError:
            raise ModelRetry(
                f"make_deliverable: no Deliverable has the id «{args.replaces}» to replace."
            ) from None


async def _make_deliverable(ctx: ToolContext, args: DeliverableArgs) -> str:
    _check_refs(ctx, args)
    if ctx.rec is not None:  # no blank for a value; a letter's dates and terms from the files
        kind = "document" if args.kind == "document" else "sheet"
        said = ctx.store.brief(ctx.brief_id)["text"]
        content = [args.title, args.body, list(args.rows)]
        await asyncio.to_thread(outputs.truthful, ctx.rec, "make_deliverable", content, kind, said)
    elif truth.placeholders_in([args.title, args.body]):
        blanks = ", ".join(truth.placeholders_in([args.title, args.body]))
        raise ModelRetry(f"make_deliverable: it has blanks left for values: {blanks}. Fill them.")
    draft = DeliverableDraft(
        id=uuid4().hex,
        kind=args.kind,
        title=args.title,
        body=args.body,
        rows=tuple(args.rows),
        sources=tuple(dict.fromkeys(args.sources)),
        replaces=args.replaces,
        off_desk=True,  # every Desk is Temporary or Draft until Plan 9's Acceptance Tests
    )
    ctx.store.save_deliverable(ctx.brief_id, ctx.run_id, draft)
    out: dict = {"deliverable_id": draft.id, "status": "draft"}
    marked = _unsourced(ctx, draft).unsourced
    if marked:
        out["no_source"] = list(marked)
    return _json(out)


# submit_for_check -----------------------------------------------------------------------------


def _is_settled(store: Store, deliverable_id: str) -> bool:
    """Checked already, or a newer draft replaces it."""
    with store.rec.read() as c:
        return bool(
            c.execute(
                "SELECT EXISTS (SELECT 1 FROM reviews WHERE deliverable_id = ?)"
                " OR EXISTS (SELECT 1 FROM deliverable_drafts WHERE replaces = ?)",
                (deliverable_id, deliverable_id),
            ).fetchone()[0]
        )


def _review_json(draft_id: str, review: Review, c_rounds: int) -> dict:
    out = {
        "deliverable_id": draft_id,
        "code": review.code,
        "comments": list(review.comments),
        "round": review.round,
        "same_provider": review.same_provider,
    }
    if review.code == "C":
        out["rounds_left"] = max(checker.MAX_ROUNDS - c_rounds, 0)
    return out


def _cell_text(cell, packet: CheckPacket) -> str:
    if not isinstance(cell, dict):
        return "" if cell is None else str(cell)
    numbers = {n["id"]: n for n in packet.numbers}
    calcs = {f["calc_id"]: f for f in packet.formulas}
    found = numbers.get(cell.get("number_id")) or calcs.get(cell.get("calc_id"))
    if found is None:
        return "?"
    unit = found.get("unit") or found.get("currency") or ""
    return f"{found['value']} {unit}".strip()


async def _disagreement(
    ctx: ToolContext, draft: DeliverableDraft, earlier: list[Review], maker: dict
) -> str:
    packet = _unsourced(ctx, draft)
    agent = maker["spec"].name
    views: list[Text | str] = [copy.fill(copy.DISAGREEMENT, agent=agent)]
    for r in [r for r in earlier if r.code == "C"][-checker.MAX_ROUNDS :]:
        views.append(copy.fill(copy.DISAGREEMENT_CHECKER, round=r.round, code=r.code))
        views.append("\n".join(f"- {c['about']}: {c['text']}" for c in r.comments))
    rows = "\n".join(
        " | ".join(f"{k}: {_cell_text(v, packet)}" for k, v in row.items()) for row in draft.rows
    )
    sources = "\n".join(f"- {s['title']}" for s in packet.sources)
    views += [copy.fill(copy.DISAGREEMENT_MAKER, agent=agent), draft.title, draft.body, rows]
    views += [sources, copy.DISAGREEMENT_ASK]
    card = Card(uuid4().hex, "disagreement", copy.DISAGREEMENT_TITLE, _join(*views), ("yes", "no"))
    choice = await _ask(ctx, card)
    return _json(
        {
            "deliverable_id": draft.id,
            "code": "C",
            "rounds_left": 0,
            "engineer_decides": True,
            "engineer_chose": "keep it as it is"
            if choice == "yes"
            else "fix it as the Checking QS says; it is not checked again",
        }
    )


async def check_deliverable(ctx: ToolContext, deliverable_id: str) -> str:
    """One check of a Deliverable, under the two-round rule: submit_for_check, and the Brief
    Runner's check of every unchecked Deliverable with numbers when the Brief ends."""
    store = ctx.store
    try:
        draft = store.deliverable(deliverable_id)
    except LookupError:
        found = None
        if ctx.rec is not None:
            found = await asyncio.to_thread(outputs.check_draft, ctx.rec, deliverable_id)
        if found is None:
            raise ModelRetry(
                f"submit_for_check: no Deliverable has the id «{deliverable_id}»; use the id "
                "make_deliverable or deliverable_create gave."
            ) from None
        return await _check_output(ctx, *found)
    earlier = store.reviews(draft.id)
    c_rounds = sum(r.code == "C" for r in earlier)
    maker = _maker(store, draft.id)
    if c_rounds >= checker.MAX_ROUNDS:
        return await _disagreement(ctx, draft, earlier, maker)
    if _is_settled(store, draft.id):
        raise ModelRetry(
            f"submit_for_check: «{draft.id}» is already checked, or a newer draft replaces it. "
            f'To answer the Checking QS, make a revised Deliverable with replaces "{draft.id}" '
            "and submit the new id."
        )
    packet = _unsourced(ctx, draft)
    review = await checker.check(packet, maker["choice"], ctx.host)
    review = replace(review, round=len(earlier) + 1)
    store.save_review(draft.id, review)
    _tally(ctx, maker["spec"].id, draft.id, 1, review.code)  # each draft is a version
    ctx.host.emit(Reviewed(ctx.brief_id, draft.id, review))
    return _json(_review_json(draft.id, review, c_rounds + (review.code == "C")))


async def _check_output(
    ctx: ToolContext, draft: DeliverableDraft, version_n: int, untraced: list[str]
) -> str:
    """One check of a Deliverable the engineer reviews beside the chat (Plan 6), of the Saved
    version it reads: recorded on that version through `review.record_review`, so a Code C
    blocks Sign-off until the engineer closes its comments. Each version is checked once; the
    next check needs the fixes accepted by the engineer, which is the round limit here."""
    if await asyncio.to_thread(outputs.checked, ctx.rec, draft.id, version_n):
        raise ModelRetry(
            f"submit_for_check: version {version_n} of «{draft.id}» is checked already. Answer "
            "the comments with deliverable_propose; once the engineer accepts the changes, "
            "submit it again."
        )
    packet = _unsourced(ctx, draft)
    extra = await asyncio.to_thread(imported.not_in_client, ctx.rec, draft.id, version=version_n)
    packet = replace(
        packet,
        unsourced=tuple(dict.fromkeys([*packet.unsourced, *untraced])),
        not_in_client_boq=tuple(extra),
    )
    review = await checker.check(packet, ctx.store.run(ctx.run_id)["choice"], ctx.host)
    with ctx.rec.read() as c:
        (earlier,) = c.execute(
            "SELECT count(*) FROM checks WHERE deliverable_id = ?", (draft.id,)
        ).fetchone()
    review = replace(review, round=earlier + 1)
    await asyncio.to_thread(
        deliverable_review.record_review,
        ctx.rec,
        draft.id,
        review,
        version_n=version_n,
        not_in_client=extra,
    )
    _tally(ctx, ctx.agent.id, draft.id, version_n, review.code)  # the maker, as its model above
    ctx.host.emit(Reviewed(ctx.brief_id, draft.id, review))
    out = _review_json(draft.id, review, 0) | {"version": version_n}
    out.pop("rounds_left", None)
    return _json(out)


def _tally(ctx: ToolContext, member_id: str, deliverable_id: str, version: int, code: str) -> None:
    """The member's record counts the check (Phase 1, C5), in Engineer Records."""
    from qsone.engine import identity

    engineer = identity.engineer_of(ctx.host)
    if engineer is not None:
        identity.tally(
            engineer,
            member_id=member_id,
            project_id=ctx.store.project_id,
            deliverable_id=deliverable_id,
            version=version,
            code=code,
        )


async def _submit_for_check(ctx: ToolContext, args: CheckArgs) -> str:
    return await check_deliverable(ctx, args.deliverable_id)


# save_desk, use_desk --------------------------------------------------------------------------


async def _save_desk(ctx: ToolContext, args: SaveDeskArgs) -> str:
    team = [_specialist(ctx, i, "save_desk") for i in dict.fromkeys(args.specialists)]
    name = {"en": args.name_en, "ar": args.name_ar}
    desk = {
        "slug": args.slug,
        "name": name,
        "purpose": args.purpose,
        "specialists": [
            {
                "name": s.name,
                "instructions": s.instructions,
                "tools": list(s.tools),
                "tier": s.tier,
            }
            for s in team
        ],
        "procedures": [p.model_dump() for p in args.procedures],
    }
    data_dir = settings.data_dir()
    shown = desks.files(desk, version=desks.next_version(args.slug, data_dir))
    listing = "\n\n".join(f"── {path} ──\n{text.strip()}" for path, text in shown.items())
    detail = _join(copy.fill(copy.DESK_SAVE, desk=name), listing)
    card = Card(uuid4().hex, "desk", copy.DESK_TITLE, detail, ("yes", "no"))
    if await _ask(ctx, card) != "yes":
        raise Denied("save_desk")
    folder = desks.save(desk, data_dir)
    return _json({"saved": args.slug, "version": int(folder.name[1:]), "status": "draft"})


async def _use_desk(ctx: ToolContext, args: UseDeskArgs) -> str:
    data_dir = settings.data_dir()
    if args.slug is None:
        return _json({"desks": desks.saved(data_dir)})
    try:
        desk = desks.load(args.slug, data_dir)
    except (LookupError, OSError, ValueError, KeyError):
        known = ", ".join(d["slug"] for d in desks.saved(data_dir)) or "none is saved yet"
        raise ModelRetry(f"use_desk: no saved Desk «{args.slug}». Saved Desks: {known}.") from None
    have = len(specialists(ctx.store, ctx.brief_id))
    if have + len(desk["specialists"]) > MAX_SPECIALISTS:
        raise ModelRetry(
            f"use_desk: the Desk has {len(desk['specialists'])} specialists and this Brief "
            f"already has {have}; a Brief has at most {MAX_SPECIALISTS}."
        )
    built = [
        _build(
            ctx,
            name=s["name"],
            instructions=s["instructions"],
            tools=s["tools"],
            tier=s["tier"],
            desk=args.slug,
            tool="use_desk",
        )
        for s in desk["specialists"]
    ]
    return _json(
        {
            "desk": args.slug,
            "version": desk["version"],
            "specialists": [{"specialist_id": s.id, "name": s.name} for s in built],
            "procedures": desk["procedures"],
        }
    )
