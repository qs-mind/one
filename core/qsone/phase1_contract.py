"""The Phase 1 contract: every shape the new screens read from the core or send to it.

Rules that hold for every model here:
- `Text` is ONE's own words, or a short name an agent wrote for the screen, in both languages.
  A plain `str` named `text`, `reason` or `opinion` is prose in the one language it was written in.
- Money and quantities are exact decimal text ("0.50"), never a JSON number. Counts are integers.
- An id is 32 lower-case hex digits, except the two fixed members `lead-qs` and `checking-qs`.
- A moment is ISO-8601 UTC written with `+00:00`; a day is `YYYY-MM-DD`.
- Unknown is `null`, never `0` or `""`.
"""

from typing import Annotated, Literal

from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictStr

from qsone import copy

# Shared -----------------------------------------------------------------------------------------

# What the screen can offer beside a refusal. "caps" is new: open Settings, Spending caps.
Fix = Literal["ai", "search", "consent", "retry", "backup", "caps"]
BriefState = Literal[
    "queued",
    "running",
    "waiting_engineer",
    "waiting_connection",
    "paused_cap",
    "stopped",
    "done",
    "failed",
]
# Every kind of card the engineer answers with POST /cards/{card_id}: the thirteen of today and
# two new ones (`keep_member`: C5, `setting`: C10). A card lives only while its Brief runs.
CardKind = Literal[
    "outside",
    "online",
    "cap",
    "price",
    "budget",
    "fallback",
    "desk",
    "disagreement",
    "question",
    "keep",
    "rows",
    "cost",
    "connector",
    "keep_member",
    "setting",
]


class Text(BaseModel):
    """ONE's own words, or a short name an agent wrote for the screen, in both languages.
    Neither side is ever empty: where nothing is known the pair itself is `null`."""

    en: str = Field(min_length=1)
    ar: str = Field(min_length=1)


class Refusal(BaseModel):
    """Every refused request of a contract route. `error` is always a pair, never a string."""

    error: Text
    fix: Fix | None = None  # the action the screen can offer
    field: str | None = None  # the value that does not fit
    example: str | None = None  # a value that would fit, for `field`
    brief_id: str | None = None  # the work that is running, when that is the reason


class BodyProblemItem(BaseModel):
    """One place where a body does not fit, as FastAPI says it: where and why."""

    loc: list[str | int]
    msg: str
    type: str


class BodyProblem(BaseModel):
    """A body the screen built wrongly (a missing key, a wrong JSON type, an unknown key).
    Never something the engineer typed: those come back as a `Refusal` with words."""

    detail: list[BodyProblemItem]


class Undoable(BaseModel):
    """A removal that can be taken back with POST /undo/{undo} for `window_ms`."""

    undo: str
    window_ms: int


class BriefStarted(BaseModel):
    """Work was started for the Lead: the new Brief's id. Its reply arrives on the chat
    stream, and a `brief` event says when its state changes."""

    brief_id: str


class Source(BaseModel):
    """Where a fact comes from: the source the Sheet, the view and the source card already read
    (`Source` in ui/src/deliverables/types.ts). `kind` is the ledger's own word and the list is
    open: an agent's word for a place in a file ("boq", "quote"), "file" for a tender fact, or
    ONE's "calculation", "engineer", "chat", "web", "prices", "sample". Only "sample" has a rule
    (the sample pill); a kind the screen does not know is drawn as a plain titled source."""

    kind: str
    title: str  # for a tender fact: the file's name, or "" for the engineer's own value
    file_name: str | None = None
    file_id: str | None = None
    # The place in the file: page, sheet, row, column, line, paragraph, item,
    # `ocr_low_confidence` (true or false); `box` is [x0, y0, x1, y1] in PDF points from the
    # top-left of a one-based page.
    locator: dict[str, bool | str | int | float | tuple[float, float, float, float]]
    url: str | None = None
    dated: str | None = None  # the day the fact is true for
    quote: str | None = None  # the line read at that place


# The engineer -----------------------------------------------------------------------------------

OrgType = Literal["contractor", "consultant", "owner", "procurement"]
Country = Literal["EG", "SA", "AE", "other"]


