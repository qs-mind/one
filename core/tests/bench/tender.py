"""The bench's tender day (Phase 1, Wave 2's real-window walk): the scripted Lead plans the
tender, works its stage, and changes a setting when the engineer asks. Deterministic, no network.

- **The plan.** The Brief "Write the tender plan" (the No plan card's button, POST
  .../plan/request): `tender_plan_write` with one stage and one member beside the
  Lead and the Checking QS, dated from today (UTC, as the project's clock) to the tender's
  submission date as ONE's kit gives it ("(this tender) | … | due <date>"). No date yet: no plan.
- **The stage.** The Brief the plan driver starts ("Stage 1 of 1: …"): the BOQ's items, the
  stage's work planned for the plan's member, the member built and given its task (it says so
  in the team room, `send_message`), then the priced sheet (`deliverable_create`), which the
  Checking QS checks. The stage then waits for the engineer's sign-off.
- **A setting.** The engineer asks for a monthly spending cap ("خلي سقف الصرف الشهري ٥٠ دولار",
  "set the monthly spending cap to 50 dollars"): `settings_set` caps.month_usd.

Registered into `fake`'s scenarios on import (fake imports this module at its end)."""

import re
from datetime import UTC, datetime

from qsone import copy
from tests.bench import fake

TITLE = {"en": "Pricing the BOQ (sample)", "ar": "تسعير جدول الكميات - عينة"}
SHEET = {"en": "Priced BOQ (bench sample)", "ar": "جدول كميات مسعر (عينة تجريبية)"}
GATE = {"en": "You sign off the priced BOQ (sample)", "ar": "اعتمادك لجدول الكميات المسعر - عينة"}
MEMBER = {  # as the Phase 1 scenarios' Pricing QS: a QS title, no personal name
    "ref": "pricing-qs",
    "name": {"en": "Pricing QS", "ar": "مهندس التسعير"},
    "title": {"en": "Pricing Quantity Surveyor (sample)", "ar": "مهندس كميات التسعير (عينة)"},
    "speciality": {"en": "Rates build-up agent (sample)", "ar": "وكيل تحليل الأسعار (عينة)"},
    "style": {"en": "Cites a source for every rate (sample)", "ar": "بيذكر مصدر لكل سعر - عينة"},
    "tools": ["search_records", "send_message"],
}
INSTRUCTIONS = (
    "You are the bench Pricing QS, a stand-in member of the QS Mind ONE test bench. You tell "
    "the Lead in the team room that you started on the sample rates, then report."
)
MONTH_CAP = "caps.month_usd"

_DUE = re.compile(r"\(this tender\) \|[^\n]*\| due (\d{4}-\d{2}-\d{2})")
_STAGE = re.compile(r"^(?:Stage \d+ of \d+: |المرحلة \d+ من \d+: )")
_CAP = re.compile(r"سقف الصرف|spending cap", re.I)  # never «الأسقف» of a BOQ item
_AMOUNT = re.compile(r"[0-9٠-٩]+(?:[.٫][0-9٠-٩]+)?")
_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩٫", "0123456789.")


def due(instructions: str) -> str:
    """This tender's submission date as ONE's kit gives the Lead, or ""."""
    found = _DUE.search(instructions)
    return found.group(1) if found else ""


def scenario(brief: str) -> str | None:
    """The tender day's scenario a Brief asks for, if any."""
    if brief in copy.PLAN_REQUEST_BRIEF.values():
        return "plan"
    if _STAGE.match(brief):
        return "stage"
    if _CAP.search(brief) and _AMOUNT.search(brief):
        return "setting"
    return None


# The plan -------------------------------------------------------------------------------------


def _plan_write(seen: fake.Seen):
    if not seen.due:
        return None  # the Brief's reply says what was done: nothing, without a date
    today = datetime.now(UTC).date().isoformat()
    stage = {
        "title": TITLE,
        "owner": MEMBER["ref"],
        "starts": today,
        "ends": seen.due,
        "outputs": [{"kind": "deliverable", "title": SHEET}],
        "gate": GATE,
        "requests": 6,
    }
    args = {"submission_date": seen.due, "stages": [stage], "team": [MEMBER]}
    return fake._call("tenderplan", "tender_plan_write", args)


# The stage ------------------------------------------------------------------------------------


def _stage_items(seen: fake.Seen):
    return fake._call("items", "find_items", {"kind": "boq_item"})


def _stage_plan(seen: fake.Seen):
    name = MEMBER["name"][seen.lang]
    task = fake._words(seen, "Sample rates for the BOQ", "أسعار عينة لجدول الكميات")
    steps = [{"specialist": name, "task": task, "requests": 2}]
    return fake._call(
        "stageplan", "plan_brief", {"steps": steps, "deliverables": [SHEET[seen.lang]]}
    )


def _stage_build(seen: fake.Seen):
    args = {
        "name_en": MEMBER["name"]["en"],
        "name_ar": MEMBER["name"]["ar"],
        "instructions": INSTRUCTIONS,
        "tools": MEMBER["tools"],
        "tier": "specialist",
    }
    return fake._call("build", "build_specialist", args)


# A setting ------------------------------------------------------------------------------------


def _setting(seen: fake.Seen):
    amount = _AMOUNT.search(seen.brief).group(0).translate(_DIGITS)
    return fake._call("setting", "settings_set", {"key": MONTH_CAP, "value": amount})


fake.LEAD_SCENARIOS.update(
    {
        "plan": (_plan_write,),
        "stage": (_stage_items, _stage_plan, _stage_build, fake._delegate, fake._sheet),
        "setting": (_setting,),
    }
)
fake._STEP_OF.update(
    {
        _plan_write: "tenderplan",
        _stage_items: "items",
        _stage_plan: "stageplan",
        _stage_build: "build",
        _setting: "setting",
    }
)
