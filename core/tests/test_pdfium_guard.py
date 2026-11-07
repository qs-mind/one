"""Process-wide PDFium safety; all documents below are synthetic sample data."""

import ast
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier


def test_pdfium_calls_are_guarded():
    violations = []
    for path in (Path(__file__).parents[1] / "qsone").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))

        def visit(node, guarded=False, path=path):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                guarded = any(ast.unparse(d) == "pdfium_locked" for d in node.decorator_list)
            if isinstance(node, ast.With):
                guarded |= any("PDFIUM" == ast.unparse(i.context_expr) for i in node.items)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                name = ast.unparse(node.func)
                if (
                    any(
                        s in name
                        for s in ("PdfDocument", "PdfPage", "PdfImage", "PdfMatrix", "FPDF")
                    )
                    and not guarded
                ):
                    violations.append(f"{path.name}:{node.lineno}: {name}")
            for child in ast.iter_child_nodes(node):
                visit(child, guarded)

        visit(tree)
    assert not violations, "\n".join(violations)


def test_real_paths_eight_threads_twenty_rounds(rec):
    from qsone.records import files, render
    from qsone.records.extract import extract
    from qsone.records.mapping.picture import crop
    from tests.samples import sample_pdf

    data = sample_pdf([["Sample security 12345"], ["Sample second page"]])
    info = files.add_file(rec, "sample.pdf", data, actor="engineer")

    barrier = Barrier(8)

    def run(_):
        for _ in range(20):
            barrier.wait(timeout=10)
            assert extract("sample.pdf", data).pages == 2
            assert render.page_png(data, 2, 160).startswith(b"\x89PNG")
            assert crop(rec, info.id, {"page": 1}, "12345", "12345").startswith(b"\x89PNG")

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(run, range(8)))


def test_ocr_releases_pdfium_before_tesseract(monkeypatch):
    from qsone.records import ocr
    from qsone.records.pdfium_guard import PDFIUM
    from qsone.tools.files import _local_page
    from tests.samples import sample_pdf

    def read_image(png, **kwargs):
        # A second thread can acquire the lock while Tesseract is running.
        def acquire():
            taken = PDFIUM.acquire(timeout=1)
            if taken:
                PDFIUM.release()
            return taken

        with ThreadPoolExecutor(max_workers=1) as pool:
            assert pool.submit(acquire).result()
        assert png.startswith(b"\x89PNG")
        return "sample OCR"

    monkeypatch.setattr(ocr, "read_image", read_image)
    assert _local_page(sample_pdf([["Sample"]]), "pdf", 1, "fake", None, "eng") == "sample OCR"
