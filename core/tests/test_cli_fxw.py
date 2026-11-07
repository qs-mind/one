"""Mapping waits include enrichment after file classification has finished."""

import pytest

from qsone.cli.commands import Commands
from qsone.cli.walk import Walk


@pytest.mark.parametrize("outcome", ["done", "failed"])
@pytest.mark.parametrize("walk_step", [False, True])
def test_slow_facts_wait(monkeypatch, outcome, walk_step):
    monkeypatch.setattr("qsone.cli.commands.time.sleep", lambda _: None)
    monkeypatch.setattr("qsone.cli.walk.time.sleep", lambda _: None)

    class Core:
        polls = 0

        def get(self, route, **kwargs):
            if route.endswith("/messages"):
                return {"messages": []}
            if route.endswith("/facts"):
                assert self.polls >= (3 if outcome == "failed" else 4)
                return {"facts": [{"state": "found"}] if outcome == "done" else []}
            if route.endswith("/links"):
                return {"links": []}
            self.polls += 1
            # First observe the gap before registration, then a slow facts pass,
            # then finished facts while links still need to be registered.
            passes = {}
            if self.polls >= 2:
                passes["facts"] = {"state": "running" if self.polls == 2 else outcome}
            if self.polls >= 4:
                passes["links"] = {"state": "done"}
            return {
                "files": [
                    {
                        "file_id": "f",
                        "ai_title": {"en": "Sample", "ar": "عينة"},
                        "local_state": "done",
                        "ai_state": "done",
                        "ai_stage": "facts"
                        if self.polls < 3 or outcome == "failed"
                        else "links"
                        if self.polls == 3
                        else "complete",
                    }
                ],
                "status": {"passes": passes},
            }

    client = Core()
    commands = Commands(client, {}, None)
    if walk_step:
        walk = Walk(commands)
        walk.project = "p"
        result = walk.step({"map": {}})
        assert bool(result["map_facts"]) == (outcome == "done")
    else:
        assert commands.map("p", wait=10)["state"] == "done"
    assert client.polls >= (3 if outcome == "failed" else 4)
