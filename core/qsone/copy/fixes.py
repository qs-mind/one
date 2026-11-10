"""What the screen can add to a text: the action that fixes it (`FIXES`, `fix_of`, `error`)."""

import re

from qsone.copy.ai import (
    AI_BUSY,
    AI_CHECK_FAILED,
    AI_KEY_REFUSED,
    AI_NO_CONNECTION,
    CLAUDE_BUSY,
    CLAUDE_CODE_MISSING,
    CLAUDE_CODE_SHIM,
    CLAUDE_CODE_SIGNED_OUT,
    CLAUDE_CODE_TOO_OLD,
    KEY_REFUSED,
    KEY_STORE_DOWN,
    MODEL_GONE,
    MODEL_GONE_TRY,
    MODELS_FAILED,
    NO_AI,
    NO_CONNECTION,
    NO_KEY,
)
from qsone.copy.journey import AI_CONSENT_NEEDED, ARCHIVE_BACKUP_FAILED, CLAUDE_CODE_NOT_FOUND
from qsone.copy.projects import PROJECT_KEY_STORE_DOWN
from qsone.copy.spending import PRICE_UNKNOWN
from qsone.copy.web import WEB_NO_SEARCH, WEB_SEARCH_KEY_REFUSED, WEB_SEARCH_LIMIT

# ---------------------------------------------------------------------------------------------
# What the screen can add to a text: the action that fixes it, for the place it shows in.
# "ai": AI settings ("Open AI settings" in the chat; nothing more in AI settings or the first
# launch's Connect AI, where the fix is already in place). "consent": the first launch's Connect
# AI step. "retry": the same check once more ("Try again"). "backup": the Backup panel.
# ---------------------------------------------------------------------------------------------
FIXES = {
    "ai": (
        NO_KEY,
        KEY_REFUSED,
        NO_AI,
        AI_KEY_REFUSED,
        PRICE_UNKNOWN,
        MODEL_GONE_TRY,
        MODEL_GONE,
    ),
    # the web search setting, in AI settings (audit B8)
    "search": (WEB_NO_SEARCH, WEB_SEARCH_KEY_REFUSED, WEB_SEARCH_LIMIT),
    "consent": (AI_CONSENT_NEEDED,),
    "retry": (
        KEY_STORE_DOWN,
        PROJECT_KEY_STORE_DOWN,
        NO_CONNECTION,
        CLAUDE_BUSY,
        MODELS_FAILED,
        AI_NO_CONNECTION,
        AI_BUSY,
        AI_CHECK_FAILED,
        CLAUDE_CODE_MISSING,
        CLAUDE_CODE_TOO_OLD,
        CLAUDE_CODE_SHIM,
        CLAUDE_CODE_SIGNED_OUT,
        CLAUDE_CODE_NOT_FOUND,
    ),
    "backup": (ARCHIVE_BACKUP_FAILED,),
}


def _shape(text: dict[str, str]) -> re.Pattern:
    """The English words of `text`, with any value in each {placeholder}."""
    pieces = re.split(r"\{[a-z_]+\}", text["en"])
    return re.compile(".+?".join(re.escape(piece) for piece in pieces), re.S)


_FIX_SHAPES = [(fix, _shape(text)) for fix, found in FIXES.items() for text in found]


def fix_of(text: object) -> str | None:
    """The action that fixes `text` (one of FIXES, filled or not), or None."""
    if not isinstance(text, dict) or not isinstance(text.get("en"), str):
        return None
    return next((fix for fix, shape in _FIX_SHAPES if shape.fullmatch(text["en"])), None)


def error(text: dict[str, str]) -> dict:
    """A JSON error body: `{"error": text}`, and its `fix` when the screen can add one."""
    fix = fix_of(text)
    return {"error": text} if fix is None else {"error": text, "fix": fix}
