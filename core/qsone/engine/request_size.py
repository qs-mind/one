"""What one model request sends, by part, in estimated tokens: for core.log, and for the test that
keeps a Brief's requests small (`tests/test_request_size.py`).

The estimate is ONE's own, not a provider's tokenizer: a token for every 2 bytes of UTF-8. Google
counted the Lead's first request of the 6 Nov real walk (instructions, the tool schemas and one
short message, 57.7 KB as sent) at 27,928 tokens; this estimate of it is 28,833, a little above
rather than below. Tool schemas (JSON) and Arabic cost more tokens per byte than English prose.

Never logs text: only sizes."""

import json

BYTES_PER_TOKEN = 2


def estimate(text: str) -> int:
    return -(-len(text.encode()) // BYTES_PER_TOKEN)


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def parts(messages: list, params) -> dict[str, int]:
    """One PydanticAI request by part: instructions, tool schemas, the engineer's words, the
    model's own earlier words and calls, and tool results."""
    from pydantic_ai.messages import (
        ModelRequest,
        ModelResponse,
        RetryPromptPart,
        SystemPromptPart,
        TextPart,
        ToolCallPart,
        ToolReturnPart,
        UserPromptPart,
    )

    found = dict.fromkeys(("instructions", "tools", "prompts", "said", "results"), 0)
    for tool in [*params.function_tools, *params.output_tools]:
        found["tools"] += estimate(
            _json(
                {
                    "name": tool.name,
                    "description": tool.description,
                    "p": tool.parameters_json_schema,
                }
            )
        )
    for message in messages:
        if isinstance(message, ModelRequest):
            if message.instructions:
                found["instructions"] = estimate(message.instructions)  # only the last is sent
            for part in message.parts:
                content = part.content if hasattr(part, "content") else ""
                content = content if isinstance(content, str) else _json(content)
                if isinstance(part, SystemPromptPart):
                    found["instructions"] += estimate(content)
                elif isinstance(part, UserPromptPart):
                    found["prompts"] += estimate(content)
                elif isinstance(part, ToolReturnPart | RetryPromptPart):
                    found["results"] += estimate(content)
        elif isinstance(message, ModelResponse):
            for part in message.parts:
                if isinstance(part, TextPart):
                    found["said"] += estimate(part.content)
                elif isinstance(part, ToolCallPart):
                    found["said"] += estimate(part.tool_name + part.args_as_json_str())
    found["total"] = sum(found.values())
    return found
