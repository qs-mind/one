"""The Deliverables in the core API (Plan 6 Task 7): the screen is the engineer, every route needs
the bearer secret, refusals are {"error": {en, ar}, "field"} (synthetic «عينة» data only)."""

import json
import threading
import time
from urllib.parse import quote

import httpx
import pytest
from fastapi.testclient import TestClient

from qsone import activity, copy
from qsone.app import create_app
from qsone.deliverables import events, review, store
from qsone.records import files, ledger
from tests.conftest import AUTH, SECRET
from tests.samples import (
    CLIENT_FIRST_ROW,
    sample_client_xlsx,
    sample_document,
    sample_sheet,
    sample_source,
)

NOWHERE = "0" * 32  # a well-formed id with nothing behind it


@pytest.fixture
def client(data_dir):
    with TestClient(create_app(SECRET, data_dir=data_dir)) as client:
        yield client


@pytest.fixture
def project(client):
    return client.post("/projects", json={"name": "مدرسة - عينة"}, headers=AUTH).json()["id"]


def records(client, project):
    return client.app.state.projects.get(project)


def get(client, path: str, **params):
    return client.get(path, params=params, headers=AUTH)


def post(client, path: str, body=None, **params):
    return client.post(path, json=body, params=params, headers=AUTH)


def item(v: dict, code: str) -> dict:
    return next(r for r in v["rows"] if r.get("code") == code)


def cell(v: dict, row_id: str, key: str) -> dict:
    return next(r for r in v["rows"] if r["id"] == row_id)["cells"][key]


def check_a(rec, d: str) -> None:
    review.record_check(
        rec, d, version_n=store.view(rec, d)["version"], code="A", checker="model-sample",
        same_provider=False, summary="", comments=[],
    )  # fmt: skip


@pytest.fixture
def sheet(client, project):
    """(base path, deliverable id) of a sample priced BOQ Sheet."""
    d = sample_sheet(records(client, project))
    return f"/projects/{project}/deliverables/{d}", d


# Reading -----------------------------------------------------------------------------------


def test_list_and_view(client, project, sheet):
    path, d = sheet
    [entry] = get(client, f"/projects/{project}/deliverables").json()["deliverables"]
    plan7 = {"id", "kind", "title", "language", "status", "code", "same_provider", "revision"}
    plan7 |= {"desk", "off_desk", "progress", "open_comments", "updated_at"}
    assert plan7 <= set(entry) and entry["id"] == d and entry["status"] == "draft"
    v = get(client, path).json()
    assert v["id"] == d and v["version"] == 1 and v["kind"] == "sheet"
    froms = {c["key"]: c["from"] for c in v["columns"]}
    assert froms["rate"] == "number:rate" and froms["code"] == "code"  # the sheet's pasteOps
    assert item(v, "03/02")["cells"]["amount"]["value"] == "4782060.00"


def test_a_view_with_moved_records_brings_its_update(client, project, sheet):
    path, d = sheet
    rec = records(client, project)
    rate = item(store.view(rec, d), "03/02")["cells"]["rate"]
    ledger.correct_number(
        rec, rate["number_id"], value="40000", reason="عرض جديد - عينة",
        source_id=sample_source(rec), dated="2026-11-04", actor="estimator",
    )  # fmt: skip
    v = get(client, path).json()
    assert v["records_moved"] and v["pending"] == 1  # made current before the view is sent
    assert item(v, "03/02")["cells"]["rate"]["value"] == "39850.50"  # pinned until accepted
    [change] = get(client, f"{path}/changes", status="pending").json()["changes"]
    assert change["op"]["op"] == "update_from_records" and change["author"] == "calc_engine"
    other = item(v, "1-1")["id"]
    r = post(client, f"{path}/changes", {"ops": [{"op": "set_field", "row": other,
             "key": "description", "value": "حفر - عينة"}]})  # fmt: skip
    r = post(client, f"{path}/changes/accept", {"ids": [r.json()["changes"][0]["id"]]})
    assert r.status_code == 409
    assert r.json() == {"error": copy.UPDATE_FIRST, "field": "ids"}
    out = post(client, f"{path}/changes/accept", {"ids": [change["id"]]}).json()
    assert out["version"] == 2 and out["accepted"] == [change["id"]]
    assert item(get(client, path).json(), "03/02")["cells"]["rate"]["value"] == "40000"


