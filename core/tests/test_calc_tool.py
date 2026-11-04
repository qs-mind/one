"""The QS Calc Engine's tools for agents and its core API routes (synthetic «عينة» data only)."""

import json

import pytest
from fastapi.testclient import TestClient

from qsone import copy
from qsone.app import create_app
from qsone.calc.tool import TOOLS, call
from qsone.calc.units import BUILT_IN
from qsone.records import ledger
from qsone.records.ledger import correct_number, numbers
from tests.calc_samples import ACTOR, DATED, SOURCES, add, sample_project, source_id
from tests.conftest import AUTH, SECRET

# Integers allowed in a reply: counts, pages, places in a list, character places, the engine.
COUNTS = {"count", "saved", "unchanged", "page", "pages", "seq", "at", "n", "places", "engine"}


@pytest.fixture
def boq(tmp_path):
    """03/02: 120 m3 at 39850.50 EGP/m3; 03/03: 45 m2 at 180.25 EGP/m2; section item "03"."""
    rec = sample_project(tmp_path)
    add(rec, "03/02", quantity=("120", "m3", None, "boq"), rate=("39850.50", "m3", "EGP", "quote"))
    add(rec, "03/03", quantity=("45", "m2", None, "boq"), rate=("180.25", "m2", "EGP", "quote"))
    add(rec, "03", kind="section")
    yield rec
    rec.close()


@pytest.fixture
def build_up(tmp_path):
    """The inputs of the calculate doc's example: a rate for 1 m3 of concrete on 03/02."""
    rec = sample_project(tmp_path)
    add(
        rec,
        "03/02",
        quantity=("120", "m3", None, "boq"),
        cement=("350", "kg/m3", None, "mix_design"),
        gang=("2400", "day", "EGP", "quote"),
        output=("8", "m3/day", None, "mix_design"),
    )
    add(rec, "CEM", kind="resource", price=("3000", "t", "EGP", "quote"))
    yield rec
    rec.close()


def number_of(rec, code: str, name: str) -> str:
    with rec.read() as c:
        return c.execute(
            "SELECT n.id FROM numbers n JOIN items i ON i.id = n.item_id"
            " WHERE i.code = ? AND n.name = ? AND n.valid_until IS NULL",
            (code, name),
        ).fetchone()[0]


def fill_placeholders(value, ids: dict):
    """Each "<…>" string in a tool example becomes the sample id it names."""
    if isinstance(value, dict):
        return {k: fill_placeholders(v, ids) for k, v in value.items()}
    if isinstance(value, list):
        return [fill_placeholders(v, ids) for v in value]
    if isinstance(value, str) and value.startswith("<") and value.endswith(">"):
        return ids[value]
    return value


def strings_only(value, key=None) -> None:
    """Numbers are strings: no float anywhere, and an int only as a count, page or place."""
    assert not isinstance(value, float), key
    if isinstance(value, int) and not isinstance(value, bool):
        assert key in COUNTS, (key, value)
    if isinstance(value, dict):
        for k, v in value.items():
            strings_only(v, k)
    if isinstance(value, list):
        for v in value:
            strings_only(v, key)


# The tools.


def test_every_tool_doc_is_short_and_its_example_runs(build_up):
    ids = {
        "<number id>": number_of(build_up, "03/02", "cement"),
        "<source id>": source_id(build_up, "quote"),
    }
    assert list(TOOLS) == ["calculate", "define_unit", "explain_number", "recalculate"]
    for tool in TOOLS.values():
        assert tool.name in TOOLS and TOOLS[tool.name] is tool
        assert len(tool.doc.split()) <= 250, tool.name
        assert json.dumps(tool.example, ensure_ascii=False) in tool.doc, tool.name
        assert set(tool.description) == {"en", "ar"} and all(tool.description.values())
        tool.request.model_validate(fill_placeholders(tool.example, ids))
        reply = call(build_up, tool.name, fill_placeholders(tool.example, ids), actor="lead-qs")
        assert "error" not in reply, (tool.name, reply)
        strings_only(reply)


def test_the_concrete_rate_example_saves_its_hand_checked_value(build_up):
    reply = call(build_up, "calculate", TOOLS["calculate"].example, actor="lead-qs")
    # 350 kg/m3 × 3000 EGP/t × 1.05 + 2400 EGP/day ÷ 8 m3/day = 1102.50 + 300
    assert [(r["code"], r["value"], r["unit"]) for r in reply["results"]] == [
        ("03/02", "1402.50", "EGP/m3")
    ]
    assert (reply["count"], reply["saved"], reply["unchanged"]) == (1, 1, 0)
    again = call(build_up, "calculate", TOOLS["calculate"].example, actor="lead-qs")
    assert (again["saved"], again["unchanged"], again["results"][0]["unchanged"]) == (0, 1, True)


