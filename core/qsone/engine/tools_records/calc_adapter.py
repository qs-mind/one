"""The Plan 3 calc tools as engine tools, through one adapter (`_calc`)."""

import asyncio

from pydantic import BaseModel

from qsone.calc import tool as calc_tool
from qsone.engine.tools import ModelRetry, Tool, ToolContext, say_refused
from qsone.engine.tools_records.shared import _actor, _json, _project

# The Plan 3 calc tools -------------------------------------------------------------------------


def _calc_retry(name: str, reply: dict) -> str:
    return (
        f"{name}: {reply['error']['en']} Field: {reply.get('field') or 'none'}. "
        f"Example: {reply.get('example')}"
    )


def _calc(name: str) -> Tool:
    plan3 = calc_tool.TOOLS[name]

    async def run(ctx: ToolContext, args: BaseModel) -> str:
        rec = _project(ctx)
        payload = args.model_dump(mode="json", exclude_unset=True)
        reply = await asyncio.to_thread(calc_tool.call, rec, name, payload, actor=_actor(ctx))
        if "error" in reply:
            say_refused(ctx, reply["error"])
            raise ModelRetry(_calc_retry(name, reply))
        return _json(reply)

    def invalid(payload: dict) -> str:
        # A payload that does not validate is refused before the project is read.
        return _calc_retry(name, calc_tool.call(None, name, payload, actor="engine"))

    return Tool(
        name=name,
        description=plan3.doc,
        args=plan3.request,
        risk="read" if name == "explain_number" else "write",
        run=run,
        activity=lambda _: plan3.description,
        writes=name == "define_unit",  # the others write nothing new on unchanged inputs
        example=plan3.example,
        invalid=invalid,
        self_paged=True,
    )
