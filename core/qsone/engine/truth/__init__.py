"""Truth checks: what a reply, a Deliverable or a letter says, against ONE's own records.

A check in code beats a sentence in a prompt. A weak model wrote «تم الانتهاء من تسعير كافة
بنود المقايسة» over 8 priced items, letters with «[مبلغ إجمالي المقايسة]», a 60-day validity
the client's email puts at ٩٠ يوم, tomorrow's date, and rates cited to a quote that does not
have them. These functions find each of those from the records; the Brief Runner, the record
tools and the Deliverable tools refuse or flag with them. Pure reading: nothing here writes.

- `coverage`: the project's BOQ items, how many have a rate, its Deliverables.
- `reply_problems`: what a reply says that the records do not show, for one retry.
- `facts`: the line the core puts beside a Brief's reply, with its flags.
- `placeholders`, `letter_problems`: for Deliverables and letters.
- `value_at`: whether a number is where its source says it is.
- `today`: the date in Cairo, which the core gives every agent."""

import json  # noqa: F401 - every name of the one-file module stays on the package, imports too
import re  # noqa: F401
from dataclasses import dataclass, field  # noqa: F401
from datetime import date, datetime  # noqa: F401
from zoneinfo import ZoneInfo  # noqa: F401

from qsone import copy  # noqa: F401
from qsone.engine import numbers_guard  # noqa: F401
from qsone.engine.truth.blanks import (  # noqa: F401
    _ID,
    _JSONISH,
    _LETTERS,
    _PLACEHOLDER,
    FOR_ENGINEER,
    placeholders,
    placeholders_in,
)
from qsone.engine.truth.cited import (  # noqa: F401
    _BARE_ROW,
    _ITEM_CODE,
    _NUMS,
    _PAGE,
    _Q,
    _ROW_SHEET,
    _SEGMENT,
    _SHEET_ROW,
    Place,
    _item_codes,
    _numbers_of,
    _sheet_names,
    _sheet_of,
    _tokens,
    citations,
    cited_values,
    miscited,
    place_text,
)
from qsone.engine.truth.claims import (  # noqa: F401
    _ADDED,
    _CLAIMS,
    _CONDITION,
    _IMPORTED,
    _NOT,
    _PRICED_DONE,
    _UNDER_WAY,
    _has_content,
    document_claims,
    overclaim,
    promise,
    undone,
)
from qsone.engine.truth.cleaning import (  # noqa: F401
    _JSON_FENCE,
    _JSON_START,
    _json_lines,
    clean_reply,
    has_json,
)
from qsone.engine.truth.clock import CAIRO, today, today_line  # noqa: F401
from qsone.engine.truth.letters import (  # noqa: F401
    _BID_FIELDS,
    _D,
    _DATE_ISO,
    _DATE_SLASH,
    _DATE_WORDS,
    _DAYS,
    _MONTH_WORDS,
    _MONTHS,
    _PERCENT,
    _TERM_UNIT,
    _TOTAL,
    _VAT_AMOUNT,
    _WITH_VAT,
    TERMS,
    _n,
    _term_values,
    dates_in,
    file_dates,
    file_terms,
    letter_problems,
)
from qsone.engine.truth.problem import Problem  # noqa: F401
from qsone.engine.truth.quotes import (  # noqa: F401
    _INSTALL,
    _SUPPLY_ITEM,
    covers_labour,
    supply_only_item,
)
from qsone.engine.truth.reads import (  # noqa: F401
    _TENDER_ABSENCE,
    _TENDER_QUESTION,
    read_passages,
    reading_problems,
    tender_search_problem,
    unread_citations,
)
from qsone.engine.truth.records import Brief, Coverage, coverage  # noqa: F401
from qsone.engine.truth.reply import _CONTRACT, DELIVERABLES, facts, reply_problems  # noqa: F401
from qsone.engine.truth.sources import (  # noqa: F401
    _NEAR,
    _PER_DAY,
    _PLACE_KEYS,
    file_text,
    per_day,
    per_day_at,
    says_per_day,
    texts_at,
    value_at,
    value_in,
)
from qsone.engine.truth.words import (  # noqa: F401
    _ALL,
    _ARABIC,
    _ASK_ENGINEER,
    _BRACKETED_ENGLISH,
    _CARD,
    _CHANGED,
    _DELIVERABLE_READY,
    _DIGITS,
    _DONE,
    _INTEGER,
    _LABOUR_CLAIM,
    _LATIN,
    _OFFER,
    _PROMISE,
    _SENTENCE,
    _TABLE_ROW,
    _TO_TEAM,
    PRICED,
    _integers,
    _sentences,
    arabic,
)
from qsone.records import boq  # noqa: F401
