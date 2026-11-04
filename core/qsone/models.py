"""GET /settings/models: the Claude models the engineer's own key can use, from Anthropic's list."""

import logging
from collections.abc import Awaitable, Callable

import anthropic
import httpx2

from qsone import copy

ModelLister = Callable[[str], Awaitable[list[dict[str, str]]]]

log = logging.getLogger("qsone.models")


async def list_models(
    api_key: str, http_client: httpx2.AsyncClient | None = None
) -> list[dict[str, str]]:
    """Every model the key can call, newest first, as {id, name}. Listing models is free."""
    async with anthropic.AsyncAnthropic(
        api_key=api_key, http_client=http_client, timeout=20
    ) as client:
        found = [m async for m in client.models.list() if m.lifecycle != "retired"]
    found.sort(key=lambda m: m.created_at, reverse=True)
    return [{"id": m.id, "name": m.display_name} for m in found]


def plain_error(error: anthropic.APIError) -> dict[str, str]:
    """The {en, ar} text the engineer sees when Anthropic does not give the list."""
    if isinstance(error, anthropic.AuthenticationError | anthropic.PermissionDeniedError):
        return copy.KEY_REFUSED
    if isinstance(error, anthropic.APIConnectionError):  # also a timeout
        return copy.NO_CONNECTION
    if isinstance(error, anthropic.RateLimitError) or (
        isinstance(error, anthropic.APIStatusError) and error.status_code >= 500  # also overloaded
    ):
        return copy.CLAUDE_BUSY
    return copy.MODELS_FAILED
