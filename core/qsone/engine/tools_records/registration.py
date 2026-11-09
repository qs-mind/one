"""Registers the records tools and the calc tools, once and in this order, and names
them (`RECORDS_TOOLS`)."""

from qsone import copy
from qsone.calc import tool as calc_tool
from qsone.engine.tools import Tool, register
from qsone.engine.tools_records.calc_adapter import _calc
from qsone.engine.tools_records.file_reads import (
    _CHUNK_DOC,
    _CHUNK_EXAMPLE,
    _SEARCH_DOC,
    _SEARCH_EXAMPLE,
    ChunkArgs,
    SearchArgs,
    _read_chunk,
    _search,
)
from qsone.engine.tools_records.item_writes import (
    _ITEM_DOC,
    _ITEM_EXAMPLE,
    NewItemArgs,
    _add_item_tool,
)
from qsone.engine.tools_records.ledger_reads import (
    _FIND_DOC,
    _FIND_EXAMPLE,
    _NUMBERS_DOC,
    _NUMBERS_EXAMPLE,
    _RANK_DOC,
    _RANK_EXAMPLE,
    FindArgs,
    ItemArgs,
    RankArgs,
    _find_items,
    _ledger_numbers,
    _rank_items,
)
from qsone.engine.tools_records.number_writes import (
    _CORRECTION_DOC,
    _CORRECTION_EXAMPLE,
    _NUMBER_DOC,
    _NUMBER_EXAMPLE,
    CorrectionArgs,
    NumberArgs,
    _correct_number,
    _record_number,
)
from qsone.engine.tools_records.shared import _field
from qsone.engine.tools_records.source_evidence import (
    _SOURCE_DOC,
    _SOURCE_EXAMPLE,
    SourceArgs,
    _add_source_tool,
)

for _tool in (
    Tool(
        "search_records",
        _SEARCH_DOC,
        SearchArgs,
        "read",
        _search,
        lambda a: copy.fill(copy.TOOL_SEARCH_RECORDS, query=a.query),
        untrusted=True,
        example=_SEARCH_EXAMPLE,
    ),
    Tool(
        "read_chunk",
        _CHUNK_DOC,
        ChunkArgs,
        "read",
        _read_chunk,
        lambda a: copy.TOOL_READ_CHUNK,
        untrusted=True,
        example=_CHUNK_EXAMPLE,
    ),
    Tool(
        "find_items",
        _FIND_DOC,
        FindArgs,
        "read",
        _find_items,
        lambda a: copy.TOOL_FIND_ITEMS,
        example=_FIND_EXAMPLE,
        self_paged=True,
    ),
    Tool(
        "ledger_numbers",
        _NUMBERS_DOC,
        ItemArgs,
        "read",
        _ledger_numbers,
        lambda a: copy.fill(copy.TOOL_LEDGER_NUMBERS, item=a.item),
        example=_NUMBERS_EXAMPLE,
    ),
    Tool(
        "rank_items",
        _RANK_DOC,
        RankArgs,
        "read",
        _rank_items,
        lambda a: copy.fill(copy.TOOL_RANK_ITEMS, top=str(a.top), name=_field(a.name)),
        example=_RANK_EXAMPLE,
    ),
    Tool(
        "add_source",
        _SOURCE_DOC,
        SourceArgs,
        "write",
        _add_source_tool,
        lambda a: copy.fill(copy.TOOL_ADD_SOURCE, title=a.title or a.file_id or a.kind),
        writes=True,
        example=_SOURCE_EXAMPLE,
    ),
    Tool(
        "add_item",
        _ITEM_DOC,
        NewItemArgs,
        "write",
        _add_item_tool,
        lambda a: copy.TOOL_ADD_ITEM,
        writes=True,
        example=_ITEM_EXAMPLE,
    ),
    Tool(
        "record_number",
        _NUMBER_DOC,
        NumberArgs,
        "write",
        _record_number,
        lambda a: copy.fill(copy.TOOL_RECORD_NUMBER, name=_field(a.name), item=a.item),
        writes=True,
        example=_NUMBER_EXAMPLE,
    ),
    Tool(
        "correct_number",
        _CORRECTION_DOC,
        CorrectionArgs,
        "write",
        _correct_number,
        lambda a: copy.TOOL_CORRECT_NUMBER,
        writes=True,
        example=_CORRECTION_EXAMPLE,
    ),
    *(_calc(name) for name in calc_tool.TOOLS),
):
    register(_tool)

RECORDS_TOOLS: tuple[str, ...] = (
    "search_records",
    "read_chunk",
    "find_items",
    "ledger_numbers",
    "rank_items",
    "add_source",
    "add_item",
    "record_number",
    "correct_number",
    *calc_tool.TOOLS,
)
