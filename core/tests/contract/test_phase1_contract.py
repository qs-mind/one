"""The Phase 1 contract between the core and the new screens (job J3).

Every route of the contract is declared on the real app with its models, behind the launch secret
like any other route, and answers 501 until its job builds it; no route of the contract takes a
request an older route answers; the file the screens' types are generated from is what the core
declares; and the models keep the contract's rules.

A job that builds a route changes nothing here: 501 is asked only of the routes that
`qsone.phase1_stubs` still serves. Synthetic «عينة» data only.
"""

import json
import re
import typing
from collections import Counter
from functools import cache
from pathlib import Path
from typing import NamedTuple

import pytest
from fastapi import APIRouter
from fastapi.routing import iter_route_contexts
from fastapi.testclient import TestClient
from pydantic import BaseModel, ValidationError
from starlette.routing import compile_path

from qsone import copy, phase1_openapi, phase1_stubs
from qsone import phase1_contract as c
from qsone.app import create_app
from qsone.engine import types as engine_types
from qsone.journey import engineer as old_card
from qsone.journey import setup_state
from tests.conftest import AUTH, SECRET

OPENAPI_FILE = Path(__file__).parents[3] / "ui" / "src" / "api" / "openapi.json"
SAMPLES = json.loads(OPENAPI_FILE.with_name("samples.json").read_text(encoding="utf-8"))
# The model of each sample the fake core serves, by the first word of its key
# ("home", "home:empty", "plan:<project id>").
SHAPES = {
    "profile": c.Profile,
    "lessons": c.Lessons,
    "home": c.Home,
    "tender": c.TenderView,
    "plan": c.PlanView,
    "findings": c.Findings,
    "members": c.Members,
    "team_members": c.TeamMembers,
    "room": c.RoomPage,
    "setup": c.SetupState,
    "settings": c.Settings,
    "ai_link": c.AiLink,
}
ID = "5a" + "0" * 30  # fits the id rule and names nothing


class Row(NamedTuple):
    """One row of the contract's table, and a request that reaches it."""

    method: str
    path: str  # as declared
    call: str  # the same path with sample values
    body: dict | None
    takes: type[BaseModel] | None  # the body's model
    status: int  # when it is done as asked
    gives: object  # the answer's model


