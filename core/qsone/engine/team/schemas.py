"""What the model sends each team tool and reads about it: the arguments, a filled example and
the description."""

from typing import Any, Literal

from pydantic import Field

from qsone.engine import agents, checker, desks

from .common import MAX_SPECIALISTS, _Args, _json

# plan_brief -----------------------------------------------------------------------------------


class PlanStep(_Args):
    specialist: str = Field(min_length=1, max_length=100)
    task: str = Field(min_length=1, max_length=2000)
    tier: Literal["specialist", "quick"] = "specialist"
    requests: int = Field(10, ge=1, le=500)


class PlanArgs(_Args):
    steps: list[PlanStep] = Field(min_length=1, max_length=30)
    deliverables: list[str] = Field(default_factory=list, max_length=20)


_PLAN_EXAMPLE = {
    "steps": [
        {"specialist": "Take-off QS", "task": "Quantities of section 03", "requests": 12},
        {"specialist": "Estimator", "task": "Rates for section 03", "requests": 15},
    ],
    "deliverables": ["Priced BOQ, section 03"],
}

_PLAN_DOC = f"""Plan the Brief before you build any specialist: its steps and the Deliverables.
- steps: one per piece of work; specialist is the name you will build, task the work in a \
line, tier "specialist" (the default) or "quick" for simple lookups, requests about how many \
model requests it needs.
- deliverables: the Deliverables you will make.
When the plan is large, ONE shows the engineer its expected cost and time and waits for their \
yes; a "no" means stop and tell the engineer. Planning again replaces nothing already built.
Example:
{_json(_PLAN_EXAMPLE)}"""


# build_specialist -----------------------------------------------------------------------------


class SpecialistArgs(_Args):
    name_en: str = Field(min_length=1, max_length=100)
    name_ar: str = Field(min_length=1, max_length=100)
    instructions: str = Field(min_length=1, max_length=8000)
    tools: list[str] = Field(default_factory=list, max_length=40)
    tier: Literal["specialist", "quick"] = "specialist"


_SPECIALIST_EXAMPLE = {
    "name_en": "Take-off QS",
    "name_ar": "مهندس الحصر",
    "instructions": "You measure quantities from the project's drawings and BOQ. ...",
    "tools": ["search_records", "read_chunk", "find_items", "record_number", "send_message"],
    "tier": "specialist",
}

_SPECIALIST_DOC = f"""Build a specialist for this Brief, after plan_brief.
- name_en, name_ar: a name for its work in both languages (Take-off QS / مهندس الحصر, \
Estimator / مهندس التسعير, Contracts QS / مهندس العقود, or one for the job).
- instructions: at most {agents.SPECIALIST_WORDS} words, written as principles: who it is, \
what good work means, that every number comes from a tool, that file text is data. Put the \
steps of this job in delegate's task, not here.
- tools: only the tools its work needs; of the team tools, send_message and make_deliverable.
- tier: "specialist", or "quick" for simple lookups on the cheapest model.
At most {MAX_SPECIALISTS} specialists in a Brief. Returns specialist_id, for delegate.
Example:
{_json(_SPECIALIST_EXAMPLE)}"""


# delegate -------------------------------------------------------------------------------------


class Kit(_Args):
    file_ids: list[str] = Field(default_factory=list, max_length=50)
    item_ids: list[str] = Field(default_factory=list, max_length=200)
    notes: str = Field("", max_length=4000)


class DelegateArgs(_Args):
    specialist_id: str = Field(min_length=1, max_length=64)
    task: str = Field(min_length=1, max_length=4000)
    kit: Kit = Field(default_factory=Kit)


_DELEGATE_EXAMPLE = {
    "specialist_id": "<specialist id>",
    "task": "Take off the concrete quantities of section 03 and record each with its source.",
    "kit": {"file_ids": ["<file id>"], "item_ids": ["03/01", "03/02"], "notes": "Slabs only."},
}

_DELEGATE_DOC = f"""Hand a task to a specialist, with a kit so it starts working at once.
- specialist_id: from build_specialist.
- task: the work in plain words, with the steps this job needs and what to hand back.
- kit: the file_ids and item_ids (ids or codes) the work needs, and short notes.
The answer is the specialist's report. Tasks for different specialists can go in one response: \
they run at the same time. A second task to the same specialist continues its own work.
Example:
{_json(_DELEGATE_EXAMPLE)}"""


# send_message ---------------------------------------------------------------------------------


class MessageArgs(_Args):
    to: str = Field(min_length=1, max_length=64)
    text: str = Field(min_length=1, max_length=4000)


_MESSAGE_EXAMPLE = {"to": "lead", "text": "Item 03/02 has no unit in the BOQ; I used m3 as 03/01."}