class ProfileIn(BaseModel):
    """PUT /engineer/profile: the seven fields as they stand. A half-filled profile is saved.
    The handler checks each value and refuses with words (PROFILE_BAD_VALUE): a name longer
    than 80 characters, a position or company longer than 120, a currency that is not three
    capitals. The bounds here only stop a runaway body."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    first_name: str = Field(max_length=1_000)
    last_name: str = Field(max_length=1_000)
    position: str = Field(max_length=1_000)
    company: str = Field(max_length=1_000)
    org_type: OrgType | None
    country: Country | None
    currency: str | None = Field(max_length=16)  # ISO 4217, three capitals


class Profile(BaseModel):
    """GET and PUT /engineer/profile: what the engineer told ONE about themselves, as stored
    in Engineer Records."""

    first_name: str  # "" until filled
    last_name: str
    position: str
    company: str
    org_type: OrgType | None
    country: Country | None
    currency: str | None
    complete: bool  # all seven are filled; the core's answer, never sent


class Lesson(BaseModel):
    """One Lesson Learned the Lead keeps about the engineer, in Engineer Records."""

    id: str
    text: str
    from_project_id: str | None  # the tender it came from; null when it came from Home
    from_project_name: str | None  # null too when that tender's name cannot be read any more
    at: str


class Lessons(BaseModel):
    """GET /engineer/lessons: every Lesson Learned that was not removed."""

    lessons: list[Lesson]  # newest first


class LessonIn(BaseModel):
    """PATCH /engineer/lessons/{lesson_id}: the lesson's new words."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    # The handler refuses more than 2,000 characters with words (LESSON_TOO_LONG); this bound
    # only stops a runaway body.
    text: str = Field(max_length=20_000)


# Home and the tender's header -------------------------------------------------------------------

StageStatus = Literal[
    "pending",
    "now",
    "waiting_engineer",  # its work ended and it asks for the engineer's sign-off; nothing else
    "approved",
]
# The first that holds, in this order; `working` when none does (section 1, row 7).
TenderState = Literal[
    "archived",  # closed and read-only; never in GET /home
    "waiting",  # running work waits on a card, or nothing runs and a blocking item waits
    "paused",  # the running work is stopped at 80% of a Spending Cap (its `cap` card waits)
    "offline",  # the running work waits for the network
    "reading",  # no plan yet, and its files are still being read
    "working",  # work is running, or queued behind other work
    "finished",  # every stage is approved
    "failed",  # the last work failed and nothing has run since; `line` says why
    "stopped",  # the last work was stopped or left and nothing has run since
    "no_plan",  # read, nothing runs, no tender plan yet
]
WaitingKind = Literal["plan", "stage", "plan_change", "decision", "unfinished"] | CardKind


class LeadBlock(BaseModel):
    """Why the Lead cannot start work now. For every tender: no AI is connected; the provider
    refused the key when ONE last listed its models; the AI consent is not given; the day's or
    the month's Spending Cap is reached; Engineer Records cannot be opened. For one tender: it is
    a Confidential Project, `ai.confidential_on_device` is on and no model on this computer is
    connected. No network is not known before work starts: it shows as `offline`."""

    reason: Text
    fix: Fix | None


class TenderRow(BaseModel):
    """One tender in a line: the row Home lists and the header its own place draws.
    The core remembers it for a closed project, so reading it opens nothing."""

    project_id: str
    name: str
    name_pair: Text | None  # only for ONE's own dated name: shown instead of `name`
    confidential: bool
    sample: bool  # something in it is sample data
    state: TenderState
    line: Text | None  # what is happening now, or why it cannot go on
    blocked: LeadBlock | None  # why the Lead cannot start work in it now; null when it can
    stage: Text | None  # the stage that is "now" or waits for sign-off; null without one
    stages: list[StageStatus]  # one per stage, in order; [] with no plan
    submission_date: str | None  # the tender fact, from the documents or the engineer
    submission_source: Source | None  # that fact's source; null with no date
    waiting: int  # items waiting for the engineer in this tender
    files_read: int  # current files whose reading has ended (read, or failed with a reason)
    files_total: int  # current files that have arrived


class WaitingItem(BaseModel):
    """One thing the engineer must answer, and the id of the part that shows it in that
    conversation. By kind, `id` is: "plan" and "plan_change" the plan's id (its last `data-plan`
    part); "stage" the stage's id (`data-stage`); "decision" the Finding's id (`data-finding`);
    "unfinished" the Brief's id (its reply is "<id>-reply"); any card kind the card's id
    (`data-card`)."""

    id: str
    kind: WaitingKind
    project_id: str | None  # null: the Home conversation
    title: Text
    text: str | None  # kind "question": the first question's own words; null for the others
    since: str
    blocking: bool  # no work goes on in that conversation until it is answered


