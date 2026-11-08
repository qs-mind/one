"""Drawing regression: synthetic evidence and scripted models only."""

# ruff: noqa: F811

import pytest

from qsone.engine import agents, truth
from qsone.engine.tools import toolset
from tests.engine_fakes import call as model_call
from tests.engine_fakes import scripted, text
from tests.test_engine_runner import (  # noqa: F401
    finish,
    links,
    make_engine,
    no_budget_card,
    project,
    registry,
    started,
    team_steps,
)
from tests.test_engine_tools import (
    ctx,  # noqa: F401
    host,  # noqa: F401
)
from tests.test_files_tools import spec_pdf  # noqa: F401


async def test_drawing_request_offers_picture_reading(ctx):
    spec = agents.lead_spec()

    def inspect(messages, info):
        offered = {t.name: t for t in info.function_tools}
        assert {"files_read", "project_map", "add_source", "ask_engineer"} <= offered.keys()
        assert "picture" in offered["files_read"].parameters_json_schema["properties"]
        assert "drawing" in offered["add_source"].description
        instructions = info.instructions
        assert "Drawings: look at the page picture" in instructions
        assert "cards" not in instructions
        return "I need the drawing file to measure quantities."

    agent = agents.build_agent(spec, scripted(inspect), toolset(spec.tools, ctx))
    await agent.run("طلع الكميات من اللوحة")


@pytest.mark.parametrize(
    "reply",
    [
        "The words were read by OCR; OCR confidence 20%–96%.",
        "النص مقروء بـ OCR بنسبة ثقة ٢٠٪–٩٦٪.",
    ],
)
def test_text_layer_is_not_ocr(reply):
    reads = [("files_read", 'file_id: sample | file: plan.pdf\n{"page": 1}\nSample plan')]
    assert truth.reading_problems(reply, reads)


def test_reading_method_and_confidence_need_evidence():
    reads = [("files_read", 'file_id: sample\n{"page": 1, "read_by": "tesseract"}\nSample')]
    assert not truth.reading_problems("Read by OCR.", reads)
    assert truth.reading_problems("OCR confidence 96%.", reads)
    assert not truth.reading_problems("The PDF text layer has no OCR confidence.", reads)


async def test_picture_reads_text_layer_page_without_overwriting(rec, spec_pdf, monkeypatch):
    from qsone.engine.tools import call
    from tests.test_files_tools import ctx_for

    class Reader:
        model_id = "sample-vision"
        on_device = True

        async def picture(self, png, *, page, points):
            assert len(points) == 2 and all(n > 0 for n in points)
            assert png.startswith(b"\x89PNG") and page == 1
            return "Sample title block: scale unreadable; ask engineer."

    import asyncio

    async def inline(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(asyncio, "to_thread", inline)
    from qsone.records import files

    before = files.file_info(rec, spec_pdf)
    result = await call(
        "files_read",
        {"file_id": spec_pdf, "pages": "1", "picture": True},
        ctx_for(rec, transcriber=Reader()),
    )
    assert '"read_by": "sample-vision"' in result
    assert "scale unreadable" in result
    assert "picture_observation" in result

    assert files.file_info(rec, spec_pdf) == before


def test_recorded_ocr_confidence_is_allowed():
    reads = [
        (
            "files_read",
            'file_id: sample\n{"page": 1, "read_by": "tesseract", "confidence": 96}\nSample',
        )
    ]
    assert not truth.reading_problems("OCR confidence 96%.", reads)
    assert truth.reading_problems("OCR confidence 20%–96%.", reads)


async def test_false_ocr_reply_is_retried_by_runner(make_engine, project, registry, monkeypatch):
    import asyncio

    from qsone.records import files
    from tests.samples import sample_pdf

    async def inline(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(asyncio, "to_thread", inline)
    file = files.add_file(
        registry.get(project),
        "plan-sample.pdf",
        sample_pdf([["Sample plan text"]]),
        actor="engineer",
    )
    lead = scripted(
        model_call("files_read", {"file_id": file.id, "pages": "1"}),
        text("The drawing words were read by OCR."),
        text("The PDF words came from its text layer; I still need to inspect the picture."),
    )
    engine = await started(make_engine(links(lead=lead, quick=lead)))
    await finish(engine, await engine.start_brief(project, "Read this drawing"))
    assert lead.calls == 3
    assert "Unsupported OCR method" in str(lead.seen[2])


_GUIDANCE_PARTS = (
    "picture=true",
    "even when",
    "title block",
    "labelled dimension",
    "measure",
    "engineer",
    "read_by",
    "not OCR",
    "confidence",
    "file/page/region",
    "ask_engineer",
    "cards",
    "calculate",
    "vision",
)


def assert_drawing_guidance(result):
    for phrase in _GUIDANCE_PARTS:
        assert phrase in result


@pytest.mark.parametrize("mode", ["sheets", "counts"])
async def test_map_drawing_modes_supply_guidance(ctx, mode):
    from qsone.engine.tools import call

    result = await call("project_map", {"mode": mode}, ctx)
    assert_drawing_guidance(result)


async def test_file_guidance_only_for_mapped_drawing_page(rec, spec_pdf):
    from qsone.engine.tools import call
    from qsone.records.mapping import store
    from tests.test_files_tools import ctx_for

    with rec.write("one") as conn:
        store.write(
            conn,
            rec,
            "map_sheets",
            {
                "file_id": spec_pdf,
                "sheet": "Sample drawing",
                "source": {"page": 1},
            },
        )
    ctx = ctx_for(rec)
    result = await call("files_read", {"file_id": spec_pdf, "pages": "2"}, ctx)
    assert "Drawing guidance:" not in result
    result = await call("files_read", {"file_id": spec_pdf, "pages": "1"}, ctx)
    assert_drawing_guidance(result)