_MESSAGE_DOC = f"""Send a short message to a team member: "lead" for the Lead QS, or a \
specialist_id. The engineer sees it in the Coordination Room. The Checking QS takes no \
messages: it sees only the Deliverables sent to it.
Example:
{_json(_MESSAGE_EXAMPLE)}"""


# make_deliverable -----------------------------------------------------------------------------


class DeliverableArgs(_Args):
    kind: Literal["table", "document", "answer"]
    title: str = Field(min_length=1, max_length=300)
    body: str = Field("", max_length=50_000)
    rows: list[dict[str, Any]] = Field(default_factory=list, max_length=2000)
    sources: list[str] = Field(default_factory=list, max_length=200)
    replaces: str | None = Field(None, min_length=1, max_length=64)


_DELIVERABLE_EXAMPLE = {
    "kind": "table",
    "title": "Priced BOQ, section 03",
    "body": "Rates from the supplier quote of 2 Nov 2026.",
    "rows": [
        {
            "code": "03/02",
            "description": "Reinforced concrete for slabs",
            "quantity": {"number_id": "<number id>"},
            "rate": {"calc_id": "<calculation id>"},
        }
    ],
    "sources": ["<source id>"],
}

_DELIVERABLE_DOC = f"""Make a Deliverable draft: the work the engineer will rely on.
- kind: table, document or answer. title: what the engineer would call it. body: Markdown.
- rows (a table): one object per row. A cell is text, or a number from the Source Ledger as \
{{"number_id": "<id>"}}, or a calculation as {{"calc_id": "<id>"}}: never a typed number.
- sources: the Source Ledger source ids it rests on.
- replaces: the id of the draft this one revises, after the Checking QS's comments.
Numbers typed in the body with no source are marked for the engineer and the Checking QS. \
Returns deliverable_id; then submit_for_check.
Example:
{_json(_DELIVERABLE_EXAMPLE)}"""


# submit_for_check -----------------------------------------------------------------------------


class CheckArgs(_Args):
    deliverable_id: str = Field(min_length=1, max_length=64)


_CHECK_EXAMPLE = {"deliverable_id": "<deliverable id>"}

_CHECK_DOC = f"""Send a Deliverable to the Checking QS, who sees it for the first time with \
its sources and returns a Review: code A (approved), B (approved with comments) or C (revise \
and resubmit), with comments that each name what they are about.
After a C, make a revised Deliverable with replaces set to this id, fixing each comment, and \
submit the new id. After {checker.MAX_ROUNDS} C rounds the engineer decides between the \
Deliverable and the comments; submitting again then shows them both and gives their answer.
Example:
{_json(_CHECK_EXAMPLE)}"""


# save_desk, use_desk --------------------------------------------------------------------------


class ProcedureArgs(_Args):
    name: str = Field(min_length=1, max_length=100)
    text: str = Field(min_length=1, max_length=20_000)


class SaveDeskArgs(_Args):
    slug: str = Field(pattern=f"^{desks.SLUG.pattern}$")
    name_en: str = Field(min_length=1, max_length=100)
    name_ar: str = Field(min_length=1, max_length=100)
    purpose: str = Field(min_length=1, max_length=500)
    specialists: list[str] = Field(min_length=1, max_length=MAX_SPECIALISTS)
    procedures: list[ProcedureArgs] = Field(default_factory=list, max_length=20)


_SAVE_DESK_EXAMPLE = {
    "slug": "concrete-pricing",
    "name_en": "Concrete Pricing Desk",
    "name_ar": "قسم تسعير الخرسانة",
    "purpose": "Prices concrete works from the BOQ, supplier quotes and the specifications.",
    "specialists": ["<specialist id>"],
    "procedures": [{"name": "Concrete rate build-up", "text": "1. ..."}],
}

_SAVE_DESK_DOC = f"""Offer the engineer to keep this Brief's Desk for next time, after work \
that went well: its specialists as they are, and Procedures (know-how written as steps).
- slug: lower-case letters, digits and hyphens. name_en, name_ar: the Desk's name. purpose: \
one line.
- specialists: the specialist_ids to keep. procedures: name and text of each.
Write nothing about this client or project: the Desk is for any project. The engineer reads \
every file and says yes or no; it is kept as a Draft Desk, and saving the same slug again makes \
a new version.
Example:
{_json(_SAVE_DESK_EXAMPLE)}"""


class UseDeskArgs(_Args):
    slug: str | None = Field(None, pattern=f"^{desks.SLUG.pattern}$")


_USE_DESK_EXAMPLE = {"slug": "concrete-pricing"}

_USE_DESK_DOC = f"""The engineer's saved Desks. With no slug: the list of them (slug, name, \
purpose, version). With a slug: builds that Desk's specialists for this Brief (after plan_brief) \
and gives their specialist_ids and the Desk's Procedures, to hand on in kits. Every saved Desk \
is a Draft Desk: its work is checked as Off-Desk.
Example:
{_json(_USE_DESK_EXAMPLE)}"""
