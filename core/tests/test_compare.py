"""Comparing two views of one Deliverable (synthetic «عينة» data only)."""

from qsone.deliverables.changes import accept, accept_mine, pending, propose
from qsone.deliverables.compare import compare, segments
from qsone.deliverables.store import view
from tests.samples import sample_document, sample_sheet


def edit(rec, d: str, *ops: dict) -> int:
    propose(rec, d, list(ops), actor="engineer")
    return accept_mine(rec, d, actor="engineer")["version"]


def by_code(v: dict, code: str) -> dict:
    return next(r for r in v["rows"] if r.get("code") == code)


def test_sheet_compare_by_part_id(rec):
    d = sample_sheet(rec)
    v1 = view(rec, d)
    rate, gone, moving = by_code(v1, "03/02"), by_code(v1, "1-2"), by_code(v1, "2-3")
    first_section = v1["rows"][0]
    edit(
        rec,
        d,
        {"op": "set_number", "row": rate["id"], "name": "rate", "value": "40000"},
        {"op": "remove_row", "row": gone["id"]},
        {"op": "move_row", "row": moving["id"], "after": first_section["id"]},
        {
            "op": "add_item_row",
            "after": rate["id"],
            "code": "2-5",
            "fields": {"description": "عزل أسطح - عينة"},
            "numbers": [{"name": "quantity", "value": "10", "unit": "م2"}],
        },
    )
    v2 = view(rec, d)
    out = compare(v1, v2)
    rows = {r["id"]: r for r in out["rows"]}
    assert rows[rate["id"]]["change"] == "changed"
    cells = rows[rate["id"]]["cells"]
    assert cells["rate"]["from"]["value"] == "39850.50" and cells["rate"]["to"]["value"] == "40000"
    assert cells["amount"]["to"]["value"] == "4800000.00" and set(cells) == {"rate", "amount"}
    assert rows[gone["id"]]["change"] == "removed"
    assert rows[gone["id"]]["cells"]["rate"] == {"from": gone["cells"]["rate"], "to": None}
    assert rows[moving["id"]]["change"] == "moved"
    [added] = [r for r in out["rows"] if r["change"] == "added"]
    assert added["cells"]["description"] == {"from": None, "to": {"text": "عزل أسطح - عينة"}}
    assert rows[by_code(v1, "1-1")["id"]] == {
        "id": by_code(v1, "1-1")["id"],
        "change": "same",
        "cells": {},
    }
    assert out["total"] == {"from": v1["total"], "to": v2["total"]}
    # rows come in the new order, and a removed row stays where it was
    order = [r["id"] for r in out["rows"]]
    assert order.index(gone["id"]) == order.index(by_code(v1, "1-1")["id"]) + 1
    assert order.index(moving["id"]) == 1
    assert compare(v1, v1)["total"] == {"from": v1["total"], "to": v1["total"]}
    assert {r["change"] for r in compare(v1, v1)["rows"]} == {"same"}


def test_a_renamed_section_is_changed(rec):
    d = sample_sheet(rec)
    v1 = view(rec, d)
    section = v1["rows"][0]
    edit(rec, d, {"op": "set_section_title", "row": section["id"], "title": "أعمال الترابة - عينة"})
    [row] = [r for r in compare(v1, view(rec, d))["rows"] if r["id"] == section["id"]]
    assert row["change"] == "changed"
    assert row["cells"]["title"] == {
        "from": {"text": "أعمال الحفر"},
        "to": {"text": "أعمال الترابة - عينة"},
    }


def test_document_compare_word_level_keeps_arabic_words_whole():
    s = segments("الأسعار سارية حالياً لمدة ٣٠ يوماً", "الأسعار سارية حالياً لمدة ٤٥ يوماً")
    assert {"op": "del", "text": "٣٠"} in s and {"op": "ins", "text": "٤٥"} in s
    assert "".join(x["text"] for x in s if x["op"] != "ins") == "الأسعار سارية حالياً لمدة ٣٠ يوماً"
    assert "".join(x["text"] for x in s if x["op"] != "del") == "الأسعار سارية حالياً لمدة ٤٥ يوماً"
    assert s[0] == {"op": "same", "text": "الأسعار سارية حالياً لمدة "}  # neighbours merged
    assert segments("", "نص - عينة") == [{"op": "ins", "text": "نص - عينة"}]
    assert segments("سطر\nثاني", "سطر\nثاني") == [{"op": "same", "text": "سطر\nثاني"}]


def test_document_compare_by_block(rec):
    sheet = sample_sheet(rec)
    d = sample_document(rec, sheet)
    v1 = view(rec, d)
    heading, *_, last = v1["blocks"]
    node = {"type": "p", "children": [{"text": "الأسعار سارية حالياً لمدة ٤٥ يوماً"}]}
    edit(
        rec,
        d,
        {"op": "set_block", "block": last["id"], "node": node},
        {"op": "remove_block", "block": heading["id"]},
        {
            "op": "insert_block",
            "after": None,
            "node": {"type": "h1", "children": [{"text": "خطاب - عينة"}]},
        },
    )
    out = compare(v1, view(rec, d))
    blocks = {b["id"]: b for b in out["blocks"]}
    assert {"op": "del", "text": "٣٠"} in blocks[last["id"]]["segments"]
    assert blocks[last["id"]]["change"] == "changed"
    assert blocks[heading["id"]] == {
        "id": heading["id"],
        "change": "removed",
        "segments": [{"op": "del", "text": "خطاب تقديم العطاء - عينة"}],
    }
    [added] = [b for b in out["blocks"] if b["change"] == "added"]
    assert added["segments"] == [{"op": "ins", "text": "خطاب - عينة"}]
    assert {b["change"] for b in out["blocks"][:2]} == {"added", "removed"}  # both at the top
    total = v1["blocks"][2]
    assert blocks[total["id"]]["change"] == "same"
    # a number reference shows its value, so a new total is a changed block
    rate = next(r for r in view(rec, sheet)["rows"] if r.get("code") == "03/02")
    edit(rec, sheet, {"op": "set_number", "row": rate["id"], "name": "rate", "value": "40000"})
    [update] = pending(rec, d)
    accept(rec, d, [update.id], actor="engineer")
    later = {b["id"]: b for b in compare(v1, view(rec, d))["blocks"]}
    assert later[total["id"]]["change"] == "changed"
    new_total = view(rec, sheet)["total"]["value"]
    assert {"op": "ins", "text": new_total} in later[total["id"]]["segments"]
