"""Signing off a stage's outputs, inside the stage's own write (contract section 7, Q1).

Every Deliverable output not signed off yet is signed off by the existing close-out rule, and
the tender summary is marked approved as `PUT .../facts` with `approve: true` does; a `map`
output needs nothing. All of it joins the caller's write, so the stage is signed off whole or
not at all."""

from qsone import copy
from qsone.deliverables import review
from qsone.deliverables import store as deliverables
from qsone.journey import understand
from qsone.records.project import Records, RecordsError


def _not_ready(output: dict, reason: dict) -> RecordsError:
    text = copy.fill(copy.STAGE_OUTPUT_NOT_READY, output=output["title"], reason=reason)
    return RecordsError(text, field="outputs")


def ready(project: Records, outputs: list[dict]) -> list[str]:
    """The Deliverables to sign off, in order. Raises STAGE_OUTPUT_NOT_READY for the first
    output that has not been made, or that the close-out rule refuses, with its reason."""
    found = []
    for output in outputs:
        if output["kind"] not in ("deliverable", "file"):
            continue
        if output["id"] is None:
            raise _not_ready(output, copy.STAGE_OUTPUT_MISSING)
        if output["kind"] == "file":
            continue
        if deliverables.status(project, output["id"])["status"] == "signed_off":
            continue
        reasons = review.closeout(project, output["id"])["reasons"]
        if reasons:
            raise _not_ready(output, reasons[0])
        found.append(output["id"])
    return found


def sign(project: Records, conn, outputs: list[dict], *, actor: str) -> None:
    """Inside the caller's write: signs off what `ready` gives, then the tender summary."""
    for deliverable_id in ready(project, outputs):
        review.sign_off(project, deliverable_id, actor=actor)
    if any(output["kind"] == "summary" for output in outputs):
        understand._approve(conn, project, True, actor)