# Changes -----------------------------------------------------------------------------------


def test_edit_accept_and_see_it(client, project, sheet):
    path, d = sheet
    row = item(get(client, path).json(), "1-1")
    op = {"op": "set_number", "row": row["id"], "name": "rate", "value": "٣٩٨٥٠٫٥٠"}
    r = post(client, f"{path}/changes", {"ops": [op], "reason": None})
    assert r.status_code == 201
    [change] = r.json()["changes"]
    assert change["author"] == "engineer" and change["status"] == "pending"
    assert change["before"]["value"] == "14" and change["after"]["value"] == "39850.50"
    assert {f["column"] for f in change["follows"] if f["row"] == row["id"]} == {"amount"}
    out = post(client, f"{path}/changes/accept", {"mine": True}).json()
    assert out == {"version": 2, "accepted": [change["id"]], "stale": []}
    v = get(client, path).json()
    assert cell(v, row["id"], "rate")["value"] == "39850.50" and v["version"] == 2
    assert get(client, f"{path}/changes").json()["changes"][0]["status"] == "accepted"


def test_reject_and_refusals_name_the_field(client, project, sheet):
    path, d = sheet
    row = item(get(client, path).json(), "03/02")
    r = post(client, f"{path}/changes", {"ops": [{"op": "set_number", "row": row["id"],
             "name": "amount", "value": "1"}]})  # fmt: skip
    assert r.status_code == 422 and r.json() == {
        "error": copy.AMOUNT_IS_COMPUTED,
        "field": "ops[0].name",
    }
    r = post(client, f"{path}/changes", {"ops": [{"op": "drop_table"}]})
    assert r.status_code == 422 and r.json()["field"] == "ops[0].op"
    r = post(client, f"{path}/changes", {"ops": [{"op": "set_number", "row": row["id"],
             "name": "rate", "value": "1"}]})  # fmt: skip
    [change] = r.json()["changes"]
    assert post(client, f"{path}/changes/reject", {"ids": [change["id"]]}).json() == {
        "rejected": [change["id"]]
    }
    r = post(client, f"{path}/changes/reject", {"ids": [change["id"]]})
    assert r.status_code == 409 and r.json() == {
        "error": copy.CHANGE_NOT_PENDING,
        "field": "ids[0]",
    }


def test_a_document_block_change_carries_its_word_segments(client, project):
    rec = records(client, project)
    d = sample_document(rec, sample_sheet(rec))
    path = f"/projects/{project}/deliverables/{d}"
    v = get(client, path).json()
    block = next(b for b in v["blocks"] if "حالياً" in json.dumps(b, ensure_ascii=False))
    node = {"type": "p", "children": [{"text": "الأسعار سارية حالياً لمدة ٤٥ يوماً"}]}
    r = post(client, f"{path}/changes", {"ops": [{"op": "set_block", "block": block["id"],
             "node": node}, {"op": "remove_block", "block": v["blocks"][0]["id"]}]})  # fmt: skip
    edit, removal = r.json()["changes"]
    assert {"op": "del", "text": "٣٠"} in edit["segments"]
    assert {"op": "ins", "text": "٤٥"} in edit["segments"]
    assert removal["segments"] == [{"op": "del", "text": "خطاب تقديم العطاء - عينة"}]
    [listed, _] = get(client, f"{path}/changes", status="pending").json()["changes"]
    assert listed["segments"] == edit["segments"]


