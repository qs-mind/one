"""A fake OpenAI-compatible provider for request-size tests: an httpx2 `MockTransport` that
answers `GET /models` and `POST /chat/completions` (streamed or not) from a script, and keeps
every request body. Not product code: no test reaches a real AI.

It speaks as Google's OpenAI-compatible endpoint does: a streamed answer carries the usage in
every chunk, each time the whole prompt and the output so far. `cached` gives the share of the
prompt it reports as read from the provider's cache (`prompt_tokens_details.cached_tokens`)."""

import json
from collections.abc import Callable
from dataclasses import dataclass, field

import httpx2

from qsone.engine import request_size


def wire_parts(body: dict, *, brief: str | None = None) -> dict[str, int]:
    """A chat-completions body by part, in estimated tokens (`request_size.estimate`): system
    (instructions), tools (their schemas), and the messages. With `brief` (the Brief's own
    words), the messages before it are counted apart as `earlier` (the chat's earlier Briefs)."""
    found = dict.fromkeys(("system", "tools", "earlier", "prompts", "said", "results"), 0)
    found["tools"] = request_size.estimate(json.dumps(body.get("tools", []), ensure_ascii=False))
    messages = body["messages"]
    start = 0
    if brief is not None:
        start = next(
            (
                i
                for i, m in enumerate(messages)
                if m["role"] == "user" and brief in str(m["content"])
            ),
            0,
        )
    for i, m in enumerate(messages):
        size = request_size.estimate(json.dumps(m, ensure_ascii=False))
        if m["role"] in ("system", "developer"):
            found["system"] += size
        elif i < start:
            found["earlier"] += size
        elif m["role"] == "user":
            found["prompts"] += size
        elif m["role"] == "tool":
            found["results"] += size
        else:
            found["said"] += size
    found["total"] = sum(found.values())
    return found


# A step answers one request's body: ("text", "...") or ("calls", [(tool, args), ...]).
Step = tuple[str, object]
Script = Callable[[dict], Step]


@dataclass
class FakeProvider:
    script: Script
    models: tuple[str, ...] = ("models/gemini-3.1-flash-lite",)
    cached: Callable[[dict], int] = lambda body: 0
    bodies: list[dict] = field(default_factory=list)
    chunk_words: int = 3  # words per streamed text chunk

    def client(self) -> httpx2.AsyncClient:
        return httpx2.AsyncClient(transport=httpx2.MockTransport(self._handle))

    def _handle(self, request: httpx2.Request) -> httpx2.Response:
        if request.url.path.endswith("/models"):
            data = [{"id": m, "object": "model", "owned_by": "google"} for m in self.models]
            return httpx2.Response(200, json={"object": "list", "data": data})
        if not request.url.path.endswith("/chat/completions"):
            return httpx2.Response(404, json={"error": {"message": "not here"}})
        body = json.loads(request.content)
        self.bodies.append(body)
        kind, value = self.script(body)
        prompt = wire_parts(body)["total"]
        cached = min(self.cached(body), prompt)
        if body.get("stream"):
            return self._stream(kind, value, prompt, cached)
        message: dict = {"role": "assistant", "content": None}
        if kind == "text":
            message["content"] = value
        else:
            message["tool_calls"] = self._calls(value)
        out = len(json.dumps(message)) // 4
        return httpx2.Response(
            200,
            json={
                "id": "fake",
                "object": "chat.completion",
                "created": 1,
                "model": body["model"],
                "choices": [{"index": 0, "message": message, "finish_reason": "stop"}],
                "usage": self._usage(prompt, out, cached),
            },
        )

    @staticmethod
    def _calls(value) -> list[dict]:
        return [
            {
                "id": f"call_{i}_{tool}",
                "type": "function",
                "function": {"name": tool, "arguments": json.dumps(args, ensure_ascii=False)},
            }
            for i, (tool, args) in enumerate(value)
        ]

    @staticmethod
    def _usage(prompt: int, out: int, cached: int) -> dict:
        usage = {"prompt_tokens": prompt, "completion_tokens": out, "total_tokens": prompt + out}
        if cached:
            usage["prompt_tokens_details"] = {"cached_tokens": cached}
        return usage

    def _stream(self, kind: str, value, prompt: int, cached: int) -> httpx2.Response:
        deltas: list[dict] = []
        if kind == "text":
            words = str(value).split(" ")
            for i in range(0, len(words), self.chunk_words):
                piece = " ".join(words[i : i + self.chunk_words])
                deltas.append({"content": piece if i == 0 else " " + piece})
        else:
            calls = self._calls(value)
            deltas.append({"tool_calls": [c | {"index": i} for i, c in enumerate(calls)]})
        lines, out = [], 0
        for i, delta in enumerate(deltas):
            out += max(1, len(json.dumps(delta)) // 8)
            last = i == len(deltas) - 1
            chunk = {
                "id": "fake",
                "object": "chat.completion.chunk",
                "created": 1,
                "model": "fake",
                "choices": [
                    {
                        "index": 0,
                        "delta": ({"role": "assistant"} if i == 0 else {}) | delta,
                        "finish_reason": ("stop" if kind == "text" else "tool_calls")
                        if last
                        else None,
                    }
                ],
                # Google's way: the whole prompt and the output so far, in every chunk
                "usage": self._usage(prompt, out, cached),
            }
            lines.append(f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n")
        lines.append("data: [DONE]\n\n")
        return httpx2.Response(
            200,
            content="".join(lines).encode(),
            headers={"content-type": "text/event-stream"},
        )
