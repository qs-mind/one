"""Revalidate existing evidence after replacement; never retain a previous confirmation."""

import json
import re

from qsone.records import files
from qsone.records.arabic import clean
from qsone.records.mapping import store


def _text(value):
    return re.sub(r"(?<=\d),(?=\d{3}(?:\D|$))", "", clean(value)).casefold()


def revalidate(rec, file_id):
    info = files.file_info(rec, file_id)
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
        if not info.replaces:
            return
        old = store.rows(c, "SELECT * FROM map_facts WHERE file_id=?", (info.replaces,))
        pieces = [
            (text, json.loads(loc))
            for text, loc in c.execute(
                "SELECT text,locator FROM chunks WHERE file_id=?", (file_id,)
            )
        ]
        for raw in old:
            fact = store.decoded(raw)
            value = fact["corrected_value"] or fact["value"]
            if not value or fact["state"] == "blank":
                continue
            locator = fact["locator"]
            matched = None
            for text, loc in pieces:
                if any(
                    loc.get(k) != locator[k]
                    for k in ("page", "sheet", "row", "paragraph")
                    if k in locator
                ):
                    continue
                if re.search(r"(?<![\w.])" + re.escape(_text(value)) + r"(?![\w.])", _text(text)):
                    matched = loc
                    break
            if matched is None:
                continue
            # Idempotent worker resume: the current source/name/value already exists.
            if c.execute(
                "SELECT 1 FROM map_facts WHERE file_id=? AND name=? AND value=? "
                "AND valid_until IS NULL",
                (file_id, raw["name"], value),
            ).fetchone():
                continue
            fact.pop("id")
            fact.update(
                file_id=file_id,
                value=value,
                valid_until=None,
                confirmed_by=None,
                confirmed_at=None,
                corrected_value=None,
                conflict_with=[],
                state="found",
                locator=matched,
                box=matched.get("box"),
            )
            store.write(c, rec, "map_facts", fact)