ROWS = [
    Row("GET", "/engineer/profile", "/engineer/profile", None, None, 200, c.Profile),
    Row(
        "PUT",
        "/engineer/profile",
        "/engineer/profile",
        {  # a half-filled profile is a body that fits
            "first_name": "",
            "last_name": "",
            "position": "",
            "company": "",
            "org_type": None,
            "country": None,
            "currency": None,
        },
        c.ProfileIn,
        200,
        c.Profile,
    ),
    Row("GET", "/engineer/lessons", "/engineer/lessons", None, None, 200, c.Lessons),
    Row(
        "PATCH",
        "/engineer/lessons/{lesson_id}",
        f"/engineer/lessons/{ID}",
        {"text": "درس - عينة"},
        c.LessonIn,
        200,
        c.Lesson,
    ),
    Row(
        "DELETE",
        "/engineer/lessons/{lesson_id}",
        f"/engineer/lessons/{ID}",
        None,
        None,
        200,
        c.Undoable,
    ),
    Row("GET", "/home", "/home", None, None, 200, c.Home),
    Row(
        "GET",
        "/projects/{project_id}/tender",
        f"/projects/{ID}/tender",
        None,
        None,
        200,
        c.TenderView,
    ),
    Row("GET", "/projects/{project_id}/plan", f"/projects/{ID}/plan", None, None, 200, c.PlanView),
    Row(
        "POST",
        "/projects/{project_id}/plan/request",
        f"/projects/{ID}/plan/request",
        None,
        None,
        202,
        c.BriefStarted,
    ),
    Row(
        "POST",
        "/projects/{project_id}/plan/approve",
        f"/projects/{ID}/plan/approve",
        {"version": 1},
        c.PlanApproveIn,
        200,
        c.PlanView,
    ),
    Row(
        "POST",
        "/projects/{project_id}/plan/stages/{stage_id}/approve",
        f"/projects/{ID}/plan/stages/{ID}/approve",
        {"version": 1},
        c.StageApproveIn,
        200,
        c.PlanView,
    ),
    Row(
        "POST",
        "/projects/{project_id}/plan/change",
        f"/projects/{ID}/plan/change",
        {"change_id": ID, "accept": True},
        c.PlanChangeIn,
        200,
        c.PlanView,
    ),
    Row(
        "GET",
        "/projects/{project_id}/findings",
        f"/projects/{ID}/findings",
        None,
        None,
        200,
        c.Findings,
    ),
    Row(
        "POST",
        "/projects/{project_id}/findings/{finding_id}/decide",
        f"/projects/{ID}/findings/{ID}/decide",
        {"choice": 0},
        c.DecideIn,
        200,
        c.Finding,
    ),
    Row(
        "GET",
        "/projects/{project_id}/members",
        f"/projects/{ID}/members",
        None,
        None,
        200,
        c.TeamMembers,
    ),
    Row("GET", "/team/members", "/team/members", None, None, 200, c.Members),
    Row(
        "GET",
        "/projects/{project_id}/room",
        f"/projects/{ID}/room?limit=2",
        None,
        None,
        200,
        c.RoomPage,
    ),
    Row(
        "POST",
        "/projects/{project_id}/room",
        f"/projects/{ID}/room",
        {"text": "رسالة - عينة"},
        c.RoomMessageIn,
        201,
        c.RoomMessage,
    ),
    Row("GET", "/setup/parts", "/setup/parts", None, None, 200, c.SetupState),
    Row("POST", "/setup/parts/retry", "/setup/parts/retry", None, None, 200, c.SetupState),
    Row("GET", "/settings", "/settings", None, None, 200, c.Settings),
    Row(
        "PATCH",
        "/settings/{key}",
        "/settings/caps.month_usd",  # a key holds one dot
        {"value": "50"},
        c.SettingIn,
        200,
        c.Setting,
    ),
    Row(
        "POST",
        "/settings/ai/connect",
        "/settings/ai/connect",
        {"key": "sample-key"},
        c.AiConnectIn,
        201,
        c.AiLink,
    ),
    Row(
        "DELETE",
        "/settings/ai/links/{link_id}",
        "/settings/ai/links/standard:abc",  # a link's id may hold a colon
        None,
        None,
        200,
        c.Undoable,
    ),
    Row("POST", "/briefs/{brief_id}/retry", f"/briefs/{ID}/retry", None, None, 202, c.BriefStarted),
]


@pytest.fixture
def app(data_dir):
    return create_app(SECRET, data_dir=data_dir)


@pytest.fixture
def client(app):
    """Requests to the real app with nothing started: these routes need no lifespan."""
    return TestClient(app)


def table(app) -> list:
    """Every route of the app, in the order a request is matched against them."""
    return list(iter_route_contexts(app.routes))


@cache
def fits(declared: str) -> re.Pattern:
    return compile_path(declared)[0]


def answering(routes: list, method: str, path: str):
    """The route that answers a request: the first whose path fits and that takes the method."""
    path = path.partition("?")[0]
    for route in routes:
        if fits(route.path).match(path) and method in (route.methods or {method}):
            return route
    return None


def is_stub(route) -> bool:
    return route.endpoint.__module__ == phase1_stubs.__name__


def is_model(value: object) -> bool:
    return (
        isinstance(value, type) and issubclass(value, BaseModel) and value.__module__ == c.__name__
    )


MODELS = [model for model in vars(c).values() if is_model(model)]


def mentions(annotation: object, kind: type) -> bool:
    return annotation is kind or any(mentions(arg, kind) for arg in typing.get_args(annotation))


def allowed(annotation: object) -> tuple:
    """Every value the Literals inside an annotation allow, in order."""
    if typing.get_origin(annotation) is typing.Literal:
        return typing.get_args(annotation)
    return tuple(value for arg in typing.get_args(annotation) for value in allowed(arg))


def allowed_in(model: type[BaseModel], field: str) -> tuple:
    return allowed(model.model_fields[field].annotation)


