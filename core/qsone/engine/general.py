"""The Engineer Records file at `<data>/engineer/`: the General chat and the cost book. And the
General chat's own Lead QS (Plan 7): three tools of its own, and no tool that needs a project.

It is a Records file like a project's, with the same schema and its own key in the key store,
but it is not under `projects/`, so `Projects.list()` never sees it. Plan 8 opens the same
folder; whichever comes first creates it.

In the General chat the Lead QS lists the projects that are not Confidential (`projects`), hands
a request to one (`hand_to_project`) or offers a new one (`offer_new_project`). The last two only
show a card (`data-hand-off`): nothing moves and nothing is created until the engineer clicks.
Importing this module registers the three tools."""

import json
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from pydantic import StringConstraints

from qsone import copy
from qsone.backup.keys import Escrow
from qsone.engine import agents
from qsone.engine.tools import REGISTRY, ToolContext, register_functions
from qsone.engine.tools_records import RECORDS_TOOLS
from qsone.engine.types import AgentSpec, Data
from qsone.records import engineer as engineer_file
from qsone.records.project import Records, RecordsError

FOLDER = engineer_file.FOLDER
NAME = engineer_file.NAME
HAND_OFF = "hand-off"  # the card's data part: `data-hand-off`


def open_engineer_records(
    data_dir: Path, escrow: Callable[[], Escrow | None] = lambda: None
) -> Records:
    """Creates the file on first use and opens it otherwise (`records/engineer.py`, with its own
    key per data folder). Raises `RecordsError`. Close it when done."""
    return engineer_file.open_records(Path(data_dir), escrow)


# The three tools -------------------------------------------------------------------------------

Request = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


def _listed(ctx: ToolContext) -> list[dict]:
    return [
        {"id": p["id"], "name": p["name"]}
        for p in ctx.projects.list()
        if "error" not in p and not p["confidential"]
    ]


def _card(ctx: ToolContext, data: dict) -> dict:
    card_id = uuid4().hex
    ctx.host.emit(Data(ctx.brief_id, HAND_OFF, card_id, data))
    return {"id": card_id} | data


def projects(ctx: ToolContext) -> list[dict]:
    """The engineer's projects on this computer that you may name, newest first:
    [{"id", "name"}]. A Confidential Project is never listed. Call it before naming or handing
    anything to a project."""
    return _listed(ctx)


def hand_to_project(ctx: ToolContext, project_id: str, request: Request) -> dict:
    """Offer to continue the engineer's request in its project. The engineer sees a card
    "Continue in «project»?" and decides; nothing moves until they click.
    - project_id: an id from `projects`.
    - request: the request as the project chat should get it, in the engineer's words and
      language.
    Example: {"project_id": "<id from projects>", "request": "سعّر بنود الخرسانة"}"""
    found = {p["id"]: p for p in _listed(ctx)}.get(project_id)
    if found is None:
        known = any(p["id"] == project_id for p in ctx.projects.list())
        text = copy.PROJECT_IS_CONFIDENTIAL if known else copy.PROJECT_NOT_FOUND
        raise RecordsError(text, status=409 if known else 404, field="project_id")
    data = {"kind": "project", "project_id": project_id, "name": found["name"], "request": request}
    return _card(ctx, data)


def offer_new_project(ctx: ToolContext, name: Name, request: Request) -> dict:
    """Offer a new project when no project from `projects` fits the request. The engineer sees
    a card "Create «name»?" and decides; nothing is created until they click.
    - name: a short project name, in the engineer's language.
    - request: the request the new project's chat should get.
    Example: {"name": "فيلا التجمع", "request": "احصر كميات الخرسانة من اللوحات"}"""
    return _card(ctx, {"kind": "new_project", "name": name, "request": request})


register_functions(
    "general", [projects, hand_to_project, offer_new_project], roles={"lead"}, risk="read"
)
GENERAL_TOOLS = ("projects", "hand_to_project", "offer_new_project")
_CARDS = ("hand_to_project", "offer_new_project")

GENERAL_LINE = (
    "This is the General chat: no project is open. Hand project work to its project with "
    "hand_to_project, offer a new project with offer_new_project when none fits, and never "
    "name a project that projects did not return. Market news, prices and suppliers you search "
    "yourself: web_search, then web_read for each page you use, and cite it; never give a "
    "remembered price as today's."
)


def project_only() -> set[str]:
    """The Lead's tools that need an open project: Project Records (Plan 4 and the `records`
    group), the BOQ import (Plan 5's `boq` group) and the Deliverables (Plan 6)."""
    from qsone.deliverables.tools import OUTPUTS_TOOLS

    grouped = {name for name, tool in REGISTRY.items() if tool.group in ("records", "boq")}
    return {*RECORDS_TOOLS, *OUTPUTS_TOOLS, *grouped}


def lead_spec() -> AgentSpec:
    """The Lead QS of the General chat: its own instructions plus one line; its tools without
    the project ones (the team and the engineer's own tools stay), plus the three above and the
    web tools. A project's Lead gives web work to a specialist to keep its context small
    (decision 7); here there is no project context, and a question about the market is the
    Lead's own (without them it told the engineer ONE cannot search the web)."""
    from qsone.tools.web import WEB_TOOLS

    lead = agents.lead_spec()
    dropped = project_only()
    tools = (*(name for name in lead.tools if name not in dropped), *GENERAL_TOOLS, *WEB_TOOLS)
    return replace(lead, instructions=f"{lead.instructions}\n\n{GENERAL_LINE}", tools=tools)


def stored_cards(brief_id: str, results: list[tuple[str, str]]) -> list[Data]:
    """The hand-off cards again, from the Lead's stored tool results (`agents.tool_returns`)."""
    found = []
    for name, text in results:
        if name not in _CARDS:
            continue
        try:
            data = json.loads(text)
        except ValueError:
            continue
        if isinstance(data, dict) and isinstance(data.get("id"), str):
            card_id = data.pop("id")
            found.append(Data(brief_id, HAND_OFF, card_id, data))
    return found
