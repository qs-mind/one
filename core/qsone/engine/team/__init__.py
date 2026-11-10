"""The team tools. Importing this module registers them.

- `plan_brief`: the Brief Budget, asked above the `budget_above` line. The Lead calls it before it
  builds anyone.
- `build_specialist`: a specialist for this Brief, under a size test and a tool check. The Lead
  never builds the Checking QS. A Brief has at most 6 specialists.
- `delegate`, `submit_for_check`: deferred. The Brief Runner runs them through `tools.call`,
  which calls `host.run_specialist` / `host.run_checker`.
- `send_message`, `make_deliverable`: for specialists too.
- `save_desk`, `use_desk`: the engineer's saved Desks, written only after their yes.

What the team tools need beyond the `ToolContext` (the Model Data Sheet, the role models, the
measured tokens per request) the Brief Runner gives as `host.setup`, a `TeamSetup`.

A specialist is stored as an agent run of its Brief, built but not yet run (status "ready"),
whose parent is the run that built it; `spec.id` names it and `specialist_run` finds its run.
Refusals go back as `ModelRetry` and say exactly what to send; the engineer's "no" is `Denied`.
No cost is ever said to a model (Mizan rule 9): the Brief Budget is the engineer's card only."""

# One module per responsibility; this file only gathers their names, as `team.py` held them:
# - `common`: the tools' names and limits, `TeamSetup`, and the helpers every tool shares.
# - `stored`: the team as stored, and the numbers that have a source in the Brief.
# - `schemas`: each tool's arguments, example and description.
# - `handlers`: what each tool does. It owns `uuid4`: to fix the ids the tools make, patch
#   `handlers.uuid4`; the `uuid4` below is only the name `team.py` showed.
# - `registration`: registers the eight tools, once, when the package is imported.

import asyncio  # noqa: F401
import json  # noqa: F401
import re  # noqa: F401
from dataclasses import dataclass, replace  # noqa: F401
from typing import Any, Literal  # noqa: F401
from uuid import uuid4  # noqa: F401

from pydantic import BaseModel, ConfigDict, Field  # noqa: F401

from qsone import copy, settings  # noqa: F401
from qsone.clientfile import imported  # noqa: F401
from qsone.deliverables import review as deliverable_review  # noqa: F401
from qsone.deliverables import tools as outputs  # noqa: F401
from qsone.engine import agents, checker, desks, numbers_guard, truth  # noqa: F401
from qsone.engine.costs import brief_budget, caps, usd_text  # noqa: F401
from qsone.engine.store import Store  # noqa: F401
from qsone.engine.tools import REGISTRY, Denied, ModelRetry, Tool, ToolContext, register  # noqa: F401
from qsone.engine.types import (  # noqa: F401
    AgentSpec,
    Card,
    CheckPacket,
    DeliverableDraft,
    ModelCard,
    ModelChoice,
    Review,
    Reviewed,
    Role,
    TeamMessage,
    Text,
)
from qsone.records.project import RecordsError  # noqa: F401

from .common import (  # noqa: F401
    MAX_SPECIALISTS,
    PLANNED,
    READY,
    SPECIALIST_TEAM_TOOLS,
    TEAM_TOOLS,
    TeamSetup,
    _Args,
    _ask,
    _join,
    _json,
    _setup,
)
from .handlers import (  # noqa: F401
    _CHECKER_AR,
    _CHECKER_EN,
    _build,
    _build_specialist,
    _cell_text,
    _cells,
    _check_kit,
    _check_output,
    _check_refs,
    _delegate,
    _disagreement,
    _is_checker,
    _is_settled,
    _make_deliverable,
    _plan_brief,
    _review_json,
    _save_desk,
    _send_message,
    _submit_for_check,
    _use_desk,
    check_deliverable,
    specialist_tools,
)
from .registration import _LEAD, _TEAM, _tool  # noqa: F401
from .schemas import (  # noqa: F401
    _CHECK_DOC,
    _CHECK_EXAMPLE,
    _DELEGATE_DOC,
    _DELEGATE_EXAMPLE,
    _DELIVERABLE_DOC,
    _DELIVERABLE_EXAMPLE,
    _MESSAGE_DOC,
    _MESSAGE_EXAMPLE,
    _PLAN_DOC,
    _PLAN_EXAMPLE,
    _SAVE_DESK_DOC,
    _SAVE_DESK_EXAMPLE,
    _SPECIALIST_DOC,
    _SPECIALIST_EXAMPLE,
    _USE_DESK_DOC,
    _USE_DESK_EXAMPLE,
    CheckArgs,
    DelegateArgs,
    DeliverableArgs,
    Kit,
    MessageArgs,
    PlanArgs,
    PlanStep,
    ProcedureArgs,
    SaveDeskArgs,
    SpecialistArgs,
    UseDeskArgs,
)
from .stored import (  # noqa: F401
    _known,
    _maker,
    _specialist,
    _unsourced,
    specialist_run,
    specialists,
)

# isort: split
from . import keep  # noqa: E402, F401 - registers keep_member (Phase 1, C5)
