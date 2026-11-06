"""One's tools (Plan 5). Each tool module registers itself in `engine.tools` when imported;
importing this package imports every one of them, so all are in `REGISTRY`."""

from qsone import view  # noqa: F401 - decision 16.1's `show`
from qsone.journey import understand  # noqa: F401 - Plan 8's `understood`, the card's tool
from qsone.tools import (  # noqa: F401 - each registers its tools
    boq,
    compare,
    connectors,
    engineer,
    files,
    lessons,
    prices,
    project_map,
    sandbox,
    sheet_pricing,
    web,
)
