"""The engineer's zoom: in ONE's own settings.json, never web storage; only the 10 % steps."""

import json

import pytest
from fastapi.testclient import TestClient

from qsone.app import create_app
from tests.conftest import AUTH, SECRET


@pytest.fixture
def client(data_dir):
    with TestClient(create_app(SECRET)) as client:
        yield client


def test_zoom_is_one_until_chosen_then_kept(client, data_dir):
    assert client.get("/settings/zoom", headers=AUTH).json() == {"zoom": 1.0}
    chosen = client.put("/settings/zoom", json={"zoom": 1.1000000000000001}, headers=AUTH)
    assert chosen.json() == {"zoom": 1.1}
    assert client.get("/settings/zoom", headers=AUTH).json() == {"zoom": 1.1}
    saved = json.loads((data_dir / "settings.json").read_text(encoding="utf-8"))
    assert saved["zoom"] == 1.1


@pytest.mark.parametrize("zoom", [0.7, 1.6, "big", None])
def test_a_zoom_off_the_steps_is_refused(client, zoom):
    assert client.put("/settings/zoom", json={"zoom": zoom}, headers=AUTH).status_code == 422
    assert client.get("/settings/zoom", headers=AUTH).json() == {"zoom": 1.0}


def test_a_hand_edited_zoom_off_the_steps_reads_as_one(client, data_dir):
    (data_dir / "settings.json").write_text(json.dumps({"zoom": 3.0}), encoding="utf-8")
    assert client.get("/settings/zoom", headers=AUTH).json() == {"zoom": 1.0}


def test_zoom_needs_the_secret(client):
    assert client.get("/settings/zoom").status_code == 401