def tags(union: object, key: str) -> tuple:
    """The value of `key` that tells each member of a union apart."""
    members = typing.get_args(typing.get_args(union)[0])
    return tuple(value for member in members for value in allowed_in(member, key))


# The routes -------------------------------------------------------------------------------------


def test_the_table_here_is_the_contracts():
    assert [(row.method, row.path) for row in ROWS] == list(phase1_openapi.ROUTES)
    assert len(ROWS) == 25


@pytest.mark.parametrize("row", ROWS, ids=lambda row: f"{row.method} {row.path}")
def test_a_contract_route_is_declared_and_refuses_until_it_is_built(app, client, row):
    route = answering(table(app), row.method, row.call)
    assert route is not None and route.path == row.path  # no older route takes the request
    declared = route.original_route
    # FastAPI keeps no status for a route that names none: it answers 200.
    assert (declared.status_code or 200, declared.response_model) == (row.status, row.gives)

    # Behind the launch secret, like any other route.
    health = client.get("/health")
    for headers in ({}, {"Authorization": "Bearer wrong"}):
        refused = client.request(row.method, row.call, json=row.body, headers=headers)
        assert (refused.status_code, refused.json()) == (health.status_code, health.json())
        assert (refused.status_code, refused.json()) == (401, {"detail": "Unauthorized"})
        # Never kept on disk by the webview, whoever answers under this path.
        assert refused.headers["cache-control"] == "no-store"

    if is_stub(route):  # a built route has its job's own tests
        answer = client.request(row.method, row.call, json=row.body, headers=AUTH)
        assert (answer.status_code, answer.json()) == (501, {"error": copy.NOT_BUILT})
        assert answer.headers["cache-control"] == "no-store"
        c.Refusal.model_validate_json(answer.text, strict=True)


@pytest.mark.parametrize(
    "row", [row for row in ROWS if row.path == "/engineer/profile"], ids=lambda row: row.method
)
def test_the_profile_routes_are_built_and_answer_their_model(app, client, row):
    """Rows 1-2 (C1): served by their own router, each answers its model in strict mode."""
    assert not is_stub(answering(table(app), row.method, row.call))
    answer = client.request(row.method, row.call, json=row.body, headers=AUTH)
    assert answer.status_code == row.status and answer.headers["cache-control"] == "no-store"
    assert row.gives.model_validate_json(answer.text, strict=True).complete is False


def test_the_not_built_text_is_a_pair_with_no_fix_to_offer():
    assert set(copy.NOT_BUILT) == {"en", "ar"} and all(copy.NOT_BUILT.values())
    assert copy.fix_of(copy.NOT_BUILT) is None


def test_a_wrongly_built_request_is_refused_before_the_stub_answers(client):
    """The stubs already check what they are sent, so a screen finds a wrong request today."""
    number = client.patch("/settings/caps.month_usd", json={"value": 50}, headers=AUTH)
    third = client.post(f"/projects/{ID}/findings/{ID}/decide", json={"choice": 2}, headers=AUTH)
    word = client.post(
        f"/projects/{ID}/plan/change", json={"change_id": ID, "accept": "yes"}, headers=AUTH
    )
    extra = client.post(f"/projects/{ID}/room", json={"text": "عينة", "to": "x"}, headers=AUTH)
    zero = client.get(f"/projects/{ID}/room?limit=0", headers=AUTH)
    for refused in (number, third, word, extra, zero):
        assert refused.status_code == 422
        c.BodyProblem.model_validate_json(refused.text, strict=True)


# Nothing older is shadowed ----------------------------------------------------------------------


def test_no_two_routes_share_a_method_and_path(app):
    """For the same method and path the first route mounted wins, so a second one is dead.
    Two paths that differ only in a parameter's name are the same path."""
    shapes = Counter(
        (method, re.sub(r"\{[^}]+\}", "{}", route.path))
        for route in table(app)
        for method in route.methods or ()
    )
    assert [shape for shape, count in shapes.items() if count > 1] == []


