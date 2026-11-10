"""Texts the core returns to the engineer, always as {en, ar} pairs.

A text says what happened and what to do, never where on the screen to go: the same text shows in
the chat, in AI settings and in the first launch. Where the engineer can act, the screen adds the
action for its place, from `fix_of` (an "Open AI settings" button in the chat; nothing more in AI
settings themselves).
"""

# One module per area, each gathered here whole, in alphabetical order. A new text is added in
# its area module and nowhere else: this file and `words_for` both get it from there. A new area
# module adds its one line here. No name is given a value in two areas: the later line would win
# and nothing would say so (tests/test_copy_package.py).

import re  # every name of the one-file module stays on the package: imports and `_names` too
from dataclasses import dataclass

from qsone.copy.account import *
from qsone.copy.ai import *
from qsone.copy.backup import *
from qsone.copy.boq import *
from qsone.copy.calc import *
from qsone.copy.connectors import *
from qsone.copy.deliverables import *
from qsone.copy.fixes import *
from qsone.copy.fixes import _FIX_SHAPES, _shape  # `import *` leaves a `_name` out
from qsone.copy.journey import *
from qsone.copy.ledger import *
from qsone.copy.lookup import words_for
from qsone.copy.plan import *
from qsone.copy.prices import *
from qsone.copy.project_map import *
from qsone.copy.projects import *
from qsone.copy.sandbox import *
from qsone.copy.search import *
from qsone.copy.spending import *
from qsone.copy.team import *
from qsone.copy.tools import *
from qsone.copy.truth import *
from qsone.copy.web import *
from qsone.copy.wording import *
from qsone.copy.wording import (
    _ARABIC,
    _ARABIC_LETTERS,
    _BLANK_THEN_STOP,
    _EXTENSION,
    _ISOLATES,
    _LATIN,
    _STRONG,
    _arabic_form,
    _one_stop,
)
