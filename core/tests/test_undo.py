"""Undo instead of "are you sure?": a removal happens at once, can be taken back inside its
window, and is purged for good after it (or at the next start). Synthetic «عينة» data only."""

import json

import pytest
from fastapi.testclient import TestClient

from qsone import copy, keys, settings
from qsone.app import create_app
from qsone.undo import Trash
from tests.conftest import AUTH, SECRET


class Timer:
    def __init__(self, timers: list, delay: float, callback) -> None:
        self.timers, self.delay, self.callback = timers, delay, callback

    def cancel(self) -> None:
        if self in self.timers:
            self.timers.remove(self)


class Later:
    """Stands in for the loop's `call_later`: keeps each timer for the test to fire."""

    def __init__(self) -> None:
        self.timers: list[Timer] = []

    def __call__(self, delay, callback) -> Timer:
        timer = Timer(self.timers, delay, callback)
        self.timers.append(timer)
        return timer

    def fire(self) -> None:
        for timer in list(self.timers):
            timer.callback()
        self.timers.clear()


class Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def later():
    return Later()


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def trash(data_dir, later, clock):
    found = Trash(later=later, clock=clock)
    shelf = {"items": ["عينة"]}
    found.kind(
        "sample",
        restore=lambda entry: shelf["items"].append(entry["name"]) or True,
        purge=lambda entry: shelf.setdefault("purged", []).append(entry["name"]),
    )
    found.shelf = shelf  # what the sample kind works on
    return found


def test_undo_inside_the_window_restores(trash, later):
    trash.shelf["items"].remove("عينة")
    given = trash.put("sample", {"name": "عينة"})
    assert given["window_ms"] == 6000 and given["undo"]
    [timer] = later.timers
    assert timer.delay == pytest.approx(6 + 2)  # the window, and time for an Undo at its end
    assert trash.undo(given["undo"])
    assert trash.shelf["items"] == ["عينة"] and "purged" not in trash.shelf
    assert later.timers == []  # its purge is called off
    assert not trash.undo(given["undo"])  # once only


def test_the_window_pauses_while_the_engineer_points_at_undo(trash, later, clock):
    given = trash.put("sample", {"name": "عينة"})
    clock.now += 4  # 2 s of the window left
    assert trash.pause(given["undo"])
    assert later.timers == []  # nothing is purged while paused
    clock.now += 60
    assert trash.resume(given["undo"])
    [timer] = later.timers
    assert timer.delay == pytest.approx(2 + 2)  # the 2 s it had left, and the grace
    later.fire()
    assert trash.shelf["purged"] == ["عينة"]
    assert not trash.pause(given["undo"]) and not trash.resume(given["undo"])


def test_after_the_window_it_is_purged_and_undo_is_too_late(trash, later):
    given = trash.put("sample", {"name": "عينة"})
    later.fire()
    assert trash.shelf["purged"] == ["عينة"]
    assert not trash.undo(given["undo"])
    assert settings.load().get("trash") in (None, {})


def test_a_core_that_stopped_in_the_window_purges_at_the_next_start(trash, data_dir, later):
    given = trash.put("sample", {"name": "عينة"})
    assert given["undo"] in settings.load()["trash"]  # kept aside on disk, not only in memory
    again = Trash(later=Later())
    purged = []
    again.kind("sample", restore=lambda entry: True, purge=lambda entry: purged.append(entry))
    again.purge_all()
    assert purged == [{"name": "عينة"}] and not again.undo(given["undo"])


def test_a_purge_that_fails_is_tried_again_at_the_next_start(trash, later):
    def broken(entry):
        raise OSError("the key store is down")

    trash.kind("broken", restore=lambda entry: True, purge=broken)
    given = trash.put("broken", {"name": "عينة"})
    later.fire()
    assert given["undo"] in settings.load()["trash"]


# The two removals that use it: a Connector and a Standard Link --------------------------------


@pytest.fixture
def client(data_dir):
    with TestClient(create_app(SECRET, data_dir=data_dir), headers=AUTH) as c:
        yield c


def test_a_removed_standard_link_comes_back_whole_with_undo(client):
    added = client.post(
        "/settings/ai/standard",
        json={"name": "عينة", "base_url": "https://api.example.com/v1", "key": "sk-sample-1"},
    ).json()
    ai = settings.ai()
    settings.save_ai("roles", {"quick": {"connector": added["id"], "model": "sample-chat"}})
    settings.save_ai("prices", {f"{added['id']}/sample-chat": {"in": "1", "out": "2"}})
    removed = client.delete(f"/settings/ai/standard/{added['id']}")
    assert removed.status_code == 200 and removed.json()["window_ms"] == 6000
    assert added["id"] not in json.dumps(settings.ai().get("standard"))  # out of use at once
    assert "quick" not in settings.ai().get("roles", {})
    assert keys.get_key(added["id"]) == "sk-sample-1"  # its key waits for the window
    assert client.post(f"/undo/{removed.json()['undo']}").status_code == 204
    back = settings.ai()
    assert [e["id"] for e in back["standard"]] == [e["id"] for e in ai["standard"]]
    assert back["roles"]["quick"]["connector"] == added["id"]
    assert f"{added['id']}/sample-chat" in back["prices"]
    gone = client.post(f"/undo/{removed.json()['undo']}")
    assert gone.status_code == 404 and gone.json()["error"] == copy.UNDO_GONE
    assert client.post(f"/undo/{removed.json()['undo']}/pause").status_code == 404


def test_pause_and_resume_answer_while_the_window_runs(client):
    added = client.post(
        "/settings/ai/standard", json={"name": "عينة", "base_url": "https://api.example.com/v1"}
    ).json()
    token = client.delete(f"/settings/ai/standard/{added['id']}").json()["undo"]
    assert client.post(f"/undo/{token}/pause").status_code == 204
    assert client.post(f"/undo/{token}/resume").status_code == 204
    assert client.post(f"/undo/{token}").status_code == 204


def test_a_removed_standard_link_loses_its_key_when_the_window_ends(client):
    added = client.post(
        "/settings/ai/standard",
        json={"name": "عينة", "base_url": "https://api.example.com/v1", "key": "sk-sample-2"},
    ).json()
    removed = client.delete(f"/settings/ai/standard/{added['id']}").json()
    client.app.state.trash.purge_all()  # as when the window ends
    assert keys.get_key(added["id"]) is None
    assert client.post(f"/undo/{removed['undo']}").status_code == 404