def test_a_refusal_says_what_to_send(boq):
    reply = call(
        boq,
        "calculate",
        {"formula": "quantity * rat", "item": "03/02", "result": {"unit": "EGP"}},
        actor="lead-qs",
    )
    assert reply["error"] == copy.fill(copy.CALC_UNKNOWN_NAME, name="rat", names="quantity, rate")
    assert reply["key"] == "CALC_UNKNOWN_NAME" and reply["name"] == "rat"
    assert reply["field"] == "formula" and reply["example"]


def test_a_refusal_shows_the_example_for_its_field(boq):
    reply = call(
        boq,
        "calculate",
        {"formula": "quantity * rate", "item": "03/02", "result": {"unit": "EGP"}},
        actor="lead-qs",
    )
    assert reply["results"][0]["value"] == "4782060.00"
    reply = call(
        boq,
        "calculate",
        {"formula": "quantity * rate", "item": "03/02", "result": {"unit": "EGP/m3"}},
        actor="lead-qs",
    )
    assert reply["key"] == "CALC_RESULT_UNIT" and reply["field"] == "result.unit"
    assert json.loads(reply["example"]) == {
        "unit": "EGP",
        "round": {"places": 2, "mode": "half_up"},
    }


def test_shape_errors_are_plain(boq):
    reply = call(boq, "calculate", {"formula": "a", "inputs": {"a": {"num": "x"}}}, actor="lead-qs")
    assert reply["field"] == "inputs.a" and reply["key"] == "CALC_REQUEST_SHAPE"
    assert "validation error" not in json.dumps(reply) and "Field required" not in json.dumps(reply)
    shapes = json.loads(reply["example"])
    assert {"item": "03/02", "name": "rate"} in shapes and len(shapes) == 5
    assert reply["error"]["en"].startswith("The request is not complete at «inputs.a»")


def test_a_shape_error_shows_the_shape_that_was_meant(boq):
    payload = {"formula": "a", "inputs": {"a": {"constant": "5", "unit": "EGP", "why": "عينة"}}}
    reply = call(boq, "calculate", payload, actor="lead-qs")
    assert reply["field"] == "inputs.a"
    assert json.loads(reply["example"]) == {
        "constant": "5",
        "unit": "%",
        "why": "estimator's waste rule",
    }
    reply = call(boq, "calculate", {"formula": "a", "result": {"round": {"places": 99}}}, actor="x")
    assert reply["field"] == "result.round.places"
    reply = call(boq, "calculate", {"formula": "a", "save": {"name": "amount"}}, actor="x")
    assert reply["field"] == "save" and json.loads(reply["example"])["name"] == "amount"
    reply = call(boq, "explain_number", {}, actor="x")
    assert reply["field"] == "number"


def test_ledger_refusals_come_back_as_data(boq):
    src = source_id(boq, "quote")
    unit = {"symbol": "bag", "equals": "50 kg", "source_id": src, "dated": DATED}
    assert call(boq, "define_unit", unit, actor="lead-qs")["equals"] == "50 kg"
    reply = call(boq, "define_unit", unit | {"equals": "25 kg"}, actor="lead-qs")
    assert reply["error"] == copy.CORRECTION_NEEDS_REASON and reply["field"] == "reason"
    assert reply["example"]


def test_define_unit_reply(boq):
    src = source_id(boq, "quote")
    reply = call(
        boq,
        "define_unit",
        {"symbol": "شيكارة", "equals": "٥٠ kg", "source_id": src, "dated": DATED},
        actor="lead-qs",
    )
    assert (reply["symbol"], reply["equals"]) == ("شيكارة", "50 kg")
    with boq.read() as c:
        (value,) = c.execute(
            "SELECT value FROM numbers WHERE id = ?", (reply["number"],)
        ).fetchone()
    assert value == "50"


def test_calculate_reply_is_small(boq):
    for n in range(25):
        add(boq, f"05/{n:02}", quantity=("2", "m3", None, "boq"), rate=("10", "m3", "EGP", "quote"))
    reply = call(
        boq,
        "calculate",
        {
            "formula": "quantity * rate",
            "for_each": {"code_prefix": "05/"},
            "result": {"unit": "EGP"},
            "save": {"name": "amount"},
        },
        actor="lead-qs",
    )
    assert (reply["count"], reply["saved"], reply["unchanged"]) == (25, 25, 0)
    assert len(reply["results"]) == 20 and "steps" not in reply
    assert reply["results"][0] == {
        "item": reply["results"][0]["item"],
        "code": "05/00",
        "value": "20.00",
        "unit": "EGP",
        "exact": True,
        "number": reply["results"][0]["number"],
        "calculation": reply["results"][0]["calculation"],
        "unchanged": False,
        "dated": DATED,
    }
    preview = call(boq, "calculate", {"formula": "quantity * rate", "item": "03/02"}, actor="x")
    assert preview["saved"] == 0 and preview["steps"][-1]["value"] == "4782060.00"


