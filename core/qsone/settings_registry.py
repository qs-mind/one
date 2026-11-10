"""Settings in one home (Phase 1, C10): every setting the screens show, where it is stored, its
recommended value and its words, in one table. The Settings screen (`PATCH /settings/{key}`) and
the Lead's `settings_set` tool change the same stored value through `change`, which checks it,
saves it at once and tells the screens (a `setting` event on the general channel).

A key is "<section>.<name>" with one dot. Values travel as the contract's: a toggle is a bool,
everything else text (a choice's value, or an exact decimal). A key or a secret is never a
setting: the AI links, the web search key and the backup have their own routes.

What the Lead may change without asking (contract Q20): anything that spends more, sends more out
or weakens a Confidential rule asks the engineer first (`asks_first`); the screen never asks.
"""

import locale
import re
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from qsone import activity, copy, settings, usage
from qsone import phase1_contract as c
from qsone.engine import costs, roles
from qsone.journey import setup_state
from qsone.records.project import RecordsError

Value = bool | str
Control = Literal["toggle", "choice", "money", "number"]

CHANNEL = "general"  # the activity channel the `setting` event goes to
_MONEY = re.compile(r"\d{1,12}(?:\.\d{1,6})?")  # exact USD, as the caps and the map allowance
_DECIMAL = re.compile(r"\d{1,3}(?:\.\d{1,3})?")
# Stored under these names in settings.json; the older values keep their names (the key table).
MODELS, ON_DEVICE, THEME = "ai_models", "confidential_on_device", "theme"


class Refused(RecordsError):
    """A refusal of the contract's shape: words, and the `field`, `example` and `brief_id`
    that apply (`phase1_contract.refusal`)."""

    def __init__(
        self,
        text: dict[str, str],
        status: int = 422,
        *,
        field: str | None = None,
        example: str | None = None,
        brief_id: str | None = None,
    ) -> None:
        super().__init__(text, status, field)
        self.example = example
        self.brief_id = brief_id


def answer(e: RecordsError):
    """The JSON answer for a refusal, with every key that applies."""
    return c.refusal(
        e.text,
        e.status,
        field=e.field,
        example=getattr(e, "example", None),
        brief_id=getattr(e, "brief_id", None),
    )


@dataclass(frozen=True)
class Entry:
    key: str
    control: Control
    title: dict[str, str]
    help: dict[str, str]
    read: Callable[[], Value]
    write: Callable[[Value], None]  # raises OSError
    recommended: Callable[[], Value]
    choices: tuple[tuple[str, dict[str, str]], ...] = ()
    bounds: tuple[str, str, str] = ("", "", "")  # a number's min, max and step
    spends_more: Literal["up", "off", "on", "any", "never"] = "never"  # when the Lead asks

    @property
    def section(self) -> str:
        return self.key.partition(".")[0]


def _saved(name: str, allowed: tuple, default):
    value = settings.load().get(name)
    return value if value in allowed else default


def _cap(name: str) -> Callable[[], Value]:
    return lambda: format(getattr(costs.caps(), name), "f")


def _save_cap(name: str) -> Callable[[Value], None]:
    def write(value: Value) -> None:
        costs.save_caps({name: value})

    return write


def _models() -> str:
    """As chosen; before any choice, `own` when the engineer has picked a model for a role."""
    return _saved(MODELS, ("recommended", "own"), "own" if roles.saved() else "recommended")


def _save_models(value: Value) -> None:
    settings.save(MODELS, value)
    if value == "recommended":
        settings.save_ai("roles", {})  # each role takes ONE's pick again (`roles.defaults`)


def _system_language() -> str:
    found = locale.getlocale()[0] or ""
    return "ar" if found.lower().startswith("ar") else "en"


def _zoom() -> str:
    from qsone.app import saved_zoom  # the app's own zoom (Ctrl/Cmd with = or -)

    return f"{saved_zoom():.1f}"


def _save_zoom(value: Value) -> None:
    from qsone.app import ZOOM_SETTING

    settings.save(ZOOM_SETTING, float(value))


def confidential_on_device() -> bool:
    """Whether a Confidential Project runs on a model on this computer only."""
    return settings.load().get(ON_DEVICE) is True


def _const(value: Value) -> Callable[[], Value]:
    return lambda: value


