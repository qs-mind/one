import logging
from datetime import UTC, datetime

from qsone import copy
from qsone.engine.types import Text

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
