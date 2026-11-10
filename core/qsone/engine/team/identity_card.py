"""A member the Lead proposes for a tender (`MemberDraft`), and the checks its identity passes
before it is stored: every field in both languages, a title that joins a QS term with a role, a
speciality that joins one with an agentic term, no person's name, never a checker, and only the
tools a specialist may have. A refusal is a `RecordsError` that names the field."""

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from qsone import copy
from qsone.records import arabic
from qsone.records.project import RecordsError

from .handlers import _is_checker, specialist_tools


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Pair(_Strict):
    """Loose on purpose: a missing language comes back as a refusal with words."""

    en: str = Field("", max_length=2000)
    ar: str = Field("", max_length=2000)


class MemberDraft(_Strict):
    """A permanent member brought in by `member_id`, or a new one described in full."""

    member_id: str | None = Field(None, min_length=1, max_length=64)
    name: Pair | None = None
    title: Pair | None = None
    speciality: Pair | None = None
    style: Pair | None = None
    tools: list[str] = Field(default_factory=list, max_length=40)
    tier: Literal["specialist", "quick"] = "specialist"


IDENTITY_FIELDS = ("name", "title", "speciality", "style")
LIMITS = {"name": 60, "title": 100, "speciality": 160, "style": 300}  # characters

# A title's role, and a speciality's agentic term, in each language; the QS term is what is
# left beside it.
_ROLE_EN = re.compile(
    r"\b(quantity surveyors?|qs|estimators?|engineers?|surveyors?|managers?|planners?)\b", re.I
)
_ROLE_AR = re.compile("مهندس كميات|مهندس|مساح كميات|مساح|مقدر|مدير|مخطط|أخصائي|اخصائي")
_AGENT_EN = re.compile(r"\bagent(s|ic)?\b", re.I)
_AGENT_AR = re.compile("وكيل|وكلاء")

# A person's name: a form of address, a family particle, or a common given name. A guard, not a
# full list: the words are whole words, chosen so that none is also a QS or an everyday word.
_ADDRESS_EN = re.compile(r"\b(mr|mrs|ms|miss|dr|eng|prof|sir|madam|bin|ibn|bint|abu)\b", re.I)
_ADDRESS_AR = re.compile(r"(^|\s)[مدأ]\s*/\s*\S")
_GIVEN_EN = frozenset(
    "ahmed ahmad mohamed mohammed muhammad mahmoud mostafa mustafa khaled khalid omar youssef "
    "yousef yusuf ibrahim tarek tariq hisham hossam karim kareem amr hussein fatma fatima "
    "mariam maryam sara sarah john david michael james robert william mary sophie emma peter "
    "paul george adam alex jack anna laura maria".split()
)
_GIVEN_AR = frozenset(
    arabic.normalise(word, stem=False)
    for word in (
        "السيد السيدة الأستاذ الأستاذة الدكتور الدكتورة بن ابن بنت أبو محمد أحمد محمود مصطفى "
        "خالد عمرو يوسف إبراهيم طارق هشام حسام حسين فاطمة مريم سارة جون ديفيد مايكل ماري "
        "بيتر جورج آدم"
    ).split()
)


def _bad(text: dict, field: str, **values) -> RecordsError:
    return RecordsError(copy.fill(text, field=field, **values), status=422, field=field)


def names_a_person(text: str) -> bool:
    """True when `text` holds a form of address or a common given name, in either language."""
    if _ADDRESS_EN.search(text) or _ADDRESS_AR.search(text):
        return True
    words = re.findall(r"[A-Za-z]+", text)
    if any(word.lower() in _GIVEN_EN for word in words):
        return True
    return any(word in _GIVEN_AR for word in arabic.normalise(text, stem=False).split())


def _joins(text: str, role: re.Pattern) -> bool:
    """`role` is in `text`, and at least one more word: the QS term it joins."""
    rest, found = role.subn(" ", text, count=1)
    return bool(found) and bool(re.search(r"\w", rest))


def check_identity(draft: MemberDraft, at: str) -> dict:
    """The identity card of a new member, as stored. `at` is where it sits in the team
    ("team[0]"). Raises `RecordsError` (422) naming the field."""
    card: dict = {}
    for name in IDENTITY_FIELDS:
        pair = getattr(draft, name)
        for lang in ("en", "ar"):
            field = f"{at}.{name}.{lang}"
            value = "" if pair is None else getattr(pair, lang)
            if not value:
                raise _bad(copy.IDENTITY_NEEDS_BOTH, f"{at}.{name}")
            if len(value) > LIMITS[name]:
                raise _bad(copy.IDENTITY_TOO_LONG, field, limit=LIMITS[name])
            if names_a_person(value):
                raise RecordsError(copy.IDENTITY_NO_PERSON_NAME, status=422, field=field)
        card[name] = {"en": pair.en, "ar": pair.ar}
    title, speciality = card["title"], card["speciality"]
    if not (_joins(title["en"], _ROLE_EN) and _joins(title["ar"], _ROLE_AR)):
        raise _bad(copy.IDENTITY_TITLE_NO_ROLE, f"{at}.title")
    if not (_joins(speciality["en"], _AGENT_EN) and _joins(speciality["ar"], _AGENT_AR)):
        raise _bad(copy.IDENTITY_SPECIALITY_NO_AGENT, f"{at}.speciality")
    if _is_checker(card["name"]) or _is_checker(title):
        raise RecordsError(copy.IDENTITY_NO_CHECKER, status=422, field=f"{at}.name")
    allowed = specialist_tools()
    unknown = [t for t in draft.tools if t not in allowed]
    if unknown:
        raise _bad(copy.IDENTITY_TOOL_UNKNOWN, f"{at}.tools", tools=", ".join(unknown))
    return card | {"tools": list(dict.fromkeys(draft.tools)), "tier": draft.tier}
