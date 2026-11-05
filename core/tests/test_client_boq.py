"""The imported client BOQ on the canvas (a read-only Client BOQ frame, live and kept), and the
Checking QS's code check of Priced BOQ rows that are not in it. Scripted hosts and checkers
only; synthetic «عينة» workbooks only."""

import json

import pytest
from fastapi.testclient import TestClient

from qsone import activity, copy
from qsone.app import create_app
from qsone.clientfile import imported
from qsone.deliverables import comments, review, store
from qsone.engine.tools import call
from qsone.engine.types import Review
from qsone.records import ledger
from qsone.records.files import add_file
from qsone.tools import boq as boq_tools  # noqa: F401 - registers boq_import
from tests.conftest import AUTH, SECRET
from tests.engine_fakes import SONNET
from tests.fakes_tools import tool_ctx
from tests.samples import SAMPLE_ACTOR, sample_boq_xlsx, sample_source

COLUMNS = {"code": "A", "description": "B", "unit": "C", "quantity": "D", "rate": "E"}
ROWS = [
    ["", "أعمال الخرسانة - عينة", "", "", ""],
    ["03/02", "خرسانة مسلحة للأسقف - عينة", "م3", 120.5, 39850.5],
    ["03/03", "خرسانة مسلحة للأعمدة - عينة", "م3", 38, 41000],
]
NAME = "مقايسة العميل - عينة.xlsx"
KEEP_ALL = json.dumps({"choice": "keep", "rows_ok": list(range(len(COLUMNS)))})


def ctx_for(rec):
    return tool_ctx(rec, answers={"rows": KEEP_ALL})


async def import_boq(rec, sheet_rows=ROWS, **args) -> str:
    file_id = add_file(rec, NAME, sample_boq_xlsx(sheet_rows), actor="engineer").id
    await run_import(rec, file_id, **args)
    return file_id


async def run_import(rec, file_id: str, **args) -> str:
    asked = {"file_id": file_id, "sheet": "BOQ", "header_row": 3, "columns": COLUMNS}
    return await call("boq_import", asked | {"currency": "EGP"} | args, ctx_for(rec))


def boq_items(rec) -> dict[str, str]:
    """{code: item id} of the imported items."""
    with rec.read() as c:
        return dict(c.execute("SELECT code, id FROM items WHERE kind = 'boq_item'").fetchall())


def priced_sheet(rec, item_ids: list[str], extra: list[tuple[str, str]] = ()) -> str:
    """A Priced BOQ of these items, plus `extra` items (code, description) priced at a sample
    rate: items of our own, not the client's."""
    source = sample_source(rec)
    ours = []
    with rec.write(SAMPLE_ACTOR) as c:
        at = rec.clock()
        for code, description in extra:
            item_id = ledger.write_item(
                c, at=at, actor=SAMPLE_ACTOR, kind="boq_item", code=code,
                fields={"description": description},
            )  # fmt: skip
            ledger.write_number(
                c, at=at, actor=SAMPLE_ACTOR, item_id=item_id, name="rate", value="100",
                unit="m3", currency="EGP", source_id=source, dated="2026-11-01",
            )  # fmt: skip
            ours.append(item_id)
    rows = [{"section": "أعمال - عينة", "level": 1}, *({"item_id": i} for i in [*item_ids, *ours])]
    return store.create(
        rec, kind="sheet", variant="boq", title="جدول مسعر - عينة", language="ar",
        actor=SAMPLE_ACTOR, rows=rows,
    )  # fmt: skip


def scripted_checker(code: str = "A"):
    seen = []

    async def checker(packet, maker):
        seen.append(packet)
        return Review(code=code, comments=(), checker=SONNET.choice, same_provider=False, round=1)

    return checker, seen


def row_comments(rec, d: str) -> list[dict]:
    return [t for t in comments.list_comments(rec, d) if t["anchor"]["type"] == "row"]


# The Client BOQ frame ------------------------------------------------------------------------


