import pytest
from fastapi.testclient import TestClient

from qsone.__main__ import main
from qsone.app import create_app


def test_health_needs_the_secret():
    client = TestClient(create_app("s3cret"))
    assert client.get("/health").status_code == 401
    assert client.get("/health", headers={"Authorization": "Bearer wrong"}).status_code == 401
    r = client.get("/health", headers={"Authorization": "Bearer s3cret"})
    assert r.status_code == 200 and r.json() == {"ok": True}


def test_refuses_to_start_without_secret(monkeypatch):
    monkeypatch.delenv("QSONE_SECRET", raising=False)
    with pytest.raises(SystemExit):
        main(["--port", "0"])


def test_start_lists_the_models_for_the_team(data_dir, monkeypatch):
    from qsone.engine import identity_routes

    listed = []

    async def recorded(engine):
        listed.append(engine)

    monkeypatch.setattr(identity_routes, "list_models", recorded)
    app = create_app("s3cret", data_dir=data_dir)
    with TestClient(app):
        pass
    assert listed == [app.state.engine]