class HomeSummary(BaseModel):
    """The Lead's words about the tenders it may speak of, and when it wrote them."""

    text: str  # the Lead's words; never mentions a Confidential Project
    at: str
    covers: int  # how many of `tenders` the summary speaks about


class UnreadableTender(BaseModel):
    """A project whose Project Records cannot be opened: nothing else about it is known."""

    project_id: str
    reason: Text  # the core's own words, as POST /projects/{id}/open would refuse


class Home(BaseModel):
    """GET /home: everything the frame and the Home place show. It never refuses: what
    cannot be read is said inside the answer."""

    summary: HomeSummary | None  # null: being written, or the Lead cannot work, or no tender
    blocked: LeadBlock | None  # why the Lead cannot start work at all now; null when it can
    last_project_id: str | None  # the tender last opened, when it is one of `tenders`
    waiting: list[WaitingItem]  # every listed tender's and the Home conversation's, oldest first
    tenders: list[TenderRow]  # archived ones left out; the order is the core's (section 1)
    unreadable: list[UnreadableTender]  # shown after the tenders


class TenderView(BaseModel):
    """GET /projects/{project_id}/tender, and the `tender` event: a tender's header and what
    waits for the engineer in it."""

    tender: TenderRow
    waiting: list[WaitingItem]  # this tender's, oldest first


# The team ---------------------------------------------------------------------------------------


class MemberModel(BaseModel):
    """The AI model a member works with now."""

    name: str
    provider: str
    on_device: bool


class MemberTool(BaseModel):
    """A tool a member may use, with the label the screen shows for it."""

    name: str  # the tool's own name, e.g. "files_read"
    title: Text


class MemberRecord(BaseModel):
    """Counted from the member's real work in ONE; zeros for a new member."""

    tenders: int  # tenders it has spent anything in, this one included
    checks_passed: int  # Checking QS results on its work with Code A or B
    checks_total: int  # one per checked version of a Deliverable it made
    cost_usd: str  # the paid cost that is known: a subscription's and unpriced use left out


class Member(BaseModel):
    """A team member's identity card and record: the Lead QS, the Checking QS or a
    specialist. Every list carries the whole member, so no route gives one alone."""

    id: str
    role: Literal["lead", "checker", "specialist"]
    kind: Literal["fixed", "temporary", "permanent"]
    name: Text  # the short name in lists and message headers, e.g. "Lead QS"
    title: Text  # its QS title
    speciality: Text
    style: Text  # working style and voice
    model: MemberModel | None  # null: none can be used for it now, or none was listed yet
    tools: list[MemberTool]
    record: MemberRecord


class TeamMember(Member):
    """A member as one tender sees it."""

    state: Literal["working", "waiting", "idle", "failed"]
    doing: Text | None
    proposed: bool  # proposed with a plan or a change the engineer has not approved yet


class Members(BaseModel):
    """GET /team/members: the team that stays from tender to tender, for Settings."""

    members: list[Member]  # the Lead, the Checking QS, then permanent ones, oldest first


class TeamMembers(BaseModel):
    """GET /projects/{project_id}/members: the team of one tender."""

    members: list[TeamMember]  # the Lead, the Checking QS, then the others as they joined


# The tender plan --------------------------------------------------------------------------------


class StageOutput(BaseModel):
    """Something a stage hands over: a Deliverable, a file, the Project Map or the tender
    summary."""

    kind: Literal["deliverable", "file", "map", "summary"]
    title: Text
    id: str | None  # the Deliverable or file once it exists; always null for map and summary


class Stage(BaseModel):
    """One stage of a tender plan: who owns it, its days, what it hands over and what the
    engineer signs off at its end."""

    id: str  # the same through every version of the plan
    title: Text
    owner_member_id: str
    engineer_supplies: Text | None  # what the engineer must bring for a stage ONE cannot do alone
    starts: str
    ends: str  # the last day, included
    status: StageStatus
    result: Text | None  # one short line on what was done, once its work has ended
    outputs: list[StageOutput]
    gate: Text  # what the engineer signs off


class PlanChange(BaseModel):
    """A Suggested change to an approved plan: the plan as it would be. It is accepted or
    rejected with POST /projects/{project_id}/plan/change. `stages[*].status`, `result` and
    output ids are always the current plan's."""

    id: str
    reason: str
    submission_date: str
    stages: list[Stage]
    team: list[Member]
    expected_cost_usd: str | None
    expected_minutes: int
    cost_basis: Text
    paid: bool  # accepting raises the expected cost: asked by press-and-hold