# Versions and compare ----------------------------------------------------------------------


def test_versions_and_compare(client, project, sheet):
    path, d = sheet
    rec = records(client, project)
    row = item(get(client, path).json(), "03/02")
    r = post(client, f"{path}/changes", {"ops": [{"op": "set_number", "row": row["id"],
             "name": "rate", "value": "40000.00"}]})  # fmt: skip
    post(client, f"{path}/changes/accept", {"mine": True})
    assert post(client, f"{path}/revisions").json() == {"no": 1}
    out = get(client, f"{path}/versions").json()
    assert [(v["n"], v["changes"]) for v in out["versions"]] == [
        (1, []),
        (2, [r.json()["changes"][0]["id"]]),
    ]
    assert out["revisions"] == [
        {
            "no": 1,
            "version_n": 2,
            "issued_at": out["revisions"][0]["issued_at"],
            "signed_off": False,
        }
    ]
    diff = get(client, f"{path}/compare", **{"from": "v:1", "to": "r:1"}).json()
    changed = next(x for x in diff["rows"] if x["id"] == row["id"])
    assert changed["change"] == "changed" and diff["total"]["from"] != diff["total"]["to"]
    assert changed["cells"]["rate"]["from"]["value"] == "39850.50"
    assert changed["cells"]["rate"]["to"]["value"] == "40000.00"
    assert get(client, path, version=1).json()["version"] == 1
    assert get(client, path, revision=1).json()["revision"]["no"] == 1
    r = get(client, f"{path}/compare", **{"from": "v:9", "to": "v:1"})
    assert r.status_code == 404 and r.json()["field"] == "version"
    r = get(client, f"{path}/compare", **{"from": "x", "to": "v:1"})
    assert r.status_code == 404 and r.json()["field"] == "from"
    assert store.view(rec, d)["version"] == 2


# Comments ----------------------------------------------------------------------------------


def test_comments_from_the_screen_are_review_comments(client, project, sheet):
    path, d = sheet
    row = item(get(client, path).json(), "03/02")
    anchor = {"type": "cell", "row": row["id"], "column": "rate"}
    body = {"anchor": anchor, "body": "راجع الفئة - عينة", "code": "C", "kind": "note",
            "author": "lead_qs"}  # fmt: skip
    r = post(client, f"{path}/comments", body)
    assert r.status_code == 201
    thread = r.json()
    assert thread["kind"] == "review" and thread["author"] == "engineer" and thread["code"] == "C"
    assert thread["anchor_now"] == anchor and thread["replies"] == []
    base = f"/projects/{project}/comments/{thread['id']}"
    replied = post(client, f"{base}/replies", {"body": "تمام - عينة"}).json()
    assert replied["id"] == thread["id"] and replied["replies"][0]["body"] == "تمام - عينة"
    reply_id = replied["replies"][0]["id"]
    assert (
        post(client, f"/projects/{project}/comments/{reply_id}/close").json()["status"] == "closed"
    )
    assert post(client, f"{base}/reopen").json()["status"] == "open"
    text = post(client, f"{base}/fix", lang="ar").json()["text"]
    assert thread["id"] in text and "«03/02»" in text
    assert [t["id"] for t in get(client, f"{path}/comments", status="open").json()["comments"]] == [
        thread["id"]
    ]
    r = post(client, f"{path}/comments", {"anchor": anchor, "body": "  "})
    assert r.status_code == 422 and r.json() == {"error": copy.COMMENT_NEEDS_TEXT, "field": "body"}
    r = post(client, f"/projects/{project}/comments/{NOWHERE}/close")
    assert r.status_code == 404 and r.json()["error"] == copy.COMMENT_NOT_FOUND


