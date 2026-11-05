"""Checks a Sandbox script before it runs (Plan 5, decision 26), so a script that cannot work is
sent back to the agent at once, with what to change, and never reaches the Sandbox.

A script must compile, be at most 200 KB, and import only Python's own modules plus `openpyxl`,
`xlrd` and `one_io`. Modules that only fail inside the Sandbox (no sockets, no processes, no
native code) are refused here too, so the agent is told up front. This is advice, not the
defence: the Sandbox itself has no network and no disk, whatever a script imports."""

import ast
import sys

from qsone import copy
from qsone.records.project import RecordsError

MAX_BYTES = 200 * 1024
REMOVED = frozenset({"socket", "ssl", "subprocess", "multiprocessing", "ctypes", "asyncio"})
ALLOWED = (frozenset(sys.stdlib_module_names) - REMOVED) | {"openpyxl", "xlrd", "one_io"}


def _refused(module: str) -> RecordsError:
    return RecordsError(copy.fill(copy.SANDBOX_MODULE, module=module), status=422, field="script")


def script(text: str) -> list[str]:
    """The top-level modules `text` imports, in order, each once. Raises `RecordsError`:
    SANDBOX_SCRIPT_TOO_BIG, SANDBOX_SYNTAX (with the line) or SANDBOX_MODULE (with the module)."""
    if len(text.encode()) > MAX_BYTES:
        raise RecordsError(copy.SANDBOX_SCRIPT_TOO_BIG, status=422, field="script")
    try:
        tree = compile(text, "script.py", "exec", ast.PyCF_ONLY_AST)
    except SyntaxError as e:
        said = copy.fill(copy.SANDBOX_SYNTAX, line=e.lineno or 1, message=e.msg)
        raise RecordsError(said, status=422, field="script") from None
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # a relative import: there is no package around the script
                raise _refused("." * node.level + (node.module or ""))
            names = [node.module or ""]
        else:
            continue
        for name in names:
            top = name.split(".", 1)[0]
            if top not in ALLOWED:
                raise _refused(top)
            if top not in found:
                found.append(top)
    return found
