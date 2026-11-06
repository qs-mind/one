"""Recheck links after local mapping.

File replacement expires facts once, in store.expire during files.add_file.
The approved facts pass re-extracts from the new file without old confirmations.
"""

from qsone.records.mapping import store


def revalidate(rec, file_id):
    with rec.write(store.ACTOR) as c:
        # Any live link touching this file must still have two live endpoints.
        links = store.rows(
            c,
            "SELECT * FROM map_links WHERE valid_until IS NULL "
            "AND (from_file_id=? OR to_file_id=?)",
            (file_id, file_id),
        )
        for link in links:
            if any(
                not c.execute(
                    "SELECT 1 FROM files WHERE id=? AND valid_until IS NULL", (link[key],)
                ).fetchone()
                for key in ("from_file_id", "to_file_id")
            ):
                store.write(c, rec, "map_links", {"id": link["id"], "valid_until": rec.clock()})