class TenderPlan(BaseModel):
    """A tender's plan: the stages dated back from the submission date, the team, and the
    estimate the engineer approves with it."""

    id: str  # the same through every version
    version: int  # 1, then one more each time what the engineer approves changes (section 1)
    status: Literal["proposed", "approved"]
    submission_date: str  # the tender fact this plan was dated back from
    stages: list[Stage]
    team: list[Member]  # the fixed members and those proposed or working; one approval covers both
    expected_cost_usd: str | None  # null when a model in the plan has no known price
    expected_minutes: int
    cost_basis: Text  # where the estimate comes from
    paid: bool  # approving starts work that costs money: asked by press-and-hold
    approved_at: str | None
    change: PlanChange | None


class PlanView(BaseModel):
    """The one body the plan travels in: the GET, the three POSTs and the `plan` event."""

    plan: TenderPlan | None  # null: this tender has no plan


class PlanApproveIn(BaseModel):
    """POST /projects/{project_id}/plan/approve: approves the plan and its team as shown."""

    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)  # the version on screen; another one is refused


class StageApproveIn(BaseModel):
    """POST /projects/{project_id}/plan/stages/{stage_id}/approve: signs off a stage of the
    plan as shown. A sign-off cannot be undone."""

    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)


class PlanChangeIn(BaseModel):
    """POST /projects/{project_id}/plan/change: accepts or rejects the Suggested change that
    is on screen."""

    model_config = ConfigDict(extra="forbid")

    change_id: str = Field(min_length=1, max_length=64)  # the change on screen
    accept: StrictBool


# Findings ---------------------------------------------------------------------------------------


class Finding(BaseModel):
    """A conflict or risk a member found in the tender, with where it was read. Once the
    Lead raises it, it is a decision: the Lead's opinion and two options for the engineer."""

    id: str
    title: Text  # a short name for lists and for its waiting item
    text: str  # the conflict or risk
    sources: list[Source]  # at least one
    status: Literal["open", "queued", "raised", "settled"]
    opinion: str | None  # the Lead's, once it decided to raise it
    options: tuple[Text, Text] | None  # null until then; the first is the Lead's recommendation
    chosen: Literal[0, 1] | None  # the engineer's choice; null when settled without one
    item_ids: list[str]  # the BOQ items it is about: their rows are marked until it is settled
    note: Text | None  # what it waits for; once settled without a choice, how it was closed
    settled_at: str | None


class Findings(BaseModel):
    """GET /projects/{project_id}/findings: every Finding of the tender."""

    findings: list[Finding]  # oldest first


class DecideIn(BaseModel):
    """POST /projects/{project_id}/findings/{finding_id}/decide: which of the two options the
    engineer takes."""

    model_config = ConfigDict(extra="forbid")

    choice: Literal[0, 1]  # 0: the first option, the Lead's recommendation


# The team room ----------------------------------------------------------------------------------


class RoomRaise(BaseModel):
    """What a raised message became in the engineer's conversation: a Finding (`id` is the
    Finding's) or a card (`id` is the card's). It is the id of that part and of its waiting item."""

    id: str
    answered: bool


class RoomMessage(BaseModel):
    """One message in a tender's team room. It also travels as the `data-room` part of the
    reply it was written in."""

    id: str
    from_id: str  # a member id, or "engineer"
    to_id: str  # a member id, "team" (everyone) or "engineer"
    text: str
    sources: list[Source]
    at: str
    # Set while what the Lead raised waits for the engineer and after they answered it; null for
    # an ordinary message, and again when a card was withdrawn or a Finding closed without them.
    raised: RoomRaise | None


class RoomPage(BaseModel):
    """GET /projects/{project_id}/room: one page of the team room."""

    messages: list[RoomMessage]  # newest first, in the order they were written
    next_cursor: str | None  # pass as `cursor` for the older page; null at the start


