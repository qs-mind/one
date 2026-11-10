"""The plan driver's test kit: a sample tender with a proposed plan, and the fixtures that make
one on a started engine with a scripted Lead. Synthetic «عينة» data only."""

import asyncio

import pytest

from qsone import settings
from qsone.engine.plan import claims, store
from qsone.engine.plan import driver as plan_driver
from qsone.engine.store import Store
from tests.test_engine_runner import (  # noqa: F401 - fixtures
    links,
    make_engine,
    project,
    registry,
    started,
    until,
)
from tests.test_tender_plan import draft, due_in, pair, stage

MAP = [{"kind": "map", "title": pair("Project map")}]  # an output that needs no sign-off of its own


class Tender:
    """A sample tender with a proposed plan of `n` stages, and the driver on an engine."""

    def __init__(
        self, engine, projects, project_id, *, n=3, supplies=None, propose=True, driver=None
    ):
        self.engine, self.project = engine, project_id
        self.rec = projects.get(project_id)
        self.store = Store(self.rec, project_id=project_id)
        if propose:
            due_in(self.rec)
            stages = [
                stage(self.rec, i, title=pair(f"Stage {i + 1}"), outputs=MAP) for i in range(n)
            ]
            if supplies is not None:
                stages[0]["engineer_supplies"] = supplies
            store.propose(self.rec, draft(self.rec, stages=stages, team=[]))
        self.driver = driver
        if driver is None:
            self.driver = plan_driver.PlanDriver(engine)
            self.driver.start()

    def approve_plan(self):
        store.approve(self.rec)
        plan_driver.on_plan_approved(self.project)

    def stage(self, n):
        return store.current(self.rec).stages[n - 1]

    def claim(self, n):
        with self.rec.read() as conn:
            return claims.latest(conn, self.stage(n).id)

    def briefs(self):
        """How many Briefs the tender has, and how many claims each stage."""
        with self.rec.read() as conn:
            (total,) = conn.execute("SELECT count(*) FROM briefs").fetchone()
            each = [
                conn.execute(
                    "SELECT count(*) FROM tender_stage_briefs WHERE stage_id = ?", (s.id,)
                ).fetchone()[0]
                for s in store.current(self.rec).stages
            ]
        return total, each

    def sign_off(self, n):
        store.approve_stage(self.rec, self.stage(n).id)
        plan_driver.on_stage_approved(self.project, self.stage(n).id)

    async def ready(self, n):
        await until(
            lambda: (
                self.stage(n).status == "waiting_engineer"
                and (self.claim(n) or {}).get("status") == "done"
            )
        )

    async def settle(self):
        for _ in range(3):
            await self.driver.idle()
            await asyncio.sleep(0.01)

    def pending(self, n):
        return self.store.pending(self.claim(n)["brief_id"])


@pytest.fixture(autouse=True)
def english():
    settings.save("language", "en")


@pytest.fixture
async def drivers():
    made: list[plan_driver.PlanDriver] = []
    yield made
    for driver in made:
        await driver.stop()


@pytest.fixture
def tender(make_engine, registry, project, drivers):  # noqa: F811
    async def make(lead, **options) -> Tender:
        engine = await started(make_engine(links(lead=lead)))
        found = Tender(engine, registry, project, **options)
        drivers.append(found.driver)
        return found

    return make


async def blocks(messages, info):
    await asyncio.Event().wait()