def test_the_screen_cannot_act_as_an_agent(client, project, sheet):
    path, d = sheet
    row = item(get(client, path).json(), "1-1")
    r = post(client, f"{path}/changes", {"ops": [{"op": "set_number", "row": row["id"],
             "name": "rate", "value": "15"}], "author": "lead_qs"})  # fmt: skip
    assert r.json()["changes"][0]["author"] == "engineer"
    for route in ("checks", "check", "notes", "review"):
        assert post(client, f"{path}/{route}", {"code": "A"}).status_code in (404, 405), route
    r = post(client, f"{path}/comments", {"anchor": {"type": "deliverable"}, "body": "x",
             "code": "A"})  # fmt: skip
    assert r.status_code == 422 and r.json()["field"] == "code"  # only B or C, never a check


# Close-out and Sign-off --------------------------------------------------------------------


def test_signoff_answers_with_the_blocking_reason(client, project, sheet):
    path, d = sheet
    out = get(client, f"{path}/closeout").json()
    assert out["can_sign_off"] is False and out["reasons"] == [copy.SIGNOFF_NEEDS_CHECK]
    r = post(client, f"{path}/signoff")
    assert r.status_code == 409 and r.json() == {"error": copy.SIGNOFF_NEEDS_CHECK, "field": None}
    check_a(records(client, project), d)
    assert get(client, f"{path}/closeout").json()["can_sign_off"] is True
    assert post(client, f"{path}/signoff").json() == {"revision": 1}
    assert get(client, path).json()["status"] == "signed_off"
    r = post(client, f"{path}/signoff")
    assert r.status_code == 409 and r.json()["error"] == copy.ALREADY_SIGNED_OFF


# Exports -----------------------------------------------------------------------------------


def disposition_name(r) -> str:
    header = r.headers["content-disposition"]
    assert header.startswith("attachment; filename=")
    encoded = header.split("filename*=UTF-8''", 1)[1]
    return encoded


def test_export_names_are_utf8(client, project, sheet):
    path, d = sheet
    r = get(client, f"{path}/export", format="xlsx")
    assert r.status_code == 200 and r.content[:2] == b"PK"
    assert r.headers["content-type"].startswith("application/vnd.openxmlformats")
    name = "جدول الكميات - عينة - مسودة.xlsx"
    assert disposition_name(r) == quote(name, safe="")
    assert "%D9%85%D8%B3" in r.headers["content-disposition"]  # «مس» of «مسودة»
    r = get(client, f"{path}/export", format="docx")
    assert r.status_code == 422
    assert r.json() == {"error": copy.EXPORT_FORMAT_NOT_ALLOWED, "field": "format"}
    r = get(client, f"{path}/export", format="pdf")
    assert r.status_code == 200 and r.content[:5] == b"%PDF-"
    assert r.headers["content-type"] == "application/pdf"


def test_a_signed_off_revision_exports_with_its_review_report(client, project, sheet):
    path, d = sheet
    rec = records(client, project)
    check_a(rec, d)
    post(client, f"{path}/signoff")
    r = get(client, f"{path}/export", format="xlsx", revision=1)
    assert disposition_name(r) == quote("جدول الكميات - عينة - إصدار 1.xlsx", safe="")
    r = get(client, f"{path}/review-report", revision=1, format="pdf")
    assert r.status_code == 200 and r.content[:5] == b"%PDF-"
    assert "%D8%AA%D9%82%D8%B1%D9%8A%D8%B1" in disposition_name(r)  # «تقرير»
    r = get(client, f"{path}/review-report", revision=2, format="pdf")
    assert r.status_code == 404 and r.json()["field"] == "revision"


# The client's file -------------------------------------------------------------------------