def test_every_older_route_is_still_answered_by_its_own_handler(app):
    """What answered a request before the contract's routes were mounted answers it now."""
    routes = table(app)
    older = [route for route in routes if not is_stub(route)]
    assert len(older) > 100 and len(routes) - len(older) <= len(ROWS)
    for route in older:
        path = re.sub(r"\{[^}]+\}", "7", route.path)
        for method in route.methods or {"GET"}:
            before = answering(older, method, path)
            assert before is not None, (method, route.path)
            assert answering(routes, method, path) is before, (method, route.path)
    # The stub router is the last thing mounted: nothing after it, nothing older behind it.
    assert [is_stub(route) for route in routes] == sorted(is_stub(route) for route in routes)


def test_the_older_routes_beside_the_new_paths_answer_as_before(client):
    """GET /setup, GET /projects/{id}/team and POST /briefs/{id}/continue keep their meaning:
    the contract's routes took other paths (/setup/parts, .../members, .../retry)."""
    setup = client.get("/setup", headers=AUTH)
    assert setup.status_code == 200
    assert setup.json() == {"done": False, "steps": dict.fromkeys(setup_state.STEPS)}
    c.SetupSteps.model_validate_json(setup.text, strict=True)  # typed for the new gate

    team = client.get(f"/projects/{ID}/team", headers=AUTH)
    assert (team.status_code, team.json()) == (200, {"desks": [], "agents": []})

    go_on = client.post(f"/briefs/{ID}/continue", headers=AUTH)
    assert (go_on.status_code, go_on.json()) == (404, {"error": copy.BRIEF_NOT_FOUND})

    zoom = client.get("/settings/zoom", headers=AUTH)  # an older /settings/<name>, no dot
    assert zoom.status_code == 200 and set(zoom.json()) == {"zoom"}


# The file the screens' types are generated from -------------------------------------------------


def test_the_screens_openapi_file_is_a_fresh_dump():
    """To write it again: python -m qsone.phase1_openapi > ui/src/api/openapi.json"""
    assert OPENAPI_FILE.read_text(encoding="utf-8") == phase1_openapi.dump()


def test_the_file_stays_the_same_when_a_route_is_built(monkeypatch):
    """A job that builds a route gives its handler a name and a docstring of its own. Neither is
    in the document, so the file does not change and parallel jobs never rewrite it."""

    class Built(APIRouter):
        def add_api_route(self, path, endpoint, **more):
            endpoint.__name__ = f"built_{endpoint.__name__}"
            endpoint.__doc__ = "What this handler does, in its job's own words."
            super().add_api_route(path, endpoint, **more)

    monkeypatch.setattr(phase1_stubs, "APIRouter", Built)
    assert phase1_openapi.dump() == OPENAPI_FILE.read_text(encoding="utf-8")


def test_the_document_holds_the_contract_and_nothing_else():
    doc = phase1_openapi.document()
    operations = {
        (method.upper(), path): operation
        for path, item in doc["paths"].items()
        for method, operation in item.items()
    }
    assert set(operations) == {(row.method, row.path) for row in ROWS}
    schemas = doc["components"]["schemas"]
    ours = {model.__name__ for model in MODELS}
    assert set(schemas) - ours == {"HTTPValidationError", "ValidationError"}  # FastAPI's own 422
    assert ours - set(schemas) == {"SettingBase"}  # only ever sent as one of its four controls
    assert {model.__name__ for model in c.SCHEMA_ONLY} <= set(schemas)

    def ref(model) -> dict:
        return {"$ref": f"#/components/schemas/{model.__name__}"}

    for row in ROWS:
        operation = operations[row.method, row.path]
        body = operation.get("requestBody")
        if row.takes is None:
            assert body is None
        else:
            assert body["required"] is True
            assert body["content"]["application/json"]["schema"] == ref(row.takes)
        done = operation["responses"][str(row.status)]["content"]["application/json"]["schema"]
        if row.gives is c.Setting:  # one of the four, told apart by `control`
            assert done["discriminator"]["propertyName"] == "control"
            assert done["oneOf"] == [ref(m) for m in typing.get_args(typing.get_args(c.Setting)[0])]
        else:
            assert done == ref(row.gives)
        # What belongs to a stub or a handler is not in the contract.
        assert "501" not in operation["responses"] and "operationId" not in operation


# The samples the screens are built against ------------------------------------------------------


