"""A Problem: one thing a reply says that the records do not show."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Problem:
    """One thing a reply says that the records do not show. `fix` is English, for the model;
    `flag` is the engineer's line, {en, ar}, or None when only the model needs to hear it."""

    kind: str
    fix: str
    flag: dict | None = None
