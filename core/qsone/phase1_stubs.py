"""Every Phase 1 route that is not built yet, declared with its models and answering 501.

The screens are built against these declarations (`qsone.phase1_contract`), so each route is here
from the first day with its path, its body and its answers, and refuses with `copy.NOT_BUILT`
until its job lands. The router is mounted last in `create_app`: it can never take a request an
older route answers.

To build a route:
1. Delete its function here, with its decorator. Nothing else in this file changes; when the last
   one goes, delete the file and its line in `create_app`.
2. Declare it in your own router with the same path, `status_code`, `response_model` and
   `responses` (the same refusals, without the 501), and refuse through
   `phase1_contract.refusal`. The handler's name and docstring are yours: neither is in the
   contract.
3. Run core/tests/contract/test_phase1_contract.py. It asks 501 only of the routes still served
   from here, and it fails when the route no longer says what ui/src/api/openapi.json says.
"""

from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from qsone import copy
from qsone import phase1_contract as c

_REFUSAL = c.Refusal
_BAD = c.Refusal | c.BodyProblem  # 422: the engineer's value, or a body the screen built wrongly


def _refusals(*codes: int) -> dict:
    """The refusals a route declares: 501 while it is a stub, and each of `codes`."""
    found: dict = {501: {"model": _REFUSAL}}
    for code in codes:
        found[code] = {"model": _BAD if code == 422 else _REFUSAL}
    return found


def _stub() -> JSONResponse:
    return c.refusal(copy.NOT_BUILT, 501)


def router() -> APIRouter:
    r = APIRouter()

    # The team room (C6).
    @r.get(
        "/projects/{project_id}/room", response_model=c.RoomPage, responses=_refusals(404, 409, 422)
    )
    def room(
        project_id: str,
        cursor: Annotated[str | None, Query(max_length=200)] = None,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
    ):
        return _stub()

    @r.post(
        "/projects/{project_id}/room",
        status_code=201,
        response_model=c.RoomMessage,
        responses=_refusals(404, 409, 422, 423),
    )
    def say_in_room(project_id: str, body: c.RoomMessageIn):
        return _stub()

    return r
