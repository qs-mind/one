"""Routes 19-20 of the Phase 1 contract: the setup strip's state, and Retry."""

from fastapi import APIRouter

from qsone import phase1_contract as c
from qsone.setup.runner import Setup


def router(setup: Setup) -> APIRouter:
    r = APIRouter()

    @r.get("/setup/parts", response_model=c.SetupState)
    def setup_parts() -> c.SetupState:
        return setup.state()

    @r.post("/setup/parts/retry", response_model=c.SetupState)
    def retry_setup() -> c.SetupState:
        """Queues every failed part again; nothing else changes. Takes no body."""
        return setup.retry()

    return r
