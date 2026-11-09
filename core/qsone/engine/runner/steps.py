import re
from uuid import uuid4

from pydantic_ai.messages import ModelRequest, ModelResponse, ToolCallPart, ToolReturnPart

from qsone import copy
from qsone.engine import focus, tool_groups, tools
from qsone.engine.runner.histories import _calls, _dump, _load
from qsone.engine.tools import REGISTRY
from qsone.engine.types import AgentSpec, Progress, Text
from qsone.records.project import RecordsError

_RECORD_ID = re.compile(r"\b[0-9a-f]{32}\b")  # an item, file or number id in a tool's words


class _BriefSteps:
    """A run's steps: its history as saved, and each tool call's words and Focus on the screen."""

    async def mapping_read(self, file_id, locator):
        """Normal files_read tool calls, mirrored in this mapping Brief's history."""
        args = {"file_id": file_id}
        if "page" in locator:
            args["pages"] = locator["page"]
        if "sheet" in locator:
            args["sheet"] = locator["sheet"]
            if "row" in locator:
                args["rows"] = locator["row"]
        history = _load(self.store.run(self.lead_run_id)["history"])
        parts = []
        for part in range(1, 101):
            call_args = args | {"part": part}
            call_id = "map-read-" + uuid4().hex
            text = await tools.call("files_read", call_args, self.lead_ctx)
            history.append(
                ModelResponse(parts=[ToolCallPart("files_read", call_args, tool_call_id=call_id)])
            )
            history.append(
                ModelRequest(parts=[ToolReturnPart("files_read", text, tool_call_id=call_id)])
            )
            self._save(self.lead_run_id, history)
            parts.append(text)
            count = re.search(r"part \d+ of (\d+)", text)
            if count is None or part >= int(count[1]) or sum(map(len, parts)) >= 12000:
                break
        return "\n".join(parts)

    def _save(self, run_id: str, messages: list) -> None:
        if self.cancel_mode != "crash":
            self.store.save_history(run_id, _dump(messages))

    def _say_tools(self, run_id: str, spec: AgentSpec, response: ModelResponse) -> None:
        for c in _calls(response):
            if c.tool_name == tool_groups.OPEN:
                continue  # ONE's own step, not work the engineer sees
            tool = REGISTRY.get(c.tool_name)
            words = copy.tool_step(c.tool_name)
            if tool is not None:
                try:
                    words = tool.activity(tool.args.model_validate(c.args_as_dict()))
                except Exception:  # noqa: BLE001 - its own words are only for the Progress Line
                    pass
            on = self._focus(c.tool_name, c.args_as_dict())
            words = self._plain(words)
            self.emit(Progress(self.brief_id, run_id, spec.name, words, on, tool=True))

    def _plain(self, words: Text) -> Text:
        """The work log's words with each record id the model gave named as the engineer knows
        it: an item by its code, a file by its name (never «البند 707d81e9…»)."""
        rec = self.place.rec
        ids = {i for text in words.values() for i in _RECORD_ID.findall(text)}
        if rec is None or not ids:
            return words
        names: dict[str, str] = {}
        try:
            with rec.read() as c:
                for i in ids:
                    row = (
                        c.execute(
                            "SELECT coalesce(code, '') FROM items WHERE id = ?", (i,)
                        ).fetchone()
                        or c.execute("SELECT name FROM files WHERE id = ?", (i,)).fetchone()
                        or c.execute(
                            "SELECT coalesce(i.code, '') FROM numbers n JOIN items i"
                            " ON i.id = n.item_id WHERE n.id = ?",
                            (i,),
                        ).fetchone()
                    )
                    if row and row[0]:
                        names[i] = row[0]
        except RecordsError:
            return words
        return {
            lang: _RECORD_ID.sub(lambda m: names.get(m[0], m[0]), text)
            for lang, text in words.items()
        }

    def _focus(self, tool: str, args: dict) -> dict | None:
        try:
            return focus.of(tool, args, self.place.rec)
        except RecordsError:  # only for the canvas: the tool call itself says what is wrong
            return None