async def test_an_import_is_a_read_only_client_boq_sheet(rec):
    f = await import_boq(rec)
    [entry] = imported.list_imported(rec)
    assert entry | {"at": None} == {
        "file_id": f,
        "name": NAME,
        "items": 2,
        "headings": 1,
        "at": None,
    }
    v = imported.sheet(rec, f)
    assert v["kind"] == "sheet" and v["variant"] == "client_boq" and v["title"] == NAME
    assert v["language"] == "ar" and v["sample"] is False
    assert [c["key"] for c in v["columns"]] == ["code", "description", "unit", "quantity", "rate"]
    assert not any(c["edit"] for c in v["columns"])  # the client's document: never edited here
    section, first, second = v["rows"]
    assert section["kind"] == "section" and section["title"] == "أعمال الخرسانة - عينة"
    assert first["code"] == "03/02" and first["cells"]["description"]["text"].startswith("خرسانة")
    assert first["cells"]["unit"] == {"text": "م3"}
    assert (first["cells"]["quantity"]["value"], first["cells"]["rate"]["value"]) == (
        "120.5",
        "39850.5",
    )
    assert second["code"] == "03/03"
    source = v["sources"][first["cells"]["rate"]["source"]]
    assert source["file_id"] == f and source["file_name"] == NAME and source["kind"] == "boq"
    assert source["locator"] | {"dated_how": None} == {
        "sheet": "BOQ",
        "row": 5,
        "column": "E",
        "dated_how": None,
    }


async def test_the_client_boq_shows_what_the_client_wrote_not_later_edits(rec):
    f = await import_boq(rec)
    item_id = boq_items(rec)["03/02"]
    ledger.update_item(rec, item_id, fields={"description": "وصف معدل - عينة"}, actor="engineer")
    first = imported.sheet(rec, f)["rows"][1]
    assert first["cells"]["description"]["text"] == "خرسانة مسلحة للأسقف - عينة"


async def test_the_import_tells_the_canvas_live_and_says_where_the_items_went(rec, monkeypatch):
    events = []
    monkeypatch.setattr(activity, "publish", lambda project, event: events.append((project, event)))
    file_id = add_file(rec, NAME, sample_boq_xlsx(ROWS), actor="engineer").id
    out = await run_import(rec, file_id)
    [(project, event)] = events
    assert project == rec.id and event["type"] == "client_boq"
    assert event["client_boq"]["file_id"] == file_id and event["client_boq"]["items"] == 2
    assert "Client BOQ frame" in out
    await run_import(rec, file_id)  # the same import again writes nothing and tells nobody
    assert len(events) == 1


async def test_importing_more_of_the_same_file_updates_its_one_frame(rec):
    f = await import_boq(rec, rows="4-5")
    assert [e["items"] for e in imported.list_imported(rec)] == [1]
    await run_import(rec, f)
    assert [(e["file_id"], e["items"]) for e in imported.list_imported(rec)] == [(f, 2)]


def test_no_import_no_client_boq(rec):
    assert imported.list_imported(rec) == []
    with pytest.raises(Exception) as e:
        imported.sheet(rec, "f" * 32)
    assert e.value.text == copy.CLIENT_BOQ_NOT_FOUND


@pytest.fixture
def client(data_dir):
    with TestClient(create_app(SECRET, data_dir=data_dir)) as client:
        yield client


async def test_the_canvas_lists_client_boqs_and_serves_each(client):
    project = client.post("/projects", json={"name": "برج - عينة"}, headers=AUTH).json()["id"]
    rec = client.app.state.projects.get(project)
    assert client.get(f"/projects/{project}/canvas", headers=AUTH).json()["client_boqs"] == []
    f = await import_boq(rec)
    layout = client.get(f"/projects/{project}/canvas", headers=AUTH).json()
    assert [e["file_id"] for e in layout["client_boqs"]] == [f]
    frame = {
        "key": f"clientboq:{f}",
        "x": 0,
        "y": 0,
        "w": 960,
        "h": 640,
        "z": 0,
        "collapsed": False,
    }
    body = {"frames": [frame], "removed": []}
    assert (
        client.put(f"/projects/{project}/canvas/frames", json=body, headers=AUTH).status_code == 200
    )
    r = client.get(f"/projects/{project}/client-boq/{f}", headers=AUTH)
    assert r.status_code == 200 and len(r.json()["rows"]) == 3
    r = client.get(f"/projects/{project}/client-boq/{'f' * 32}", headers=AUTH)
    assert r.status_code == 404 and r.json()["error"] == copy.CLIENT_BOQ_NOT_FOUND


