"""The append-only audit trail. Callers write it in the same transaction as the change;
triggers in the file refuse any edit or delete."""

import json


def _dump(value: dict | None) -> str | None:
    return None if value is None else json.dumps(value, ensure_ascii=False)


def record(
    conn,
    *,
    at: str,
    actor: str,
    action: str,
    table: str,
    row_id: str,
    before: dict | None,
    after: dict | None,
) -> None:
    conn.execute(
        "INSERT INTO audit(at, actor, action, table_name, row_id, before, after)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (at, actor, action, table, row_id, _dump(before), _dump(after)),
    )


def history(conn, row_id: str) -> list[dict]:
    """Every audit row for one row, oldest first."""
    rows = conn.execute(
        "SELECT at, actor, action, table_name, row_id, before, after FROM audit"
        " WHERE row_id = ? ORDER BY id",
        (row_id,),
    )
    return [
        {
            "at": at,
            "actor": actor,
            "action": action,
            "table": table,
            "row_id": rid,
            "before": None if before is None else json.loads(before),
            "after": None if after is None else json.loads(after),
        }
        for at, actor, action, table, rid, before, after in rows
    ]
