"""PDF region comments and number locations, using generated sample PDFs only."""

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from qsone.app import create_app
from qsone.deliverables import comments
from tests.conftest import AUTH, SECRET
from tests.samples import sample_pdf, sample_sheet


@pytest.fixture
async def setup(data_dir):
    app = create_app(SECRET, data_dir=data_dir)

    # This sandbox may not wake an asyncio self-pipe across threads; keep I/O ticks bounded.
    async def pulse():
        while True:
            await asyncio.sleep(0.01)

    task = asyncio.create_task(pulse())
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        client.app = app
        p = (await client.post("/projects", json={"name": "Sample"}, headers=AUTH)).json()["id"]
        f = (
            await client.post(
                f"/projects/{p}/files",
                params={"name": "sample.pdf"},
                content=sample_pdf([["Sample 3,450.00 and 13450", "3450"], ["Other page"]]),
                headers=AUTH,
            )
        ).json()["id"]
        yield client, p, f
    task.cancel()


async def test_value_boxes(setup):
    c, p, f = setup
    url = f"/projects/{p}/files/{f}/pages/1/boxes"
    r = await c.get(url, params={"value": "3450"}, headers=AUTH)
    assert r.status_code == 200
    got = r.json()
    assert (got["width"], got["height"]) == (595, 842)
    assert len(got["boxes"]) == 2
    for x0, y0, x1, y1 in got["boxes"]:
        assert 0 <= x0 < x1 <= 595 and 0 <= y0 < y1 < 100
    assert (await c.get(url, params={"value": "99"}, headers=AUTH)).json()["boxes"] == []
    assert (await c.get(url.replace("/1/", "/9/"), headers=AUTH)).status_code == 404
    assert (await c.get(url)).status_code == 401


async def test_region_thread_create_list_reply_reopen(setup):
    c, p, f = setup
    anchor = {"kind": "file_region", "file_id": f, "page": 2, "box": [10, 20, 90, 60]}
    url = f"/projects/{p}/files/{f}/comments"
    r = await c.post(url, json={"anchor": anchor, "body": "Sample region note"}, headers=AUTH)
    assert r.status_code == 201, r.text
    thread = r.json()
    assert thread["anchor_now"] == anchor
    cid = thread["id"]
    assert (await c.get(url, headers=AUTH)).json()["comments"][0]["id"] == cid
    base = f"/projects/{p}/comments/{cid}"
    assert (
        await c.post(base + "/replies", json={"body": "Sample reply"}, headers=AUTH)
    ).status_code == 200
    assert (await c.post(base + "/close", headers=AUTH)).json()["status"] == "closed"
    assert (await c.post(base + "/reopen", headers=AUTH)).json()["status"] == "open"
    rec = c.app.state.projects.get(p)
    got = comments.list_comments(rec, None)
    assert got[0]["anchor_now"] == anchor and len(got[0]["replies"]) == 1
    with rec.read() as conn:
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


@pytest.mark.parametrize(
    "patch",
    [
        {"page": 0},
        {"page": 3},
        {"page": True},
        {"box": [5, 2, 1, 4]},
        {"box": [-1, 2, 3, 4]},
        {"box": [0, 0, 600, 10]},
        {"file_id": "missing"},
    ],
)
async def test_invalid_region_refused(setup, patch):
    c, p, f = setup
    anchor = {"kind": "file_region", "file_id": f, "page": 1, "box": [10, 20, 90, 60], **patch}
    r = await c.post(
        f"/projects/{p}/files/{f}/comments", json={"anchor": anchor, "body": "Sample"}, headers=AUTH
    )
    assert r.status_code in (404, 422)


async def test_region_on_deliverable(setup):
    c, p, f = setup
    rec = c.app.state.projects.get(p)
    d = sample_sheet(rec)
    anchor = {"kind": "file_region", "file_id": f, "page": 1, "box": [10, 20, 90, 60]}
    comments.add(rec, d, kind="review", anchor=anchor, body="Sample", actor="engineer")
    assert comments.list_comments(rec, d)[0]["anchor_now"] == anchor


