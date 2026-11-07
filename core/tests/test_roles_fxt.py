"""Engineer-selected models never cause an automatic price upgrade."""

from dataclasses import replace

from qsone.engine import roles
from qsone.engine.types import ModelChoice
from tests.engine_fakes import HAIKU, OPUS, SONNET


def test_native_typed_unpriced_haiku_replaces_existing_roles():
    roles.choose("checker", OPUS.choice)
    choice = ModelChoice("anthropic", "claude-haiku-5-5")
    roles.choose("lead", choice)
    assert roles.chosen([HAIKU, OPUS, SONNET]) == dict.fromkeys(roles.ROLES, choice)


async def test_typed_model_absent_from_sheet_replaces_existing_connector_roles():
    roles.choose("checker", OPUS.choice)
    choice = ModelChoice("anthropic", "claude-haiku-5-5")
    await roles.select_lead(choice, [HAIKU, OPUS, SONNET], [])
    assert roles.chosen([HAIKU, OPUS, SONNET]) == dict.fromkeys(roles.ROLES, choice)


async def test_priced_selection_never_upgrades_any_role(monkeypatch):
    async def check(*args, **kwargs):
        return None

    from qsone.engine import connectors

    monkeypatch.setattr(connectors, "check", check)
    unknown = replace(OPUS, choice=ModelChoice("anthropic", "unknown"), price_in=None)
    await roles.select_lead(SONNET.choice, [OPUS, SONNET, HAIKU, unknown], [])
    picked = roles.saved()
    assert picked["lead"] == picked["specialist"] == SONNET.choice
    assert picked["quick"] == HAIKU.choice
    assert set(picked.values()) <= {SONNET.choice, HAIKU.choice}


def test_typed_standard_model_absent_from_sheet_never_uses_price_ranking(monkeypatch):
    choice = ModelChoice("standard:existing", "claude-haiku-5-5")
    monkeypatch.setattr(roles.standard, "typed", lambda: [choice])
    assert roles.defaults([OPUS, SONNET]) == dict.fromkeys(roles.ROLES, choice)


def test_explicit_role_upgrade_still_wins():
    roles.choose("lead", HAIKU.choice)
    roles.choose("checker", OPUS.choice)
    assert roles.chosen([HAIKU, OPUS])["checker"] == OPUS.choice


def test_saved_lead_without_other_roles_never_upgrades():
    from qsone import settings

    settings.save_ai("roles", {"lead": {"connector": "anthropic", "model": "claude-haiku-5-5"}})
    picked = roles.chosen([OPUS, HAIKU])
    assert picked == dict.fromkeys(roles.ROLES, ModelChoice("anthropic", "claude-haiku-5-5"))


def test_refused_selected_lead_never_upgrades():
    from qsone.engine import connectors

    roles.choose("lead", HAIKU.choice)
    connectors.note_refused(HAIKU.choice)
    assert roles.chosen([HAIKU, OPUS]) == {}