def test_every_sample_has_a_model_and_every_model_a_sample():
    assert {key.partition(":")[0] for key in SAMPLES} == set(SHAPES)
    assert len(SAMPLES) == 28


@pytest.mark.parametrize("key", sorted(SAMPLES))
def test_a_sample_is_an_answer_the_core_could_give(key):
    """ui/src/api/samples.json is what the fake core serves, so the screens are built on it.
    Each sample fits its model in strict mode, and it is exactly what that model sends: no key
    the model does not have, none left out."""
    model = SHAPES[key.partition(":")[0]]
    read = model.model_validate_json(json.dumps(SAMPLES[key]), strict=True)
    assert read.model_dump(mode="json") == SAMPLES[key]


# The rules the models keep ----------------------------------------------------------------------


def test_no_number_is_a_float():
    """Money and quantities are exact decimal text and counts are integers, so no field is a
    float. The one place that holds one is a source's place in a file: `box` is in PDF points."""
    floats = {
        (model.__name__, name)
        for model in MODELS
        for name, field in model.model_fields.items()
        if mentions(field.annotation, float)
    }
    assert floats == {("Source", "locator")}
    assert {c.Source, c.TenderPlan, c.MoneySetting, c.MemberRecord} <= set(MODELS)


def test_money_as_a_json_number_is_refused():
    assert c.SettingIn.model_validate({"value": "0.50"}).value == "0.50"
    assert c.SettingIn.model_validate({"value": True}).value is True
    for number in (50, 0.5):
        with pytest.raises(ValidationError):
            c.SettingIn.model_validate({"value": number})
    record = {"tenders": 1, "checks_passed": 0, "checks_total": 0}
    assert c.MemberRecord.model_validate(record | {"cost_usd": "0.50"}).cost_usd == "0.50"
    with pytest.raises(ValidationError):
        c.MemberRecord.model_validate(record | {"cost_usd": 0.5})


@pytest.mark.parametrize(
    "pair",
    [
        {"en": "Sample"},
        {"ar": "عينة"},
        {"en": "", "ar": "عينة"},
        {"en": "Sample", "ar": ""},
        {"en": "Sample", "ar": None},
        "Sample",
    ],
)
def test_a_text_needs_both_languages(pair):
    assert c.Text.model_validate({"en": "Sample", "ar": "عينة"}).ar == "عينة"
    with pytest.raises(ValidationError):
        c.Text.model_validate(pair)
    with pytest.raises(ValidationError):  # and so does a refusal: `error` is never a string
        c.Refusal.model_validate({"error": pair})


