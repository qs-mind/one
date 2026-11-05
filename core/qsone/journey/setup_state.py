"""The first launch's steps and the AI consent, in settings.json (decisions 23 and 26).

- `setup`: {step: "done" | "skipped"} for each step the engineer passed; `setup_done_at` once
  every step has one. Skipping a step is as good as doing it: the app works either way.
- `ai_consent`: {at, text_version}. Every AI call refuses with AI_CONSENT_NEEDED until it holds
  the current `CONSENT_VERSION`; when the consent text changes, the version goes up and the
  engineer is asked again.
- `language`: the screen's language as the engineer chose it in the first step ("ar" or "en"),
  for the outside links and Usage Stats. Until then, the system's language.

Importing this module adds the consent check to `costs.AI_CALL_CHECKS`, the one list every AI
call passes before it goes.
"""

import locale
from typing import Literal

from qsone import copy, settings
from qsone.engine import costs
from qsone.engine.types import ModelChoice, Text
from qsone.records.project import RecordsError, utc_now

STEPS = ("language", "account", "ai", "card", "usage")
CONSENT_VERSION = 1  # goes up when the consent text on the screen changes

State = Literal["done", "skipped"]
Language = Literal["ar", "en"]


def _steps() -> dict[str, State]:
    saved = settings.load().get("setup")
    saved = saved if isinstance(saved, dict) else {}
    return {s: saved[s] for s in STEPS if saved.get(s) in ("done", "skipped")}


def setup() -> dict:
    """{"done": bool, "steps": {step: "done" | "skipped" | None}}."""
    passed = _steps()
    return {"done": len(passed) == len(STEPS), "steps": {s: passed.get(s) for s in STEPS}}


def mark(step: str, state: State) -> dict:
    """Saves one step's state; the first time every step has one, `setup_done_at` is kept.
    Raises `KeyError` for an unknown step and `OSError` when settings.json cannot be written."""
    if step not in STEPS:
        raise KeyError(step)
    passed = _steps() | {step: state}
    settings.save("setup", passed)
    if len(passed) == len(STEPS) and not settings.load().get("setup_done_at"):
        settings.save("setup_done_at", utc_now())
    return setup()


def language() -> Language:
    """The screen's language: as the engineer chose it, else the system's (ar* is Arabic)."""
    chosen = settings.load().get("language")
    if chosen in ("ar", "en"):
        return chosen
    found = locale.getlocale()[0] or ""
    return "ar" if found.lower().startswith("ar") else "en"


def set_language(lang: Language) -> None:
    """Raises `OSError` when settings.json cannot be written."""
    settings.save("language", lang)


# The AI consent ------------------------------------------------------------------------------


def consent() -> dict | None:
    """{"at", "text_version"} when the engineer said yes to the current text, else None."""
    saved = settings.load().get("ai_consent")
    if not isinstance(saved, dict):
        return None
    version = saved.get("text_version")
    at = saved.get("at")
    if not isinstance(at, str) or not isinstance(version, int) or version < CONSENT_VERSION:
        return None
    return {"at": at, "text_version": version}


def give_consent(text_version: int) -> dict:
    """The engineer said yes to the text of `text_version`. Raises `OSError` when settings.json
    cannot be written. An older version is kept but does not count (`consent` stays None)."""
    given = {"at": utc_now(), "text_version": text_version}
    settings.save("ai_consent", given)
    return given


def require_consent() -> None:
    """Raises `RecordsError(AI_CONSENT_NEEDED, 409)` until the engineer said yes."""
    if consent() is None:
        raise RecordsError(copy.AI_CONSENT_NEEDED, status=409)


def _check(choice: ModelChoice) -> Text | None:
    return copy.AI_CONSENT_NEEDED if consent() is None else None


costs.AI_CALL_CHECKS.append(_check)