ENTRIES: tuple[Entry, ...] = (
    Entry(
        "ai.models",
        "choice",
        copy.SET_AI_MODELS,
        copy.SET_AI_MODELS_HELP,
        _models,
        _save_models,
        _const("recommended"),
        (("recommended", copy.SET_MODELS_RECOMMENDED), ("own", copy.SET_MODELS_OWN)),
        spends_more="any",
    ),
    Entry(
        "ai.confidential_on_device",
        "toggle",
        copy.SET_ON_DEVICE,
        copy.SET_ON_DEVICE_HELP,
        confidential_on_device,
        lambda value: settings.save(ON_DEVICE, value),
        _const(False),
        spends_more="off",
    ),
    *(
        Entry(
            f"caps.{name}_usd",
            "money",
            title,
            help_,
            _cap(name),
            _save_cap(name),
            _const(format(getattr(costs.RECOMMENDED, name), "f")),
            spends_more="up",
        )
        for name, title, help_ in (
            ("brief", copy.SET_CAP_BRIEF, copy.SET_CAP_BRIEF_HELP),
            ("day", copy.SET_CAP_DAY, copy.SET_CAP_DAY_HELP),
            ("month", copy.SET_CAP_MONTH, copy.SET_CAP_MONTH_HELP),
            ("budget_above", copy.SET_BUDGET_ABOVE, copy.SET_BUDGET_ABOVE_HELP),
        )
    ),
    Entry(
        "caps.map_auto_usd",
        "money",
        copy.SET_MAP_AUTO,
        copy.SET_MAP_AUTO_HELP,
        lambda: format(settings.map_auto_usd(), "f"),
        settings.save_map_auto_usd,
        _const("0.50"),
        spends_more="up",
    ),
    Entry(
        "caps.subscription_stops",
        "toggle",
        copy.SET_SUBSCRIPTION,
        copy.SET_SUBSCRIPTION_HELP,
        lambda: costs.caps().subscription_stops,
        _save_cap("subscription_stops"),
        _const(costs.RECOMMENDED.subscription_stops),
        spends_more="off",
    ),
    Entry(
        "privacy.usage_stats",
        "toggle",
        copy.SET_USAGE_STATS,
        copy.SET_USAGE_STATS_HELP,
        lambda: usage.is_on() is True,  # not asked yet is off
        usage.set_on,
        _const(False),
        spends_more="on",
    ),
    Entry(
        "look.language",
        "choice",
        copy.SET_LANGUAGE,
        copy.SET_LANGUAGE_HELP,
        setup_state.language,
        setup_state.set_language,
        _system_language,
        (("ar", copy.SET_LANGUAGE_AR), ("en", copy.SET_LANGUAGE_EN)),
    ),
    Entry(
        "look.theme",
        "choice",
        copy.SET_THEME,
        copy.SET_THEME_HELP,
        lambda: _saved(THEME, ("system", "light", "dark"), "system"),
        lambda value: settings.save(THEME, value),
        _const("system"),
        (
            ("system", copy.SET_THEME_SYSTEM),
            ("light", copy.SET_THEME_LIGHT),
            ("dark", copy.SET_THEME_DARK),
        ),
    ),
    Entry(
        "look.zoom",
        "number",
        copy.SET_ZOOM,
        copy.SET_ZOOM_HELP,
        _zoom,
        _save_zoom,
        _const("1.0"),
        bounds=("0.8", "1.5", "0.1"),
    ),
)
_BY_KEY = {entry.key: entry for entry in ENTRIES}


def entry(key: str) -> Entry:
    """Raises `Refused` (404 SETTING_NOT_FOUND) for a key ONE does not have."""
    found = _BY_KEY.get(key)
    if found is None:
        raise Refused(copy.SETTING_NOT_FOUND, 404, field="key")
    return found


def _same(e: Entry, a: Value, b: Value) -> bool:
    if e.control in ("money", "number"):
        return Decimal(str(a)) == Decimal(str(b))
    return a == b


def shown(e: Entry) -> c.ToggleSetting | c.ChoiceSetting | c.MoneySetting | c.NumberSetting:
    """The setting as the screen draws it: its value now, and its recommended one."""
    value, recommended = e.read(), e.recommended()
    base = {
        "key": e.key,
        "section": e.section,
        "title": e.title,
        "help": e.help,
        "at_recommended": _same(e, value, recommended),
        "control": e.control,
        "value": value,
        "recommended": recommended,
    }
    if e.control == "toggle":
        return c.ToggleSetting(**base)
    if e.control == "choice":
        choices = [c.SettingChoice(value=v, title=t) for v, t in e.choices]
        return c.ChoiceSetting(**base, choices=choices)
    if e.control == "money":
        return c.MoneySetting(**base, currency="USD")
    low, high, step = e.bounds
    return c.NumberSetting(**base, min=low, max=high, step=step)


def all_settings() -> c.Settings:
    return c.Settings(settings=[shown(e) for e in ENTRIES])


def parse(e: Entry, raw: object) -> Value:
    """The value to store, or `Refused` with the field and a value that fits."""
    example = e.recommended()
    bad = Refused(
        copy.fill(copy.SETTING_BAD_VALUE, setting=e.title),
        field="value",
        example=str(example).lower() if isinstance(example, bool) else str(example),
    )
    if e.control == "toggle":
        if not isinstance(raw, bool):
            raise bad
        return raw
    if not isinstance(raw, str):
        raise bad
    if e.control == "choice":
        if raw not in dict(e.choices):
            raise bad
        return raw
    if e.control == "money":
        if not _MONEY.fullmatch(raw):
            raise Refused(copy.NUMBER_NOT_EXACT, field="value", example=str(example))
        return raw
    low, high, step = (Decimal(x) for x in e.bounds)
    number = Decimal(raw) if _DECIMAL.fullmatch(raw) else None
    if number is None or not low <= number <= high or (number - low) % step:
        raise bad
    return format(number.quantize(step), "f")


def asks_first(e: Entry, before: Value, after: Value) -> bool:
    """Whether the Lead must ask the engineer before this change (contract Q20)."""
    if _same(e, before, after):
        return False
    if e.spends_more == "up":
        return Decimal(str(after)) > Decimal(str(before))
    if e.spends_more == "off":
        return after is False
    if e.spends_more == "on":
        return after is True
    return e.spends_more == "any"


def save(e: Entry, value: Value):
    """Stores a value `parse` gave and tells the screens; the setting as stored. Raises
    `Refused` (503 SETTINGS_NOT_SAVED) when settings.json cannot be written."""
    try:
        e.write(value)
    except OSError:
        raise Refused(copy.SETTINGS_NOT_SAVED, 503) from None
    stored = shown(e)
    activity.publish(CHANNEL, {"type": "setting", "setting": stored.model_dump(mode="json")})
    return stored


def change(key: str, raw: object):
    """Checks and saves one setting at once, as the screen asks: the setting as stored."""
    e = entry(key)
    return save(e, parse(e, raw))