class RoomMessageIn(BaseModel):
    """POST /projects/{project_id}/room: what the engineer writes to the team."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    # The handler refuses more than 20,000 characters with words (ROOM_TOO_LONG).
    text: str = Field(max_length=200_000)


# Automatic setup --------------------------------------------------------------------------------


class SetupPart(BaseModel):
    """One part ONE needs beyond the installer, and how far its download is."""

    id: str
    title: Text
    state: Literal["present", "queued", "downloading", "waiting_network", "failed", "unavailable"]
    done_bytes: int
    total_bytes: int  # from the manifest in code, so always known
    affects: Text  # what does not work without it
    reason: Text | None  # why it failed, or why it cannot run on this computer; else null


class SetupState(BaseModel):
    """GET /setup/parts, POST /setup/parts/retry and the `setup` event: the Automatic setup."""

    ready: bool  # every part is present or unavailable: nothing more will be downloaded
    parts: list[SetupPart]


# Settings ---------------------------------------------------------------------------------------

SettingSection = Literal["ai", "caps", "privacy", "look"]


class SettingBase(BaseModel):
    """What every setting carries, whatever its control."""

    key: str  # "<section>.<name>", e.g. "caps.month_usd"
    section: SettingSection
    title: Text
    help: Text
    at_recommended: bool


class ToggleSetting(SettingBase):
    """A setting that is on or off."""

    control: Literal["toggle"]
    value: bool
    recommended: bool


class SettingChoice(BaseModel):
    """One value a choice setting can take, with its label."""

    value: str
    title: Text


class ChoiceSetting(SettingBase):
    """A setting that takes one of a few values."""

    control: Literal["choice"]
    value: str
    recommended: str
    choices: list[SettingChoice]


class MoneySetting(SettingBase):
    """A setting that is an amount of money, as exact decimal text."""

    control: Literal["money"]
    value: str
    recommended: str
    currency: str  # "USD"


class NumberSetting(SettingBase):
    """A setting that is a number within limits, as exact decimal text."""

    control: Literal["number"]
    value: str
    recommended: str
    min: str
    max: str
    step: str


Setting = Annotated[
    ToggleSetting | ChoiceSetting | MoneySetting | NumberSetting, Field(discriminator="control")
]


class Settings(BaseModel):
    """GET /settings: every setting the screens draw from data. The profile, the AI links,
    the Connectors, the Backup and the team have their own routes."""

    settings: list[Setting]  # in the registry's order: ai, caps, privacy, look


class SettingIn(BaseModel):
    """PATCH /settings/{key}. A toggle takes true or false; every other control takes text
    (a choice's value, or an exact decimal). To put a setting back, send its `recommended`."""

    model_config = ConfigDict(extra="forbid")

    value: StrictBool | StrictStr


class AiConnectIn(BaseModel):
    """POST /settings/ai/connect: the key as it was pasted. The provider is read from the
    key's own form and from nothing else."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    # The handler refuses a key it does not recognise with words (KEY_NOT_RECOGNISED) and never
    # echoes it; this bound only stops a runaway body.
    key: str = Field(min_length=1, max_length=10_000)


class AiLink(BaseModel):
    """A provider connected with a pasted key. The key itself is never in any answer."""

    id: str  # the connector's id, as in GET /settings/ai: "anthropic" or "standard:<id>"
    name: str
    provider: str


# Shapes that travel outside a route's JSON answer -----------------------------------------------
# Parts of the chat stream: {"type": "data-<name>", "id": ..., "data": <shape>}. The AI SDK types
# a part's `id` as optional, so each part repeats in `data` what it points at.


class PlanPart(BaseModel):
    """data-plan (id: the plan's id): the Lead proposed this version, or a change to it, here."""

    plan_id: str
    version: int


class StagePart(BaseModel):
    """data-stage (id: the stage's id): this reply ends the stage and asks for its sign-off."""

    stage_id: str


class FindingPart(BaseModel):
    """data-finding (id: the Finding's id): the Lead raised this Finding here."""

    finding_id: str


class SourcesPart(BaseModel):
    """data-sources (id: the Brief's id): what the reply rests on, as far as the core can prove:
    the sources of its figures, then the places the Lead read in this work (section 3.1)."""

    sources: list[Source]


class SteerPart(BaseModel):
    """data-steer (id: a new id): what the engineer wrote while this work ran."""

    text: str
    at: str


# data-room (id: the message's id) carries a RoomMessage.


class StoredMessageMark(BaseModel):
    """The keys this contract adds to `metadata` of a message in GET /chat/{chat_id}/messages."""

    at: str  # the question: when its Brief was made; the reply: when it last changed
    by: Literal["one"] | None = None  # on a question: ONE started this work, not the engineer


class KeepMemberCard(BaseModel):
    """`payload` of a `keep_member` card."""

    member_id: str


class CardQuestion(BaseModel):
    """One question in `payload.questions` of a `question` card."""

    id: str
    text: str
    options: list[str] | None = None
    free_text: bool | None = None
    # New: what the answer is, so the screen draws the right field. The answer stays text: an
    # exact decimal for "number" and "money", YYYY-MM-DD for "date". Left out: "text".
    kind: Literal["text", "number", "money", "date"] | None = None
    unit: str | None = None  # a currency code for "money"; "%" or a unit for "number"


class UnreadPart(BaseModel):
    """One part of a file ONE could not read (added to a file's JSON as `unread`)."""

    part: Text
    why: Text


StepState = Literal["done", "skipped"]


class SetupStepStates(BaseModel):
    """Each first-launch step: how it was passed, or null when it was not yet."""

    language: StepState | None
    account: StepState | None
    ai: StepState | None
    card: StepState | None
    usage: StepState | None


class SetupSteps(BaseModel):
    """The answer GET /setup and PUT /setup/{step} already give, typed for the new gate."""

    done: bool
    steps: SetupStepStates


# Events on GET /projects/{project_id}/activity (a tender's id, or "general").


class PlanEvent(PlanView):
    """`plan`: the plan was proposed, approved or changed, a stage moved, or a Suggested
    change came or went. The screen replaces its plan and reloads the members."""

    type: Literal["plan"]


class FindingEvent(BaseModel):
    """`finding`: a Finding was recorded, queued, raised or settled, or its note changed.
    The screen replaces it by id, or adds it at the end."""

    type: Literal["finding"]
    finding: Finding


class RoomEvent(BaseModel):
    """`room`: a message was written in the team room, or its `raised` changed."""

    type: Literal["room"]
    message: RoomMessage


class MemberEvent(BaseModel):
    """`member`: a member joined or became permanent, or its `state` or `doing` changed."""

    type: Literal["member"]
    member: TeamMember


class TenderEvent(TenderView):
    """`tender`: the tender's row, or what waits in it, changed. Replaces both."""

    type: Literal["tender"]


class BriefEvent(BaseModel):
    """`brief`: a Brief in this tender's chat started or changed state."""

    type: Literal["brief"]
    brief_id: str
    state: BriefState


class HomeEvent(BaseModel):
    """`home`: something GET /home answers has changed."""

    type: Literal["home"]  # reload GET /home


class SettingEvent(BaseModel):
    """`setting`: a setting changed, by the screen or by the Lead."""

    type: Literal["setting"]
    setting: Setting


class SetupEvent(BaseModel):
    """`setup`: a part's state or bytes changed."""

    type: Literal["setup"]
    setup: SetupState


class LessonsEvent(BaseModel):
    """`lessons`: a lesson was saved, changed, removed or put back."""

    type: Literal["lessons"]  # reload GET /engineer/lessons


TenderActivity = Annotated[
    PlanEvent | FindingEvent | RoomEvent | MemberEvent | TenderEvent | BriefEvent,
    Field(discriminator="type"),
]
GeneralActivity = Annotated[
    HomeEvent | SettingEvent | SetupEvent | LessonsEvent, Field(discriminator="type")
]

# Models no route returns: the export adds them to the OpenAPI document by hand.
SCHEMA_ONLY = (
    PlanPart,
    StagePart,
    FindingPart,
    SourcesPart,
    SteerPart,
    StoredMessageMark,
    KeepMemberCard,
    CardQuestion,
    UnreadPart,
    SetupSteps,
    PlanEvent,
    FindingEvent,
    RoomEvent,
    MemberEvent,
    TenderEvent,
    BriefEvent,
    HomeEvent,
    SettingEvent,
    SetupEvent,
    LessonsEvent,
)


# The one way a contract route refuses -----------------------------------------------------------


def refusal(
    text: dict[str, str],
    status: int = 409,
    *,
    field: str | None = None,
    example: str | None = None,
    brief_id: str | None = None,
) -> JSONResponse:
    """A `Refusal` as the answer: the text with its `fix` (`copy.error`), and the keys that
    apply. Every contract router catches `RecordsError` and answers through this, because the
    app's own handler drops `field`."""
    more = {"field": field, "example": example, "brief_id": brief_id}
    body = copy.error(text) | {k: v for k, v in more.items() if v is not None}
    return JSONResponse(body, status_code=status)