def test_the_enums_are_the_designs():
    cards = (
        "outside",
        "online",
        "cap",
        "price",
        "budget",
        "fallback",
        "desk",
        "disagreement",
        "question",
        "keep",
        "rows",
        "cost",
        "connector",
        "keep_member",
        "setting",
    )
    brief_states = (
        "queued",
        "running",
        "waiting_engineer",
        "waiting_connection",
        "paused_cap",
        "stopped",
        "done",
        "failed",
    )
    found = {
        "Fix": allowed(c.Fix),
        "BriefState": allowed(c.BriefState),
        "CardKind": allowed(c.CardKind),
        "OrgType": allowed(c.OrgType),
        "Country": allowed(c.Country),
        "StageStatus": allowed(c.StageStatus),
        "TenderState": allowed(c.TenderState),
        "WaitingKind": allowed(c.WaitingKind),
        "SettingSection": allowed(c.SettingSection),
        "StepState": allowed(c.StepState),
        "Member.role": allowed_in(c.Member, "role"),
        "Member.kind": allowed_in(c.Member, "kind"),
        "TeamMember.state": allowed_in(c.TeamMember, "state"),
        "StageOutput.kind": allowed_in(c.StageOutput, "kind"),
        "TenderPlan.status": allowed_in(c.TenderPlan, "status"),
        "Finding.status": allowed_in(c.Finding, "status"),
        "Finding.chosen": allowed_in(c.Finding, "chosen"),
        "DecideIn.choice": allowed_in(c.DecideIn, "choice"),
        "SetupPart.state": allowed_in(c.SetupPart, "state"),
        "CardQuestion.kind": allowed_in(c.CardQuestion, "kind"),
        "StoredMessageMark.by": allowed_in(c.StoredMessageMark, "by"),
        "BriefEvent.state": allowed_in(c.BriefEvent, "state"),
        "Setting.control": tags(c.Setting, "control"),
        "TenderActivity.type": tags(c.TenderActivity, "type"),
        "GeneralActivity.type": tags(c.GeneralActivity, "type"),
    }
    assert found == {
        "Fix": ("ai", "search", "consent", "retry", "backup", "caps"),
        "BriefState": brief_states,
        "CardKind": cards,
        "OrgType": ("contractor", "consultant", "owner", "procurement"),
        "Country": ("EG", "SA", "AE", "other"),
        "StageStatus": ("pending", "now", "waiting_engineer", "approved"),
        "TenderState": (
            "archived",
            "waiting",
            "paused",
            "offline",
            "reading",
            "working",
            "finished",
            "failed",
            "stopped",
            "no_plan",
        ),
        "WaitingKind": ("plan", "stage", "plan_change", "decision", "unfinished", *cards),
        "SettingSection": ("ai", "caps", "privacy", "look"),
        "StepState": ("done", "skipped"),
        "Member.role": ("lead", "checker", "specialist"),
        "Member.kind": ("fixed", "temporary", "permanent"),
        "TeamMember.state": ("working", "waiting", "idle", "failed"),
        "StageOutput.kind": ("deliverable", "file", "map", "summary"),
        "TenderPlan.status": ("proposed", "approved"),
        "Finding.status": ("open", "queued", "raised", "settled"),
        "Finding.chosen": (0, 1),
        "DecideIn.choice": (0, 1),
        "SetupPart.state": (
            "present",
            "queued",
            "downloading",
            "waiting_network",
            "failed",
            "unavailable",
        ),
        "CardQuestion.kind": ("text", "number", "money", "date"),
        "StoredMessageMark.by": ("one",),
        "BriefEvent.state": brief_states,
        "Setting.control": ("toggle", "choice", "money", "number"),
        "TenderActivity.type": ("plan", "finding", "room", "member", "tender", "brief"),
        "GeneralActivity.type": ("home", "setting", "setup", "lessons"),
    }


def test_the_enums_the_core_already_has_are_the_cores():
    """Where the contract repeats a list the core keeps, the two say the same."""
    assert allowed(c.BriefState) == allowed(engine_types.BriefState)
    assert allowed(c.CardKind) == (*allowed(engine_types.CardKind), "keep_member", "setting")
    assert set(allowed(c.Fix)) == set(copy.FIXES) | {"caps"}  # "caps" comes with Settings
    # The old introduction card fills a new profile: its role becomes `org_type`.
    assert allowed(c.OrgType) == allowed_in(old_card.Card, "role")
    assert allowed(c.Country) == allowed_in(old_card.Card, "country")
    assert tuple(c.SetupStepStates.model_fields) == setup_state.STEPS


def test_no_plan_yet_is_a_null_inside_a_200():
    """A tender with no plan is not an error: GET /projects/{project_id}/plan answers 200 with
    `{"plan": null}`, never a bare null and never a 404. The route is a stub until its job
    lands, so this is asked of the model and of what the route declares."""
    none = c.PlanView.model_validate_json('{"plan": null}', strict=True)
    assert none.plan is None and none.model_dump(mode="json") == {"plan": None}
    with pytest.raises(ValidationError):
        c.PlanView.model_validate({})  # the key is always there
    with pytest.raises(ValidationError):
        c.PlanView.model_validate(None)
    assert c.PlanEvent.model_validate({"type": "plan", "plan": None}).plan is None

    doc = phase1_openapi.document()
    declared = doc["paths"]["/projects/{project_id}/plan"]["get"]["responses"]
    assert declared["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/PlanView"
    }
    plan = doc["components"]["schemas"]["PlanView"]
    assert plan["required"] == ["plan"]
    assert plan["properties"]["plan"]["anyOf"] == [
        {"$ref": "#/components/schemas/TenderPlan"},
        {"type": "null"},
    ]
