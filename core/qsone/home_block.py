"""Why the Lead cannot start work now (`LeadBlock`, Phase 1, C7), for Home and every tender.

From what this computer keeps only: no provider is asked, and no network is waited for."""

from qsone import copy
from qsone.records.project import RecordsError


def _connected(engine) -> bool:
    """Any AI is linked: from what this computer keeps, never by asking a provider."""
    from qsone import keys
    from qsone.engine.connectors.native_anthropic import NativeLink

    return any(not isinstance(c, NativeLink) or keys.get_key(c.id) for c in engine.connectors())


def _cap_reached(engine) -> dict | None:
    from qsone.engine import costs

    book = engine.cost_book()
    if book is None:
        return None
    limits = costs.caps()
    today = engine.clock().astimezone(book.local_tz).date()
    scopes = (
        (copy.SCOPE_DAY, {"day": today}, limits.day),
        (copy.SCOPE_MONTH, {"month": (today.year, today.month)}, limits.month),
    )
    for name, where, cap in scopes:
        spent = book.spent(**where, count_equivalent=limits.subscription_stops)
        if spent >= cap:
            amounts = {"spent": costs.usd_text(spent), "cap": costs.usd_text(cap)}
            return copy.fill(copy.CAP_STOPPED, scope_name=name, **amounts)
    return None


def lead_block(engine) -> dict | None:
    """`LeadBlock` as JSON: why the Lead cannot start work at all now; None when it can."""
    from qsone.journey import setup_state

    try:
        engine.engineer_records()
    except RecordsError as e:
        return {"reason": e.text, "fix": copy.fix_of(e.text)}
    if setup_state.consent() is None:
        return {"reason": copy.AI_CONSENT_NEEDED, "fix": "consent"}
    if not _connected(engine):
        return {"reason": copy.NO_AI, "fix": "ai"}
    refused = getattr(engine, "key_refused", None)  # at the last listing of the models
    if refused is not None:
        return {"reason": refused, "fix": "ai"}
    reached = _cap_reached(engine)
    return None if reached is None else {"reason": reached, "fix": "caps"}


def tender_block(engine, confidential: bool, blocked: dict | None) -> dict | None:
    """One tender's `LeadBlock`: every tender's (`blocked`), or the Confidential rule's while
    `ai.confidential_on_device` is on and no model on this computer is connected."""
    from qsone.settings_registry import confidential_on_device

    if blocked is not None or not confidential or not confidential_on_device():
        return blocked
    if any(getattr(c, "on_device", False) for c in engine.connectors()):
        return None
    return {"reason": copy.CONFIDENTIAL_NO_LOCAL_AI, "fix": "ai"}


def project_block(engine, rec) -> dict | None:
    """`TenderRow.blocked` for `rec` at this moment: what a route that would start the Lead's
    work in it refuses with (contract section 1), before it stores anything."""
    return tender_block(engine, rec.meta().get("confidential") == "1", lead_block(engine))
