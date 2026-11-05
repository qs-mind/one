"""The Standard Link: any OpenAI-compatible provider (DeepSeek, Mistral, Qwen, Ollama, llama.cpp).

The engineer may add several, each with a name, a base URL and an optional key; local servers
have no key. A base URL on this computer makes it `on_device`. Entries live in settings.json
"ai.standard"; keys only in the key store, under "standard:<id>".
"""

import ipaddress
from typing import Literal
from urllib.parse import urlsplit
from uuid import uuid4

import httpx2
import openai
from genai_prices import data_snapshot
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from qsone import keys, settings
from qsone.engine.connectors import efforts_of
from qsone.engine.types import ModelCard, ModelChoice

PREFIX = "standard:"


class KeyInTheClear(ValueError):
    """A key would travel over plain http to another computer."""


def on_device(base_url: str) -> bool:
    host = urlsplit(base_url).hostname or ""
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def provider_of(base_url: str) -> str:
    """genai-prices' id for the provider at `base_url` ("deepseek"), else the URL's host.

    It decides a Same-provider check, and which prices apply: an unknown host has none."""
    try:
        return data_snapshot.get_snapshot().find_provider(None, None, base_url).id
    except LookupError:
        return urlsplit(base_url).hostname or base_url


class StandardLink:
    kind: Literal["model"] = "model"

    def __init__(
        self,
        entry_id: str,
        name: str,
        base_url: str,
        provider: str,
        *,
        http_client: httpx2.AsyncClient | None = None,
    ) -> None:
        self.id = PREFIX + entry_id
        self.name = name
        self.base_url = base_url
        self.provider = provider
        self.on_device = on_device(base_url)
        self._http = http_client

    def _key(self) -> str:
        return keys.get_key(self.id) or "none"  # the SDK needs one; a local server ignores it

    async def cards(self) -> list[ModelCard]:
        """`GET <base_url>/models`, in the server's order.

        That list says nothing of images, tools or context: images stay off (none are sent),
        tools on (the Standard Link speaks OpenAI's tool calls), the context unknown. Its
        effort levels are PydanticAI's guess from the model's name (`reasoning_effort`)."""
        client = openai.AsyncOpenAI(
            base_url=self.base_url, api_key=self._key(), http_client=self._http, timeout=20
        )
        try:
            found = [m.id async for m in client.models.list()]
        finally:
            if self._http is None:
                await client.close()
        cards = []
        for model_id in found:
            efforts, effort_default = efforts_of(OpenAIProvider.model_profile(model_id))
            cards.append(
                ModelCard(
                    choice=ModelChoice(self.id, model_id),
                    name=model_id,
                    provider=self.provider,
                    images=False,
                    tools=True,
                    context=None,
                    price_in=None,
                    price_out=None,
                    price_source=None,
                    on_device=self.on_device,
                    efforts=efforts,
                    effort_default=effort_default,
                )
            )
        return cards

    def model(self, model_id: str) -> OpenAIChatModel:
        provider = OpenAIProvider(
            base_url=self.base_url, api_key=self._key(), http_client=self._http
        )
        return OpenAIChatModel(model_id, provider=provider)


def _entries() -> list[dict]:
    saved = settings.ai().get("standard")
    if not isinstance(saved, list):
        return []
    fields = ("id", "name", "base_url", "provider")
    return [
        e for e in saved if isinstance(e, dict) and all(isinstance(e.get(f), str) for f in fields)
    ]


def links(*, http_client: httpx2.AsyncClient | None = None) -> list[StandardLink]:
    return [
        StandardLink(e["id"], e["name"], e["base_url"], e["provider"], http_client=http_client)
        for e in _entries()
    ]


def add(name: str, base_url: str, key: str | None) -> StandardLink:
    """Saves a new entry; its key goes to the key store only.

    Raises `ValueError` for a URL that is not http(s) with a host, `KeyInTheClear`,
    `keyring.errors.KeyringError` (then nothing is saved) and `OSError`."""
    parts = urlsplit(base_url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValueError("base_url must be an http:// or https:// address")
    if key and parts.scheme == "http" and not on_device(base_url):
        raise KeyInTheClear("a key needs https:// unless the server is on this computer")
    link = StandardLink(uuid4().hex[:12], name, base_url.rstrip("/"), provider_of(base_url))
    if key:
        keys.set_key(link.id, key)
    entry = {"id": link.id.removeprefix(PREFIX), "name": link.name, "base_url": link.base_url}
    settings.save_ai("standard", [*_entries(), entry | {"provider": link.provider}])
    return link


def remove(connector_id: str) -> bool:
    """Removes the entry, its key, and the role choices and prices that named it.

    False when there is no such entry. Raises `KeyringError` (then nothing is removed) and
    `OSError`."""
    if take_out(connector_id) is None:
        return False
    forget_key({"id": connector_id})
    return True


def _part(ai: dict, name: str) -> dict:
    found = ai.get(name)
    return dict(found) if isinstance(found, dict) else {}


def take_out(connector_id: str) -> dict | None:
    """Takes the entry out of use, with the role choices and prices that named it; its key
    stays. What was taken, for `put_back` (Undo); None when there is no such entry."""
    entries = _entries()
    at = next((i for i, e in enumerate(entries) if PREFIX + e["id"] == connector_id), None)
    if at is None:
        return None
    ai = settings.ai()

    def named(choice) -> bool:
        return isinstance(choice, dict) and choice.get("connector") == connector_id

    roles, prices = _part(ai, "roles"), _part(ai, "prices")
    mine = {k: p for k, p in prices.items() if k.startswith(connector_id + "/")}
    settings.save(
        "ai",
        ai
        | {
            "standard": entries[:at] + entries[at + 1 :],
            "roles": {r: c for r, c in roles.items() if not named(c)},
            "prices": {k: p for k, p in prices.items() if k not in mine},
        },
    )
    return {
        "id": connector_id,
        "at": at,
        "entry": entries[at],
        "roles": {r: c for r, c in roles.items() if named(c)},
        "prices": mine,
    }


def put_back(taken: dict) -> bool:
    """Undo of `take_out`: the entry in its place again, its prices, and its role choices for
    the roles not chosen anew since."""
    entries = _entries()
    if any(e["id"] == taken["entry"]["id"] for e in entries):
        return False
    entries.insert(taken["at"], taken["entry"])
    ai = settings.ai()
    roles = taken["roles"] | _part(ai, "roles")
    prices = _part(ai, "prices") | taken["prices"]
    settings.save("ai", ai | {"standard": entries, "roles": roles, "prices": prices})
    return True


def forget_key(taken: dict) -> None:
    """The purge after `take_out`'s Undo window. Raises `KeyringError` (tried again later)."""
    keys.delete_key(taken["id"])
