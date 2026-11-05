"""One's tools (Plan 5). Each tool module registers itself in `engine.tools` when imported;
importing this package imports every one of them, so all are in `REGISTRY`."""

from qsone.tools import (  # noqa: F401 - each registers its tools
    boq,
    connectors,
    engineer,
    files,
    lessons,
    prices,
    sandbox,
    web,
)