def test_fill_preview_mismatches_and_file(client, project, sheet):
    path, d = sheet
    rec = records(client, project)
    from qsone.clientfile import fill

    v = store.view(rec, d)
    file_id = files.add_file(
        rec, "مقايسة العميل - عينة.xlsx", sample_client_xlsx(), actor="engineer"
    ).id
    rows = [r for r in v["rows"] if r["kind"] == "item"]
    rows[0], rows[1] = rows[1], rows[0]  # two client rows map to each other's items
    plan = fill.save_plan(rec, d, file_id, {
        "sheet": "BOQ", "header_row": 11, "write": ["rate"],
        "columns": {"code": "A", "description": "B", "rate": "E", "amount": "F"},
        "rows": [{"row": CLIENT_FIRST_ROW + i, "part": r["id"]} for i, r in enumerate(rows)],
    }, actor="lead_qs")  # fmt: skip
    base = f"/projects/{project}/fill-plans/{plan}"
    r = get(client, f"{base}/preview")
    assert r.status_code == 409 and r.json() == {"error": copy.FILL_NEEDS_SIGNOFF, "field": None}
    check_a(rec, d)
    post(client, f"{path}/signoff")
    out = get(client, f"{base}/preview").json()
    assert out["writes"] and out["mismatches"]
    rows_off = [m["row"] for m in out["mismatches"]]
    r = get(client, f"{base}/file")
    assert r.status_code == 409 and r.json()["field"].startswith("rows[")
    out = post(client, f"{base}/accept-mismatches", {"rows": rows_off}).json()
    assert all(m["accepted"] for m in out["mismatches"])
    r = get(client, f"{base}/file")
    assert r.status_code == 200 and r.content[:2] == b"PK"
    assert disposition_name(r) == quote("مقايسة العميل - عينة - QS Mind One.xlsx", safe="")
    r = get(client, f"/projects/{project}/fill-plans/{NOWHERE}/preview")
    assert r.status_code == 404 and r.json()["error"] == copy.FILL_PLAN_NOT_FOUND


def test_a_sheet_lists_its_fill_plans_newest_first(client, project, sheet):
    """The screen finds a Sheet's Fill Plans here: the client's file name, when it was made and
    whether it can fill yet. The ids are for the routes, never shown."""
    path, d = sheet
    rec = records(client, project)
    from qsone.clientfile import fill

    assert get(client, f"{path}/fill-plans").json() == {"plans": []}
    v = store.view(rec, d)
    file_id = files.add_file(
        rec, "مقايسة العميل - عينة.xlsx", sample_client_xlsx(), actor="engineer"
    ).id
    first_row = next(r for r in v["rows"] if r["kind"] == "item")
    plan = {
        "sheet": "BOQ", "header_row": 11, "write": ["rate"], "columns": {"rate": "E"},
        "rows": [{"row": CLIENT_FIRST_ROW, "part": first_row["id"]}],
    }  # fmt: skip
    heard = []
    stop = events.listen(lambda p, event: heard.append((p, event["deliverable"]["id"])))
    try:
        older = fill.save_plan(rec, d, file_id, plan, actor="lead_qs")
    finally:
        stop()
    assert heard == [(project, d)]  # an open review board loads the plan
    [found] = get(client, f"{path}/fill-plans").json()["plans"]
    assert set(found) == {"id", "file_name", "created_at", "status"}
    assert found["id"] == older and found["file_name"] == "مقايسة العميل - عينة.xlsx"
    assert found["status"] == "needs_signoff" and found["created_at"]
    check_a(rec, d)
    post(client, f"{path}/signoff")
    newer = fill.save_plan(rec, d, file_id, plan, actor="lead_qs")
    plans = get(client, f"{path}/fill-plans").json()["plans"]
    assert [p["id"] for p in plans] == [newer, older]
    assert {p["status"] for p in plans} == {"ready"}
    other = sample_sheet(rec)  # another Sheet's list is its own
    r = get(client, f"/projects/{project}/deliverables/{other}/fill-plans")
    assert r.json() == {"plans": []}
    r = get(client, f"/projects/{project}/deliverables/{NOWHERE}/fill-plans")
    assert r.status_code == 404 and r.json()["error"] == copy.DELIVERABLE_NOT_FOUND


# Live events -------------------------------------------------------------------------------


