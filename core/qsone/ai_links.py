"""Connect an AI provider by pasting its key, and disconnect it (Phase 1, routes 23 and 24).

The provider is read from the key's own form (its prefix and length) and from nothing else, so a
key never goes to a company it is not from: a key ONE does not recognise is sent to no one and
the screen offers the Standard Link by address instead (`POST /settings/ai/standard`). A
recognised key goes only to its provider's fixed address, for one free check (the provider's
list of models); only then is it kept in the key store. A key is never echoed, logged or kept
anywhere else.

A link's id is the connector's, as `GET /settings/ai` lists it: "anthropic" (the Native Link) or
"standard:<id>". Claude Code is not a link: it has no key and is switched off by its own route.
Disconnecting takes a link out of use at once; its key leaves the key store when the Undo window
ends (the key waits under a parked name meanwhile, never in settings.json).
"""

import re
from dataclasses import dataclass
from uuid import uuid4

import anthropic
import httpx2
import openai
from keyring.errors import KeyringError

from qsone import copy, keys, models
from qsone import phase1_contract as c
from qsone.engine import connectors
from qsone.engine.connectors import standard
from qsone.engine.connectors.native_anthropic import NativeLink
from qsone.journey import setup_state
from qsone.settings_registry import Refused
from qsone.undo import Trash


@dataclass(frozen=True)
class KeyForm:
    form: re.Pattern
    name: str  # the link's name, as the engineer knows the provider
    base_url: str | None  # the provider's OpenAI-compatible address; None: the Native Link


# Only forms that belong to one provider. A bare "sk-…" is OpenAI's older form and several
# other providers' too, so it is not recognised.
FORMS = (
    KeyForm(re.compile(r"sk-ant-api\d{2}-[A-Za-z0-9_-]{20,200}"), NativeLink.name, None),
    KeyForm(re.compile(r"sk-or-v1-[0-9a-f]{64}"), "OpenRouter", "https://openrouter.ai/api/v1"),
    KeyForm(
        re.compile(r"sk-(?:proj|svcacct)-[A-Za-z0-9_-]{20,300}"),
        "OpenAI",
        "https://api.openai.com/v1",
    ),
    KeyForm(
        re.compile(r"AIza[0-9A-Za-z_-]{35}"),
        "Gemini",
        "https://generativelanguage.googleapis.com/v1beta/openai",
    ),
    KeyForm(re.compile(r"gsk_[A-Za-z0-9]{52}"), "Groq", "https://api.groq.com/openai/v1"),
    KeyForm(re.compile(r"xai-[A-Za-z0-9]{20,200}"), "xAI", "https://api.x.ai/v1"),
)
NATIVE = NativeLink.id
PARKED = "removed:"  # the key store name a disconnected key waits under: "removed:<token>"


def recognise(key: str) -> KeyForm | None:
    return next((f for f in FORMS if f.form.fullmatch(key)), None)


def _not_recognised() -> Refused:
    return Refused(copy.KEY_NOT_RECOGNISED, 422, field="key")


def _check_failed(error: Exception, name: str) -> Refused:
    """The provider did not take the key (409, `field: "key"`), or could not be asked (502)."""
    text = connectors.plain_error(error, name)
    refused = text in (copy.KEY_REFUSED, copy.fill(copy.AI_KEY_REFUSED, provider=name))
    return Refused(text, 409, field="key") if refused else Refused(text, 502)


def _store(name: str, key: str) -> None:
    try:
        keys.set_key(name, key)
    except KeyringError:
        raise Refused(copy.KEY_STORE_DOWN, 503) from None


async def _check_native(key: str, http: httpx2.AsyncClient | None) -> None:
    try:
        await models.list_model_infos(key, http)
    except anthropic.APIError as error:
        raise _check_failed(error, NativeLink.name) from None