# Rows not in the client's BOQ ----------------------------------------------------------------


async def test_a_priced_row_not_in_the_client_boq_is_flagged_on_its_row(rec):
    await import_boq(rec)
    items = boq_items(rec)
    d = priced_sheet(rec, list(items.values()), extra=[("9-9", "سقالات للموقع - عينة")])
    ctx = ctx_for(rec)
    ctx.host.checker, seen = scripted_checker("A")
    await call("submit_for_check", {"deliverable_id": d}, ctx)
    [packet] = seen
    [flag] = packet.not_in_client_boq
    assert (flag["code"], flag["description"]) == ("9-9", "سقالات للموقع - عينة")
    [thread] = row_comments(rec, d)
    assert thread["anchor"] == {"type": "row", "row": flag["row"]}
    assert (
        thread["body"]
        == "البند ده مش موجود في مقايسة العميل: 9-9 سقالات للموقع - عينة. تسيبه ولا تشيله؟"
    )
    assert (
        thread["author"] == review.CHECKER and thread["status"] == "open" and thread["code"] is None
    )
    gate = review.closeout(rec, d)
    assert gate["blocking"] == []  # the engineer decides; it never blocks Sign-off by itself
    assert copy.SIGNOFF_OPEN_CODE_C not in gate["reasons"]


async def test_the_checking_qs_sees_the_list_in_its_packet_text(rec):
    from qsone.engine import checker

    await import_boq(rec)
    d = priced_sheet(rec, list(boq_items(rec).values()), extra=[("9-9", "سقالات - عينة")])
    ctx = ctx_for(rec)
    ctx.host.checker, seen = scripted_checker()
    await call("submit_for_check", {"deliverable_id": d}, ctx)
    text = checker.packet_text(seen[0], "FENCE")
    assert "not in the client's imported BOQ" in text and "سقالات - عينة" in text


async def test_rows_that_match_the_client_boq_are_not_flagged(rec):
    await import_boq(rec)
    items = boq_items(rec)
    # the client's own items, an item of ours with one of their codes, and one with their words
    d = priced_sheet(
        rec,
        list(items.values()),
        extra=[("03/02", "وصف آخر - عينة"), ("X-1", "خرسانة مسلحة للأعمدة - عينة")],
    )
    assert imported.not_in_client(rec, d) == []
    ctx = ctx_for(rec)
    ctx.host.checker, seen = scripted_checker()
    await call("submit_for_check", {"deliverable_id": d}, ctx)
    assert seen[0].not_in_client_boq == () and row_comments(rec, d) == []


async def test_no_imported_client_boq_no_flag(rec):
    d = priced_sheet(rec, [], extra=[("9-9", "سقالات للموقع - عينة")])
    assert imported.not_in_client(rec, d) == []
    ctx = ctx_for(rec)
    ctx.host.checker, seen = scripted_checker()
    await call("submit_for_check", {"deliverable_id": d}, ctx)
    assert seen[0].not_in_client_boq == () and row_comments(rec, d) == []


async def test_a_re_check_does_not_comment_on_a_row_twice(rec):
    await import_boq(rec)
    d = priced_sheet(rec, list(boq_items(rec).values()), extra=[("9-9", "سقالات - عينة")])
    rows = imported.not_in_client(rec, d)
    verdict = Review(code="B", comments=(), checker=SONNET.choice, same_provider=False, round=1)
    review.record_review(rec, d, verdict, version_n=1, not_in_client=rows)
    [thread] = row_comments(rec, d)
    comments.close(rec, thread["id"], actor="engineer")  # kept: the engineer resolved it
    review.record_review(rec, d, verdict, version_n=1, not_in_client=rows)
    assert [t["status"] for t in row_comments(rec, d)] == ["closed"]