def test_activity_reports_a_new_version(serve_app, data_dir):
    app = create_app(SECRET, data_dir=data_dir)
    url = serve_app(app)
    with httpx.Client(timeout=10, headers=AUTH) as client:
        project = client.post(f"{url}/projects", json={"name": "مدرسة - عينة"}).json()["id"]
        d = sample_sheet(app.state.projects.get(project))
        path = f"{url}/projects/{project}/deliverables/{d}"
        row = item(client.get(path).json(), "1-1")
        with client.stream("GET", f"{url}/projects/{project}/activity") as stream:
            deadline = time.monotonic() + 10
            while project not in activity.HUB._subscribers:  # the stream is listening
                assert time.monotonic() < deadline
                time.sleep(0.01)

            def edit():
                with httpx.Client(timeout=10, headers=AUTH) as other:
                    op = {"op": "set_number", "row": row["id"], "name": "rate", "value": "15"}
                    other.post(f"{path}/changes", json={"ops": [op]})
                    other.post(f"{path}/changes/accept", json={"mine": True})

            threading.Thread(target=edit, daemon=True).start()
            events = []
            for line in stream.iter_lines():
                if line.startswith("data: "):
                    events.append(json.loads(line[6:]))
                    if events[-1]["deliverable"]["pending"] == 0 and len(events) > 1:
                        break
    assert {e["type"] for e in events} == {"deliverable"}
    assert events[0]["deliverable"]["id"] == d and events[0]["deliverable"]["pending"] == 1
    assert events[-1]["deliverable"]["status"] == "draft"


# The secret and the ids --------------------------------------------------------------------

ROUTES = [
    ("GET", "/deliverables"),
    ("GET", "/deliverables/{d}"),
    ("GET", "/deliverables/{d}/changes"),
    ("POST", "/deliverables/{d}/changes"),
    ("POST", "/deliverables/{d}/changes/accept"),
    ("POST", "/deliverables/{d}/changes/reject"),
    ("GET", "/deliverables/{d}/versions"),
    ("GET", "/deliverables/{d}/compare"),
    ("GET", "/deliverables/{d}/comments"),
    ("POST", "/deliverables/{d}/comments"),
    ("POST", "/comments/{d}/replies"),
    ("POST", "/comments/{d}/close"),
    ("POST", "/comments/{d}/reopen"),
    ("POST", "/comments/{d}/fix"),
    ("GET", "/deliverables/{d}/closeout"),
    ("POST", "/deliverables/{d}/revisions"),
    ("POST", "/deliverables/{d}/signoff"),
    ("GET", "/deliverables/{d}/export"),
    ("GET", "/deliverables/{d}/review-report"),
    ("GET", "/deliverables/{d}/fill-plans"),
    ("GET", "/fill-plans/{d}/preview"),
    ("POST", "/fill-plans/{d}/accept-mismatches"),
    ("GET", "/fill-plans/{d}/file"),
]


def test_routes_need_the_secret(client, project, sheet):
    _, d = sheet
    for method, route in ROUTES:
        path = f"/projects/{project}" + route.format(d=d)
        assert client.request(method, path).status_code == 401, route


@pytest.mark.parametrize("bad", ["..x", "x" * 32, "A" * 32, "0" * 31, "%2e%2e%2fx"])
def test_bad_ids_never_reach_the_file(client, project, bad):
    for method, route in ROUTES[1:]:
        path = f"/projects/{project}" + route.format(d=bad)
        r = client.request(method, path, headers=AUTH, json={})
        assert r.status_code == 404, (route, bad)
    r = client.get(f"/projects/{bad}/deliverables", headers=AUTH)
    assert r.status_code == 404
    r = get(client, f"/projects/{project}/deliverables/{NOWHERE}")
    assert r.status_code == 404
    assert r.json() == {"error": copy.DELIVERABLE_NOT_FOUND, "field": "deliverable"}