async def _check_standard(form: KeyForm, key: str, http: httpx2.AsyncClient | None) -> None:
    client = openai.AsyncOpenAI(
        base_url=form.base_url, api_key=key, http_client=http, timeout=20, max_retries=0
    )
    try:
        [m async for m in client.models.list()]
    except openai.APIError as error:
        raise _check_failed(error, form.name) from None
    finally:
        if http is None:
            await client.close()


def _linked(form: KeyForm, key: str) -> c.AiLink | None:
    """The link this key already makes, if any."""
    if form.base_url is None:
        return _native() if keys.get_key(NATIVE) == key else None
    provider = standard.provider_of(form.base_url)
    for link in standard.links():
        if link.provider == provider and keys.get_key(link.id) == key:
            return c.AiLink(id=link.id, name=link.name, provider=link.provider)
    return None


def _native() -> c.AiLink:
    return c.AiLink(id=NATIVE, name=NativeLink.name, provider=NativeLink.provider)


async def connect(key: str, http: httpx2.AsyncClient | None = None) -> tuple[c.AiLink, bool]:
    """The link the key makes, and whether it is new. Raises `RecordsError` before the AI
    consent, and `Refused` with the contract's words otherwise."""
    setup_state.require_consent()
    form = recognise(key)
    if form is None:
        raise _not_recognised()
    found = _linked(form, key)
    if found is not None:
        return found, False
    if form.base_url is None:
        await _check_native(key, http)
        _store(NATIVE, key)
        return _native(), True
    await _check_standard(form, key, http)
    try:
        link = standard.add(form.name, form.base_url, key)
    except KeyringError:
        raise Refused(copy.KEY_STORE_DOWN, 503) from None
    except OSError:
        raise Refused(copy.SETTINGS_NOT_SAVED, 503) from None
    return c.AiLink(id=link.id, name=link.name, provider=link.provider), True


# Disconnecting ---------------------------------------------------------------------------------


def using(engine: object, link_id: str) -> str | None:
    """The id of a running Brief whose team uses the link, if any."""
    # The engine keeps its running Briefs here; each knows its team's models once it starts.
    for brief in getattr(engine, "_briefs", {}).values():
        setup = getattr(brief, "setup", None)
        if brief.finished or setup is None:
            continue
        if any(choice.connector == link_id for choice in setup.roles.values()):
            return brief.brief_id
    return None


def _put_back(entry: dict) -> bool:
    """Undo: the parked key is the Native Link's again, unless a key was pasted since."""
    key = keys.get_key(entry["parked"])
    if key is None or keys.get_key(NATIVE) is not None:
        return False
    keys.set_key(NATIVE, key)
    keys.delete_key(entry["parked"])
    return True


def _forget(entry: dict) -> None:
    keys.delete_key(entry["parked"])


def kinds(trash: Trash) -> None:
    """How a disconnected Native Link is put back and purged (a Standard Link's kind is
    `standard`, which the AI settings' router gives)."""
    trash.kind(NATIVE, restore=_put_back, purge=_forget)


def disconnect(link_id: str, trash: Trash, engine: object) -> dict:
    """Takes the link out of use: `{undo, window_ms}`. Raises `Refused`."""
    is_native = link_id == NATIVE and keys.get_key(NATIVE) is not None
    is_standard = link_id.startswith(standard.PREFIX) and any(
        link.id == link_id for link in standard.links()
    )
    if not (is_native or is_standard):
        raise Refused(copy.AI_LINK_NOT_FOUND, 404)
    running = using(engine, link_id)
    if running is not None:
        raise Refused(copy.AI_LINK_IN_USE, 409, brief_id=running)
    if is_standard:
        try:
            taken = standard.take_out(link_id)
        except OSError:
            raise Refused(copy.SETTINGS_NOT_SAVED, 503) from None
        return trash.put("standard", taken)
    parked = PARKED + uuid4().hex
    try:
        _store(parked, keys.get_key(NATIVE) or "")
        keys.delete_key(NATIVE)
    except KeyringError:
        raise Refused(copy.KEY_STORE_DOWN, 503) from None
    return trash.put(NATIVE, {"id": NATIVE, "parked": parked})
