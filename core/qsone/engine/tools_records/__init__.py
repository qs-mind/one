"""The Project Records tools, and the Plan 3 calc tools through one adapter.

Importing this module registers them. All need an open project (`ctx.rec`). Writes go through
`records.ledger`, so every number keeps its source and date; the actor is the agent's English
name. Reading file text (`search_records`, `read_chunk`) comes back fenced as data, with the
file's id and name, so the agent cites the file with no id asked of the engineer.

This is the only engine file that imports `qsone.calc` (Plan 3): each calc tool becomes an
engine `Tool` with its own doc, request model and refusals; `explain_number` reads, the others
write; an "error" reply becomes `ModelRetry` with its English text, field and example.

Plan 5 (Task 7) extends them:
- a source must point at real evidence (`evidence`): a file and a place inside it, a page in
  the Web Log, a QS Mind price in the cache, a settled question card, an answered Connector
  call. Its link, title and dates come from that evidence, never from the model; a computed
  number's source is the QS Calc Engine's alone;
- `where="engineer"` writes to Engineer Records, after the engineer's yes (a `keep` card, once
  per Brief); `search_records` and `read_chunk` read there too;
- `add_item` keeps personal data only as the engineer said (`records.keep`)."""

# Every name the one-file module had is still an attribute of this package, the names it
# imported too. A name here is a copy: to change one at run time (`UNDATED_FILES`), set it
# on the module that owns it.
# ruff: noqa: F401

import asyncio
import json
import math
import re
from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from qsone import copy
from qsone.calc import resolve
from qsone.calc import tool as calc_tool
from qsone.calc.errors import CalcError
from qsone.calc.units import UnitTable
from qsone.engine import truth
from qsone.engine.tools import ModelRetry, Tool, ToolContext, register, say_refused
from qsone.engine.tools_records.calc_adapter import _calc, _calc_retry
from qsone.engine.tools_records.file_reads import (
    _CHUNK_DOC,
    _CHUNK_EXAMPLE,
    _HIT_CHARS,
    _SEARCH_DOC,
    _SEARCH_EXAMPLE,
    ChunkArgs,
    SearchArgs,
    _chunk,
    _read_chunk,
    _received_ids,
    _search,
    _search_required,
)
from qsone.engine.tools_records.item_writes import (
    _CLIENT_KINDS,
    _ITEM_DOC,
    _ITEM_EXAMPLE,
    NewItemArgs,
    _add_item,
    _add_item_tool,
    _imported,
)
from qsone.engine.tools_records.ledger_reads import (
    _FIND_DOC,
    _FIND_EXAMPLE,
    _ITEMS_PER_PAGE,
    _MISSING_SHOWN,
    _NUMBERS_DOC,
    _NUMBERS_EXAMPLE,
    _RANK_DOC,
    _RANK_EXAMPLE,
    FindArgs,
    ItemArgs,
    RankArgs,
    _find,
    _find_items,
    _ledger_numbers,
    _numbers,
    _rank,
    _rank_items,
)
from qsone.engine.tools_records.number_checks import (
    _BASE,
    _check_number,
    _quantity_unit,
    _same_measure,
)
from qsone.engine.tools_records.number_writes import (
    _CORRECTION_DOC,
    _CORRECTION_EXAMPLE,
    _NUMBER_DOC,
    _NUMBER_EXAMPLE,
    CorrectionArgs,
    NumberArgs,
    _correct,
    _correct_number,
    _record,
    _record_number,
)
from qsone.engine.tools_records.pricing_intent import (
    _engineers_priced_copy,
    _price_item_named,
    _pricing_requested,
)
from qsone.engine.tools_records.registration import RECORDS_TOOLS, _tool
from qsone.engine.tools_records.shared import (
    _DATE,
    _ENGINEER_REFUSED,
    _RATES,
    Where,
    _actor,
    _Args,
    _engineer,
    _engineer_allowed,
    _engineer_ok,
    _field,
    _json,
    _project,
    _target,
)
from qsone.engine.tools_records.source_evidence import (
    _COMPUTED,
    _COUNTRIES,
    _DIGITS,
    _KEY,
    _REF,
    _SOURCE_DOC,
    _SOURCE_EXAMPLE,
    _UNCHECKED,
    OWN_PRICE_REF,
    UNDATED_FILES,
    Covers,
    SourceArgs,
    _add_source_tool,
    _connector_source,
    _covers,
    _day,
    _engineer_source,
    _file_source,
    _inside,
    _made_by_a_script,
    _no_evidence,
    _own_price_source,
    _place,
    _prices_source,
    _web_source,
    _write_source,
    evidence,
)
from qsone.engine.types import Card, Text
from qsone.records import arabic, boq, keep, ledger, search
from qsone.records.project import Records, RecordsError
