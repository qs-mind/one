"""The Brief Runner: each engineer message is a Brief, run as a background task that no HTTP
request owns.

- **Durable steps.** Each agent run's Checkpoint is its own message history, saved in the
  project's encrypted file after every model response and every tool round. `delegate` and
  `submit_for_check` are PydanticAI deferred calls: the runner runs them (specialists in
  parallel, at most `max_agents` agents at once across all Briefs), stores each result as it
  finishes, and resumes the Lead with `deferred_tool_results`. Continue rebuilds every run from
  its Checkpoint: a history that ends in a response with inline tool calls not yet answered is
  cut back to its last request, so at most one model request is redone; a replayed write tool
  call never writes twice (`tools.call`). A fresh launch never continues anything by itself.
- **The Subscription Link.** A run on the engineer's Claude Code is a job with its own MCP token;
  its deferred tools run inside the MCP call. It keeps no history in One, so the runner keeps a
  mirror of it (its task, each tool call and result, its answer) as an ordinary history, for the
  numbers guard and for the Lead of the next Brief.
- **Stop, steer, failures.** Stop cancels the Brief's task, which reaches every agent of it
  (Claude Code is interrupted, then terminated, then killed). A message sent while it runs is
  enqueued into the running Lead. A provider that is down is tried once more after 5 s, then
  the role moves to a model of the same price or cheaper (a costlier one asks); no internet
  waits 5, 15, 30, 60 s, then every 60 s; a refused key fails plainly; a Spending Cap stops it.
- **The end.** The numbers guard marks typed numbers with no source in the Lead's reply, and
  every unchecked Deliverable with numbers goes to the Checking QS before the Brief is done.

Its events reach the screen through `events` (replayed from the start, then live) and
`stream.ui_stream`; the team and its state reach Plan 7's canvas through `activity`.
Never logs Brief text, messages, cards or tool arguments: only ids and states."""

# ruff: noqa: F401

import asyncio
import json
import logging
import re
import shutil
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP
from pathlib import Path
from typing import Any
from uuid import uuid4

import anthropic
import openai
from pydantic_ai import Agent, DeferredToolRequests, DeferredToolResults, ModelRetry, ToolFailed
from pydantic_ai.exceptions import (
    ModelAPIError,
    ModelAuthenticationError,
    ModelConnectionError,
    ModelHTTPError,
    ModelRateLimitError,
    ModelRequestTimeout,
    ModelServerError,
    ModelUnavailableError,
    UnexpectedModelBehavior,
    UsageLimitExceeded,
)
from pydantic_ai.messages import (
    ModelMessagesTypeAdapter,
    ModelRequest,
    ModelResponse,
    PartDeltaEvent,
    PartStartEvent,
    RetryFeedbackPart,
    RetryPromptPart,
    TextPart,
    TextPartDelta,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.settings import ModelSettings
from pydantic_ai.usage import UsageLimits

from qsone import activity, copy, usage, view
from qsone.deliverables import tools as outputs
from qsone.engine import (
    agents,
    cards,
    checker,
    desks,
    focus,
    general,
    numbers_guard,
    oneshot,
    roles,
    selection,
    team,
    tool_groups,
    tools,
    truth,
)
from qsone.engine import connectors as connectors_mod
from qsone.engine.costs import CallRefused, CapReached, CostedModel, Spending
from qsone.engine.data_text import as_data, new_fence
from qsone.engine.mcp_server import McpGate, RunScope
from qsone.engine.store import UNFINISHED, CostBook, Store
from qsone.engine.team import TeamSetup
from qsone.engine.tools import DENIED, REGISTRY, Denied, ToolContext
from qsone.engine.types import (
    AgentSpec,
    Asked,
    BriefState,
    Card,
    CheckPacket,
    Data,
    Effort,
    Event,
    ModelCard,
    ModelChoice,
    Progress,
    Review,
    Reviewed,
    Role,
    Settled,
    Status,
    TeamMessage,
    Text,
    TextDelta,
    Unsourced,
    brief_language,
    choice_of,
    reply_line,
)
from qsone.engine.worklog import WorkLog
from qsone.journey import engineer, understand
from qsone.projects import Projects
from qsone.records.project import Records, RecordsError

from .brief import _Brief, _Place
from .engine import Engine, _chat_activity
from .errors import BriefBusy, NoAI, _Busy, _Fail
from .failures import _REPLY_GAVE_UP, _TOOL_GAVE_UP, BUSY_WAIT, OFFLINE_WAITS, _error_kind
from .histories import (
    NOT_DONE,
    STEPS_NOTE,
    _answered,
    _calls,
    _deferred,
    _dump,
    _last_response,
    _load,
    _refused,
    _sent_back,
    _tool_results,
    cut_back,
    final_text,
    heard,
    lead_text,
    outcomes,
    pending_deferred,
    settled,
)
from .lead import _DEFERRED, REPORT_LIMIT, STEP_LIMIT, _result_value
from .link import _agent_job
from .shared import _ROLE_NAMES, GENERAL, TOOL_RETRIES, WORK, log, utc_now
from .specialists import REVIEW_AS_JSON, SPECIALIST_RULES
from .steps import _RECORD_ID
from .stored import (
    _first_said,
    _report_message,
    _stored_events,
    _with_reports,
    question_id,
    reply_id,
)
from .team_view import _AgentState
from .truth_checks import _NO_SEARCH_SAID, _descriptions, _marked, _no_search_notice
