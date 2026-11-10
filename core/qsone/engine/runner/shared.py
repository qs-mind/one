import logging
from datetime import UTC, datetime

from qsone import copy
from qsone.engine.runner.errors import NoAI
from qsone.engine.types import ModelCard, Text
from qsone.records.project import Records

log = logging.getLogger("qsone.engine.runner")

GENERAL = "general"  # the General chat's id; it lives in the Engineer Records file
WORK = "claude-work"  # <data>/claude-work/<run id>/: one Claude Code run's folder
TOOL_RETRIES = 3  # how often a model may fix one tool call, or its final answer
_ROLE_NAMES: dict[str, Text] = {
    "lead": copy.ROLE_LEAD,
    "checker": copy.ROLE_CHECKER,
    "specialist": copy.ROLE_SPECIALIST,
    "quick": copy.ROLE_QUICK,
}


def utc_now() -> datetime:
    return datetime.now(UTC)


def kept_here(rec: Records | None, sheet: list[ModelCard]) -> list[ModelCard]:
    """The models work in `rec` may use: only those on this computer when nothing may leave it
    (`tools.services.stays_here`). Raises `NoAI` when there is none."""
    from qsone.tools.services import stays_here

    if not stays_here(rec):
        return sheet
    found = [c for c in sheet if c.on_device]
    if not found:
        raise NoAI(copy.CONFIDENTIAL_NO_LOCAL_AI)
    return found
