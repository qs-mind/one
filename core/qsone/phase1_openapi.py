"""The Phase 1 contract as one OpenAPI document: the screens' types are generated from it.

    python -m qsone.phase1_openapi > ui/src/api/openapi.json

The document holds the contract's routes and their models, and nothing else of the core. It is
read from the app's own route table, so it says what the core really declares. The app is built
for that and never started: no lifespan runs, and nothing of the engineer's is read or written.

What belongs to a handler and not to the contract is left out: its name and docstring
(`operationId`, `summary`, `description`, and the `title` FastAPI makes from the name for an
answer that is one of several shapes). So the output is the same whatever a handler is called,
and changes only when the contract does. core/tests/contract/test_phase1_contract.py keeps the
file in the repository equal to it.
"""

import json
import sys
import tempfile
from pathlib import Path

from fastapi.openapi.utils import get_openapi
from fastapi.routing import iter_route_contexts
from pydantic.json_schema import models_json_schema

from qsone import phase1_contract
from qsone.app import create_app

# The contract's routes, in the order of its table.
ROUTES = (
    ("GET", "/engineer/profile"),
    ("PUT", "/engineer/profile"),
    ("GET", "/engineer/lessons"),
    ("PATCH", "/engineer/lessons/{lesson_id}"),
    ("DELETE", "/engineer/lessons/{lesson_id}"),
    ("GET", "/home"),
    ("GET", "/projects/{project_id}/tender"),
    ("GET", "/projects/{project_id}/plan"),
    ("POST", "/projects/{project_id}/plan/request"),
    ("POST", "/projects/{project_id}/plan/approve"),
    ("POST", "/projects/{project_id}/plan/stages/{stage_id}/approve"),
    ("POST", "/projects/{project_id}/plan/change"),
    ("GET", "/projects/{project_id}/findings"),
    ("POST", "/projects/{project_id}/findings/{finding_id}/decide"),
    ("GET", "/projects/{project_id}/members"),
    ("GET", "/team/members"),
    ("GET", "/projects/{project_id}/room"),
    ("POST", "/projects/{project_id}/room"),
    ("GET", "/setup/parts"),
    ("POST", "/setup/parts/retry"),
    ("GET", "/settings"),
    ("PATCH", "/settings/{key}"),
    ("POST", "/settings/ai/connect"),
    ("DELETE", "/settings/ai/links/{link_id}"),
    ("POST", "/briefs/{brief_id}/retry"),
)


def document() -> dict:
    """The OpenAPI document of the contract's routes, with the shapes no route returns."""
    with tempfile.TemporaryDirectory() as folder:
        app = create_app("contract", data_dir=Path(folder))
        declared = {}
        for route in iter_route_contexts(app.routes):
            for method in route.methods or ():
                declared.setdefault((method, route.path), route)  # the first one answers
        doc = get_openapi(
            title="QS Mind ONE: the Phase 1 contract",
            version="1",
            routes=[declared[route] for route in ROUTES],
        )
    for operations in doc["paths"].values():
        for operation in operations.values():
            for key in ("operationId", "summary", "description"):
                operation.pop(key, None)
            for response in operation["responses"].values():
                for content in response.get("content", {}).values():
                    content["schema"].pop("title", None)  # "Response 422 <handler's name> ..."
    _, more = models_json_schema(
        [(model, "serialization") for model in phase1_contract.SCHEMA_ONLY],
        ref_template="#/components/schemas/{model}",
    )
    for name, schema in more.get("$defs", {}).items():
        doc["components"]["schemas"].setdefault(name, schema)  # a route's own schema is kept
    return doc


def dump() -> str:
    """The document as text: the same bytes for the same contract."""
    return json.dumps(document(), indent=2, sort_keys=True) + "\n"


if __name__ == "__main__":
    sys.stdout.write(dump())