def test_numbers_are_strings_in_every_reply(boq):
    saved = call(
        boq,
        "calculate",
        {
            "formula": "sum(a) * (1 + oh)",
            "inputs": {
                "a": {"each": {"code_prefix": "03/"}, "name": "rate"},
                "oh": {"constant": "10", "unit": "%", "why": "عينة"},
            },
            "item": "03",
            "result": {"unit": "EGP/m3", "round": {"places": 3, "mode": "up"}},
            "save": {"name": "x"},
        },
        actor="lead-qs",
    )
    assert "error" in saved  # m3 and m2 rates do not add
    amount = call(
        boq,
        "calculate",
        {
            "formula": "quantity * rate / 7",
            "item": "03/02",
            "result": {"unit": "EGP"},
            "save": {"name": "amount"},
        },
        actor="lead-qs",
    )
    explained = call(boq, "explain_number", {"number": amount["results"][0]["number"]}, actor="x")
    for reply in (saved, amount, explained):
        strings_only(reply)
    assert explained["calculation"]["inputs"][0]["value"] == "120"
    assert amount["notes"] == [copy.CALC_NOTE_INEXACT]


def test_recalculate_lists_then_applies(boq):
    amount = call(
        boq,
        "calculate",
        {
            "formula": "quantity * rate",
            "item": "03/02",
            "result": {"unit": "EGP"},
            "save": {"name": "amount"},
        },
        actor="lead-qs",
    )
    assert call(boq, "recalculate", {}, actor="x") == {"stale": [], "count": 0}
    correct_number(
        boq,
        number_of(boq, "03/02", "rate"),
        value="40000",
        reason="عرض جديد - عينة",
        source_id=source_id(boq, "quote"),
        dated="2026-11-03",
        actor="engineer",
    )
    listed = call(boq, "recalculate", {"apply": False}, actor="x")
    assert listed["count"] == 1 and listed["stale"][0]["code"] == "03/02"
    assert listed["stale"][0]["calculation"] == amount["results"][0]["calculation"]
    done = call(boq, "recalculate", {"apply": True}, actor="lead-qs")
    assert done["count"] == 1 and done["failed"] == [] and done["waiting"] == []
    assert (done["changes"][0]["was"], done["changes"][0]["now"]) == ("4782060.00", "4800000.00")
    strings_only(listed)
    strings_only(done)


# The core API.


@pytest.fixture
def client(data_dir):
    with TestClient(create_app(SECRET, data_dir=data_dir)) as client:  # lifespan closes projects
        yield client


@pytest.fixture
def project(client):
    """A project made through the API, holding the sample sources and the 03 section."""
    pid = client.post("/projects", json={"name": "مدرسة - عينة"}, headers=AUTH).json()["id"]
    rec = client.app.state.projects.get(pid)
    with rec.write(ACTOR) as conn:
        for kind, title in SOURCES.items():
            ledger.write_source(conn, at=rec.clock(), actor=ACTOR, kind=kind, title=title)
    add(rec, "03/02", quantity=("120", "m3", None, "boq"), rate=("39850.50", "m3", "EGP", "quote"))
    add(rec, "03/03", quantity=("45", "m2", None, "boq"), rate=("180.25", "m2", "EGP", "quote"))
    return pid


AMOUNTS = {
    "formula": "quantity * rate",
    "for_each": {"code_prefix": "03/"},
    "result": {"unit": "EGP"},
    "save": {"name": "amount"},
}


def records(client, pid):
    return client.app.state.projects.get(pid)


def test_http_preview_and_save(client, project):
    preview = {k: v for k, v in AMOUNTS.items() if k != "save"}
    r = client.post(f"/projects/{project}/calc", json=preview, headers=AUTH)
    assert r.status_code == 200
    assert [x["value"] for x in r.json()["results"]] == ["4782060.00", "8111.25"]
    rec = records(client, project)
    with rec.read() as c:
        assert c.execute("SELECT count(*) FROM calculations").fetchone()[0] == 0

    r = client.post(f"/projects/{project}/calc", json=AMOUNTS, headers=AUTH)
    assert r.status_code == 201 and r.json()["saved"] == 2
    with rec.read() as c:
        (by,) = c.execute("SELECT DISTINCT recorded_by FROM calculations").fetchone()
    assert by == "engineer"
    r = client.post(f"/projects/{project}/calc", json=AMOUNTS, headers=AUTH)
    assert r.status_code == 200 and r.json()["unchanged"] == 2


