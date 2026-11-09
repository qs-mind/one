"""The records a reply is checked against: the project's coverage and what one Brief did."""

from dataclasses import dataclass, field

# The records ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class Coverage:
    items: int  # BOQ items in the project
    priced: int  # of them, with a current rate
    deliverables: int  # Deliverables in the project (beside the chat or drafts)
    client: int = 0  # of the priced, the rate the client's BOQ holds (a "boq" source): not ONE's


def coverage(rec) -> Coverage:
    """The project's BOQ items, how many have a current rate, and its Deliverables."""
    with rec.read() as c:
        (items,) = c.execute("SELECT count(*) FROM items WHERE kind = 'boq_item'").fetchone()
        (priced,) = c.execute(
            "SELECT count(DISTINCT i.id) FROM items i JOIN numbers n ON n.item_id = i.id"
            " WHERE i.kind = 'boq_item' AND n.name = 'rate' AND n.valid_until IS NULL"
        ).fetchone()
        (client,) = c.execute(
            "SELECT count(DISTINCT i.id) FROM items i JOIN numbers n ON n.item_id = i.id"
            " JOIN sources s ON s.id = n.source_id WHERE i.kind = 'boq_item' AND n.name = 'rate'"
            " AND n.valid_until IS NULL AND s.kind = 'boq'"
        ).fetchone()
        made = 0
        for table in ("deliverables", "deliverable_drafts"):
            try:
                (n,) = c.execute(f"SELECT count(*) FROM {table}").fetchone()
            except Exception:  # noqa: BLE001 - an older file has no such table
                n = 0
            made += n
    return Coverage(items, priced, made, client)


@dataclass
class Brief:
    """What one Brief did, from its own tool results: the facts its reply is checked against."""

    writes: int = 0  # write tool calls that went through
    deliverables: int = 0  # Deliverables it made
    shown: bool = False  # it showed a view (show)
    understood: bool = False  # the "I understood this" card was saved
    understood_refused: str | None = None  # the last refusal of understood, when not saved
    specialists: tuple[str, ...] = ()  # the names of the specialists it built (en and ar)
    supply_only: tuple[str, ...] = ()  # the titles of supply-only quotes it cited
    tool_names: frozenset[str] = field(default_factory=frozenset)
    done: set[str] = field(default_factory=set)  # the tools with a call that went through
    refused: dict[str, dict] = field(default_factory=dict)  # tool: why ({en, ar}), when its last
    # call was refused (a retry or a "not done") and none went through after
    item_rows: int | None = None  # item rows in the Deliverables it made, and numbers it set or
    # recorded on items; None when it made no Deliverable
