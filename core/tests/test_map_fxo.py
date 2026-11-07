"""FXO reproductions use synthetic source text and scripted providers only."""

import json

import pytest

from qsone.engine.connectors import standard
from qsone.engine.map_digest import digest
from qsone.records import files
from qsone.records.mapping import facts, store
from qsone.records.search import search
from qsone.tools.project_map import MapArgs, drawing_evidence, read_map
from tests.fakes_tools import tool_ctx
from tests.samples import sample_pdf


def test_reuse_provider_key_and_replace_typed_model():
    old = standard.add("Sample", "https://example.test/v1", "sample", "old")
    new = standard.add("Sample", "https://example.test/v1/", "sample", "new")
    assert new.id == old.id
    assert standard.typed() == [type(standard.typed()[0])(old.id, "new")]


def test_adjacent_phrase_label_beats_partial_and_prose(rec):
    for i, text in enumerate(
        [
            "العروض " * 20,
            "فتح عروض 16/04/1448",
            "فتح باب العروض " * 20,
            "تتضمن الشروط فتح العروض في الموعد المقرر " * 8,
            "فتح العروض 16/04/1448",
        ]
    ):
        files.add_file(rec, f"sample-{i}.pdf", sample_pdf([[text[::-1]]]), actor="test")
    assert search(rec, "فتح العروض").hits[0].file_name == "sample-4.pdf"


async def test_drawings_digest_all_files_and_51_sheets(rec):
    for i in range(18):
        name = "MAIN POWER SINGLE LINE DIAGRAM.dwg" if i == 17 else f"Sample-{i}.dwg"
        f = files.add_file(rec, name, f"sample drawing {i}".encode(), actor="test")
        with rec.write("test") as c:
            for j in range(4 if i == 17 else (2 if i < 4 else 3)):
                store.write(
                    c,
                    rec,
                    "map_sheets",
                    {
                        "file_id": f.id,
                        "sheet": f"SLD{j + 1}" if i == 17 else f"Paper{j}",
                        "number": f"EL-{504 + j:03}" if i == 17 else f"EL-{i * 3 + j:03}",
                        "title": "Sample sheet",
                        "counts": {},
                    },
                )
            if i == 17:
                store.write(
                    c,
                    rec,
                    "map_sheets",
                    {
                        "file_id": f.id,
                        "sheet": "Model",
                        "counts": {"MCCB": 339},
                    },
                )
    text = digest(rec)
    assert "drawing sheets: 51" in text
    assert "EL-000" in text
    assert "MAIN POWER SINGLE LINE DIAGRAM.dwg" in text
    rows, page = [], 1
    while page is not None:
        result = drawing_evidence(rec, MapArgs(mode="sheets", page=page))
        rows.extend(result["sheets"])
        page = result["next_page"]
    assert len(rows) == 51
    result = json.loads(
        await read_map(tool_ctx(rec), MapArgs(mode="counts", file_id=name, label="MCCB"))
    )
    assert result["counts"][0]["total"] == 339
    with pytest.raises(Exception, match="MAIN POWER SINGLE LINE DIAGRAM"):
        await read_map(tool_ctx(rec), MapArgs(mode="file", file_id="MAIN POWER SINGLE LINE.dwg"))


def test_fact_prompt_frontloads_key_lines():
    page = {
        "file_id": "sample",
        "locator": {"page": 7},
        "text": "Sample prose\n" * 100
        + "فتح العروض 16/04/1448\nالترسية 29/06/1448\nبدء الأعمال 07/07/1448",
    }
    text = facts.prompt([page])
    assert text.index("Key lines") < text.index("Sample prose")
    assert text.index("16/04/1448", text.index("Key lines")) < text.index("Sample prose")
    assert '"page": 7' in text


async def test_pdf_read_frontloads_key_lines(rec):
    from qsone.engine.tools import call

    f = files.add_file(
        rec,
        "sample.pdf",
        sample_pdf([["Sample prose"] * 40 + ["Opening 16/04/1448"]]),
        actor="test",
    )
    text = await call("files_read", {"file_id": f.id, "pages": "1"}, tool_ctx(rec))
    assert text.index("Key lines") < text.index("Sample prose")
    assert text.index("Opening 16/04/1448") < text.index("Sample prose")


async def test_model_selection_recomputes_roles_and_probes_quick(monkeypatch):
    from decimal import Decimal

    from qsone.engine import connectors, roles
    from qsone.engine.types import ModelCard, ModelChoice

    def card(name, price):
        return ModelCard(
            ModelChoice("standard:sample", name),
            name,
            "google",
            False,
            True,
            None,
            Decimal(price),
            Decimal(price),
            "sample",
        )

    sheet = [
        card("models/old", "2"),
        card("models/new", "3"),
        card("models/retired", ".1"),
        card("models/quick", ".2"),
    ]
    roles.choose("lead", sheet[0].choice)
    seen = []

    async def probe(via, **kwargs):
        seen.append(via)
        if via.endswith("/retired"):
            connectors.note_refused(sheet[2].choice)
            return {"en": "Unavailable", "ar": "مش متاح"}
        return None

    monkeypatch.setattr(connectors, "check", probe)
    await roles.select_lead(ModelChoice("standard:sample", "new"), sheet, [])
    assert roles.saved()["lead"] == sheet[1].choice
    assert roles.saved()["specialist"] == sheet[1].choice
    assert roles.saved()["quick"] == sheet[3].choice
    assert seen == ["standard:sample/models/retired", "standard:sample/models/quick"]
    seen.clear()
    await roles.select_lead(sheet[1].choice, sheet, [])
    assert all("retired" not in v for v in seen)


def test_cli_switch_selects_lead_after_connection_check(tmp_path):
    from qsone.cli.commands import Commands

    calls = []

    class Client:
        def get(self, route):
            return {"at": "sample", "roles": {}}

        def post(self, route, body):
            calls.append((route, body))
            return {"id": "standard:sample"}

        def request(self, method, route, **kwargs):
            calls.append((route, kwargs.get("json")))

    source = tmp_path / "sample-token.txt"
    source.write_text("scripted test token")
    Commands(Client(), {}, tmp_path / "session").setup_ai("google", "sample-new", source)
    assert calls[-1] == ("/settings/model", {"id": "sample-new", "connector": "standard:sample"})
    assert calls[-2][0] == "/settings/ai/check"


def test_model_route_applies_canonical_standard_choice(monkeypatch):
    from decimal import Decimal

    from fastapi.testclient import TestClient

    from qsone.app import create_app
    from qsone.engine import roles
    from qsone.engine.types import ModelCard, ModelChoice
    from tests.conftest import AUTH, SECRET

    app = create_app(SECRET)
    choice = ModelChoice("standard:sample", "models/new")
    card = ModelCard(
        choice, "Sample", "google", False, True, None, Decimal("1"), Decimal("1"), "sample"
    )

    async def sheet():
        return [card], []

    monkeypatch.setattr(app.state.engine, "sheet", sheet)
    roles.choose("lead", ModelChoice("standard:old", "old"))
    with TestClient(app) as client:
        result = client.put(
            "/settings/model", json={"id": "new", "connector": "standard:sample"}, headers=AUTH
        )
        assert client.get("/settings/model", headers=AUTH).json() == {"id": choice.model}
    assert result.status_code == 200
    assert all(c == choice for c in roles.saved().values())