def test_http_refusals_are_the_tool_body(client, project):
    r = client.post(f"/projects/{project}/calc", json={"formula": "1 +"}, headers=AUTH)
    assert r.status_code == 422
    body = r.json()
    assert body["key"] == "CALC_UNEXPECTED" and body["field"] == "formula" and body["error"]["ar"]
    r = client.post(f"/projects/{project}/calc", json={"formula": "a", "bad": 1}, headers=AUTH)
    assert r.status_code == 422 and r.json()["field"] == "bad" and "detail" not in r.json()


def test_http_explain_a_number(client, project):
    saved = client.post(f"/projects/{project}/calc", json=AMOUNTS, headers=AUTH).json()
    number = saved["results"][0]["number"]
    r = client.get(f"/projects/{project}/numbers/{number}/explain", headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert body["source"]["kind"] == "calculation"
    assert {i["name"]: i["source"]["title"] for i in body["calculation"]["inputs"]} == {
        "quantity": SOURCES["boq"],
        "rate": SOURCES["quote"],
    }
    r = client.get(f"/projects/{project}/numbers/{number}/explain?page=2", headers=AUTH)
    assert r.json()["calculation"]["page"] == 2 and r.json()["calculation"]["inputs"] == []
    r = client.get(f"/projects/{project}/numbers/{'0' * 32}/explain", headers=AUTH)
    assert r.status_code == 422 and r.json()["key"] == "CALC_NUMBER_NOT_FOUND"


def test_http_units(client, project):
    r = client.get(f"/projects/{project}/units", headers=AUTH)
    assert r.status_code == 200
    assert r.json() == {"built_in": list(BUILT_IN), "defined": []}
    src = source_id(records(client, project), "quote")
    body = {"symbol": "bag", "equals": "50 kg", "source_id": src, "dated": DATED}
    r = client.post(f"/projects/{project}/units", json=body, headers=AUTH)
    assert r.status_code == 201
    number = r.json()["number"]
    assert r.json() == {"symbol": "bag", "equals": "50 kg", "number": number}
    defined = client.get(f"/projects/{project}/units", headers=AUTH).json()["defined"]
    assert defined == [
        {
            "symbol": "bag",
            "equals": "50 kg",
            "number": number,
            "source": {"id": src, "title": SOURCES["quote"]},
            "dated": DATED,
        }
    ]
    r = client.post(f"/projects/{project}/units", json=body | {"symbol": "m"}, headers=AUTH)
    assert r.status_code == 422 and r.json()["key"] == "CALC_UNIT_BUILT_IN"


def test_http_stale_and_recalculate(client, project):
    client.post(f"/projects/{project}/calc", json=AMOUNTS, headers=AUTH)
    stale = f"/projects/{project}/calc/stale"
    assert client.get(stale, headers=AUTH).json() == {"stale": [], "count": 0}
    rec = records(client, project)
    correct_number(
        rec,
        number_of(rec, "03/02", "rate"),
        value="40000",
        reason="عرض جديد - عينة",
        source_id=source_id(rec, "quote"),
        dated="2026-11-03",
        actor="engineer",
    )
    listed = client.get(stale, headers=AUTH).json()
    assert listed["count"] == 1
    r = client.post(
        f"/projects/{project}/calc/recalculate",
        json={"only": [listed["stale"][0]["calculation"]]},
        headers=AUTH,
    )
    assert r.status_code == 200 and r.json()["changes"][0]["now"] == "4800000.00"
    assert client.get(stale, headers=AUTH).json()["count"] == 0
    r = client.post(f"/projects/{project}/calc/recalculate", headers=AUTH)
    assert r.status_code == 200 and r.json()["count"] == 0
    assert numbers(rec, rec_item(rec, "03/02"))  # the old values are kept


def rec_item(rec, code):
    with rec.read() as c:
        return c.execute("SELECT id FROM items WHERE code = ?", (code,)).fetchone()[0]


ROUTES = [
    ("post", "/calc"),
    ("get", "/units"),
    ("post", "/units"),
    ("get", f"/numbers/{'0' * 32}/explain"),
    ("get", "/calc/stale"),
    ("post", "/calc/recalculate"),
]


@pytest.mark.parametrize("method, path", ROUTES)
def test_routes_need_the_secret(client, project, method, path):
    r = getattr(client, method)(f"/projects/{project}{path}")
    assert r.status_code == 401


@pytest.mark.parametrize("method, path", ROUTES)
def test_closed_project_answers_in_plain_words(client, project, method, path):
    client.post(f"/projects/{project}/close", headers=AUTH)
    body = {"formula": "1"} if path == "/calc" else {}
    r = getattr(client, method)(
        f"/projects/{project}{path}", headers=AUTH, **json_for(method, body)
    )
    assert r.status_code == 409 and r.json()["error"] == copy.PROJECT_NOT_OPEN


def json_for(method, body):
    return {"json": body} if method == "post" else {}
