"""The Native Link: Claude through Anthropic's API and the engineer's own key."""

from typing import Literal

import httpx2
from pydantic_ai.models.anthropic import AnthropicModel, AnthropicModelSettings
from pydantic_ai.providers.anthropic import AnthropicProvider

from qsone import keys, models
from qsone.engine.connectors import NoKey, efforts_of
from qsone.engine.types import ModelCard, ModelChoice


class NativeLink:
    id = "anthropic"
    kind: Literal["model"] = "model"
    name = "Claude"
    provider = "anthropic"
    on_device = False

    def __init__(self, *, http_client: httpx2.AsyncClient | None = None) -> None:
        self._http = http_client

    async def cards(self) -> list[ModelCard]:
        """Every model the key can call, from Anthropic's own list (free); none without a key."""
        key = keys.get_key(self.id)
        if key is None:
            return []
        found = []
        for info in await models.list_model_infos(key, self._http):
            efforts, effort_default = efforts_of(AnthropicProvider.model_profile(info.id))
            found.append(
                ModelCard(
                    choice=ModelChoice(self.id, info.id),
                    name=info.display_name,
                    provider=self.provider,
                    images=bool(info.capabilities and info.capabilities.image_input.supported),
                    tools=True,  # every Claude model takes tools
                    context=info.max_input_tokens,
                    price_in=None,
                    price_out=None,
                    price_source=None,
                    efforts=efforts,
                    effort_default=effort_default,
                )
            )
        return found

    def model(self, model_id: str) -> AnthropicModel:
        key = keys.get_key(self.id)
        if key is None:  # never let the SDK fall back to an ANTHROPIC_API_KEY variable
            raise NoKey(self.id)
        return AnthropicModel(
            model_id,
            provider=AnthropicProvider(api_key=key, http_client=self._http),
            settings=AnthropicModelSettings(
                anthropic_cache_instructions=True, anthropic_cache_tool_definitions=True
            ),
        )