async def test_lead_reads_file_comments(setup):
    from qsone.deliverables.tools import deliverable_comment
    from tests.fakes_tools import tool_ctx

    c, p, f = setup
    rec = c.app.state.projects.get(p)
    anchor = {"kind": "file_region", "file_id": f, "page": 1, "box": [10, 20, 90, 60]}
    comments.add(rec, None, kind="review", anchor=anchor, body="Sample question", actor="engineer")
    out = deliverable_comment(tool_ctx(rec), file_id=f)
    assert out["comments"][0]["anchor_now"] == anchor


def test_migration_keeps_old_threads_and_replies(data_dir, monkeypatch):
    from qsone.records import schema
    from qsone.records.project import Records

    migrations = schema.MIGRATIONS
    with monkeypatch.context() as patch:
        patch.setattr(schema, "MIGRATIONS", migrations[:-1])
        rec = Records.create(data_dir / "migration-sample", name="Sample", actor="engineer")
        d = sample_sheet(rec)
        cid = comments.add(
            rec, d, kind="review", anchor={"type": "deliverable"}, body="Sample", actor="engineer"
        )
        comments.reply(rec, cid, body="Sample reply", actor="engineer")
        before = comments.list_comments(rec, d)
        rec.close()
    rec = Records.open(data_dir / "migration-sample")
    try:
        assert comments.list_comments(rec, d) == before
        with rec.read() as conn:
            assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        with pytest.raises(Exception, match="Comments are never deleted"):
            with rec.write("engineer") as conn:
                conn.execute("DELETE FROM comments WHERE id = ?", (cid,))
    finally:
        rec.close()


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_boxes_follow_crop_and_rotation(rec, rotation):
    import io

    import pypdfium2

    from qsone.records import files, regions

    doc = pypdfium2.PdfDocument(sample_pdf([["3450"]]))
    page = doc[0]
    page.set_cropbox(40, 40, 555, 802)
    page.set_rotation(rotation)
    buffer = io.BytesIO()
    doc.save(buffer)
    page.close()
    doc.close()
    f = files.add_file(rec, "sample.pdf", buffer.getvalue(), actor="engineer").id
    got = regions.page_boxes(rec, f, 1, "3450")
    assert (got["width"], got["height"]) == ((515, 762) if rotation in (0, 180) else (762, 515))
    assert len(got["boxes"]) == 1
    x0, y0, x1, y1 = got["boxes"][0]
    assert 0 <= x0 < x1 <= got["width"] and 0 <= y0 < y1 <= got["height"]
    if rotation == 0:
        assert x0 < 100 and y0 < 60
    if rotation == 90:
        assert x0 > got["width"] - 60 and y0 < 100


async def test_checker_rejects_invalid_region(setup):
    from qsone.deliverables.review import record_check
    from qsone.deliverables.store import view
    from qsone.records.project import RecordsError

    c, p, f = setup
    rec = c.app.state.projects.get(p)
    d = sample_sheet(rec)
    with pytest.raises(RecordsError):
        record_check(
            rec,
            d,
            version_n=view(rec, d)["version"],
            code="B",
            checker="sample",
            same_provider=False,
            summary="Sample",
            comments=[
                {
                    "body": "Sample",
                    "anchor": {
                        "kind": "file_region",
                        "file_id": f,
                        "page": 99,
                        "box": [0, 0, 10, 10],
                    },
                }
            ],
        )


def test_region_survives_project_reopen(rec):
    from qsone.records import files
    from qsone.records.project import Records

    f = files.add_file(rec, "sample.pdf", sample_pdf([["3450"]]), actor="engineer").id
    anchor = {"kind": "file_region", "file_id": f, "page": 1, "box": [10, 20, 90, 60]}
    cid = comments.add(rec, None, kind="review", anchor=anchor, body="Sample", actor="engineer")
    folder = rec.folder
    rec.close()
    reopened = Records.open(folder)
    try:
        got = comments.file_comments(reopened, f)
        assert got[0]["id"] == cid and got[0]["anchor_now"] == anchor
    finally:
        reopened.close()


def test_arabic_digits_and_scan_without_text(rec):
    from qsone.records import files, regions

    f = files.add_file(rec, "sample.pdf", sample_pdf([["٣٬٤٥٠٫٠٠"], []]), actor="engineer").id
    assert len(regions.page_boxes(rec, f, 1, "3450")["boxes"]) == 1
    assert regions.page_boxes(rec, f, 2, "3450")["boxes"] == []
