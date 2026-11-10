"""What the Lead sends the plan tools, the checks a plan passes before it is stored, and its
expected cost and time.

A plan is checked in code, never by the model: stages in order, dated from today to the
tender's submission date, every owner on the team, every short name in both languages. A check
that fails raises `RecordsError` naming the value (`field`); the tool sends it back to the Lead
with a filled example."""

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from qsone import copy
from qsone.engine import costs, roles
from qsone.engine.types import ModelCard, ModelChoice, Role, Text
from qsone.records.project import RecordsError

LEAD = "lead-qs"
CHECKER = "checking-qs"
FIXED = (LEAD, CHECKER)
MAX_STAGES = 20
MAX_MEMBERS = 6  # the members a plan proposes beside the two fixed ones
_REF = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")


class _Args(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class TextIn(_Args):
    """A short name for the screen, in both languages (checked by `check`, so a missing one is
    named in the refusal)."""

    en: str = Field("", max_length=200)
    ar: str = Field("", max_length=200)


class OutputIn(_Args):
    kind: Literal["deliverable", "file", "map", "summary"]
    title: TextIn


class StageIn(_Args):
    id: str | None = Field(None, max_length=64)  # a stage already in the plan keeps its id
    title: TextIn
    owner: str = Field(min_length=1, max_length=64)  # lead-qs, checking-qs or a team ref
    engineer_supplies: TextIn | None = None  # what the engineer brings, when ONE cannot do it
    starts: date
    ends: date  # the last day, included
    outputs: list[OutputIn] = Field(default_factory=list, max_length=10)
    gate: TextIn  # what the engineer signs off
    requests: int = Field(ge=1, le=500)  # about how many model requests its work needs


class MemberIn(_Args):
    ref: str = Field(min_length=1, max_length=40)  # how the stages name it, e.g. "pricing-qs"
    name: TextIn  # the short name in lists, e.g. "Pricing QS"
    title: TextIn  # its QS title
    speciality: TextIn
    style: TextIn  # working style and voice
    tools: list[str] = Field(default_factory=list, max_length=40)


class PlanIn(_Args):
    submission_date: date  # the tender's own submission date, as its facts hold it
    stages: list[StageIn] = Field(min_length=1, max_length=MAX_STAGES)
    team: list[MemberIn] = Field(default_factory=list, max_length=MAX_MEMBERS)


@dataclass(frozen=True)
class Estimate:
    usd: str | None  # None when a model in the plan has no known price
    minutes: int
    basis: Text
    paid: bool  # approving starts work that costs money

    def same_figures(self, other: "Estimate") -> bool:
        """The figures the engineer approves; the basis only says how they were worked out."""
        return (self.usd, self.minutes, self.paid) == (other.usd, other.minutes, other.paid)


@dataclass(frozen=True)
class PlanDraft:
    """A plan as the Lead wrote it, with its estimate, ready for `store.propose`."""

    submission_date: str
    stages: list[StageIn]
    team: list[MemberIn]
    estimate: Estimate
    # (input, output, requests) of the requests measured when it was worked out; kept, so that
    # only the sheet moves the figures at approval
    measured: tuple[int, int, int] | None = None


# The estimate -----------------------------------------------------------------------------------


def picked_roles(sheet: list[ModelCard]) -> dict[Role, ModelChoice]:
    """The model of each role for an estimate: the engineer's choices on the sheet over the
    defaults, every role filled. The same at proposal and at approval, so only a change of the
    models, prices or AI links moves the estimate."""
    allowed = {card.choice for card in sheet}
    picked = {r: c for r, c in roles.chosen(sheet).items() if c in allowed}
    if "lead" not in picked and sheet:
        picked["lead"] = sheet[0].choice
    for role in roles.ROLES:
        if "lead" in picked:
            picked.setdefault(role, picked["lead"])
    return picked


def _tier(owner: str) -> Role:
    return "lead" if owner == LEAD else "checker" if owner == CHECKER else "specialist"


# The work of one stage for its estimate: (owner, model requests, Deliverables it makes).
Work = tuple[str, int, int]


def work_of(stages: list[StageIn]) -> list[Work]:
    return [
        (s.owner, s.requests, sum(1 for o in s.outputs if o.kind == "deliverable")) for s in stages
    ]


def estimate(
    work: list[Work], sheet: list[ModelCard], measured: tuple[int, int, int] | None
) -> Estimate:
    """The plan's expected cost and time by `costs.brief_budget`: each stage's requests on its
    owner's model, one Lead request to hand it over and end it, and one Checking QS request for
    each Deliverable it makes."""
    items = []
    for owner, requests, made in work:
        items.append({"tier": _tier(owner), "requests": requests})
        items.append({"tier": "lead", "requests": 1})
        if made:
            items.append({"tier": "checker", "requests": made})
    budget = costs.brief_budget(items, sheet, picked_roles(sheet), measured, "same")
    usd = None if budget.usd is None else costs.usd_text(budget.usd)
    return Estimate(usd, budget.minutes, budget.basis, usd is None or Decimal(usd) > 0)


# The checks ---------------------------------------------------------------------------------------


def _bad(text: dict, where: str, **values) -> RecordsError:
    return RecordsError(copy.fill(text, **values) if values else text, status=422, field=where)


def _pair(value: TextIn | None, field: str) -> None:
    if value is not None and not (value.en and value.ar):
        raise _bad(copy.PLAN_TEXT_PAIR, field, field=field)


def check_date(fact: str | None, today: date) -> date:
    """The tender's submission date as the plan may use it, or PLAN_NEEDS_SUBMISSION_DATE
    (409) when it is missing or has passed."""
    try:
        found = date.fromisoformat(fact) if fact else None
    except ValueError:
        found = None
    if found is None or found < today:
        raise RecordsError(copy.PLAN_NEEDS_SUBMISSION_DATE, field="submission_date")
    return found


def _check_team(team: list[MemberIn], allowed_tools: set[str]) -> None:
    refs: set[str] = set()
    for n, member in enumerate(team):
        where = f"team[{n}]"
        if not _REF.match(member.ref) or member.ref in FIXED or member.ref in refs:
            raise _bad(copy.PLAN_MEMBER_REF, f"{where}.ref", n=n + 1, ref=member.ref)
        refs.add(member.ref)
        for name in ("name", "title", "speciality", "style"):
            _pair(getattr(member, name), f"{where}.{name}")
        for tool in member.tools:
            if tool not in allowed_tools:
                raise _bad(copy.PLAN_MEMBER_TOOL, f"{where}.tools", n=n + 1, tool=tool)


def check(
    plan: PlanIn,
    *,
    fact: str | None,
    today: date,
    known: dict[str, dict],
    allowed_tools: set[str],
    locked: frozenset[str] = frozenset(),
) -> None:
    """Raises `RecordsError` for the first value that does not fit. `fact` is the tender's
    submission date, `known` the stages of the plan now by id, `locked` the ids of stages that
    are not `pending` any more: their dates are kept as they are, not checked against today."""
    due = check_date(fact, today)
    if plan.submission_date != due:
        raise _bad(copy.PLAN_DATE_NOT_FACT, "submission_date", date=due.isoformat())
    _check_team(plan.team, allowed_tools)
    owners = {*FIXED, *(member.ref for member in plan.team)}
    seen: set[str] = set()
    before: StageIn | None = None
    for n, stage in enumerate(plan.stages):
        where = f"stages[{n}]"
        if stage.id is not None:
            if stage.id not in known:
                raise _bad(copy.PLAN_STAGE_UNKNOWN, f"{where}.id", n=n + 1, id=stage.id)
            if stage.id in seen:
                raise _bad(copy.PLAN_STAGE_TWICE, f"{where}.id", n=n + 1, id=stage.id)
            seen.add(stage.id)
        for name in ("title", "gate", "engineer_supplies"):
            _pair(getattr(stage, name), f"{where}.{name}")
        for k, output in enumerate(stage.outputs):
            _pair(output.title, f"{where}.outputs[{k}].title")
        if stage.owner not in owners:
            raise _bad(copy.PLAN_OWNER_UNKNOWN, f"{where}.owner", n=n + 1, owner=stage.owner)
        if stage.ends < stage.starts:
            raise _bad(copy.PLAN_STAGE_DATES, f"{where}.ends", n=n + 1)
        if before is not None and stage.starts < before.ends:
            raise _bad(copy.PLAN_STAGE_ORDER, f"{where}.starts", n=n + 1)
        dated = stage.id in locked or (today <= stage.starts and stage.ends <= due)
        if not dated:
            values = {"n": n + 1, "today": today.isoformat(), "date": due.isoformat()}
            raise _bad(copy.PLAN_DATE_OUTSIDE, f"{where}.starts", **values)
        before = stage
