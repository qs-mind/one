"""A page with a little real text and a scanned table (decisions §17.19): the numbers this
computer read from its picture never back a source until the AI reads the page, and the AI may
read it. A very long picture is read at a bounded size. Scripted readers only."""

from qsone.engine import truth
from qsone.records import files, ocr, ocr_engine
from tests import ocr_fakes
from tests.samples import sample_pdf


def _mixed(rec):
    """Page 1: the text layer «Bill of Quantities», then local OCR words from the map worker."""
    fid = files.add_file(
        rec, "boq sample.pdf", sample_pdf([["Bill of Quantities"]]), actor="engineer"
    ).id
    page = ocr_fakes.words("Rate", "450", "Amount", "81450", "1.5")
    assert ocr.wants_ai(page)
    files.add_ocr_pages(
        rec,
        fid,
        {1: page.pieces(1)},
        read_by=ocr.READ_BY,
        actor="engineer",
        include_text_pages=True,
    )
    return fid


def test_a_local_number_beside_a_text_layer_is_no_evidence_until_the_ai_reads(rec):
    fid = _mixed(rec)
    with rec.read() as conn:
        assert files.pages_wanting_ai(conn, fid) == {1}
        found, _, seen = truth.value_in(conn, fid, {"page": 1}, "81450")
        assert found is False and "81450" not in seen  # only the text layer is checked
    stored = files.add_ocr_pages(
        rec, fid, {1: "Rate 450 Amount 81,450"}, read_by="fake-vision", actor="engineer"
    )
    assert stored == 1  # the AI reads beside the text layer and the local reading
    with rec.read() as conn:
        assert files.pages_wanting_ai(conn, fid) == set()
        assert truth.value_in(conn, fid, {"page": 1}, "81450")[0] is True
    again = files.add_ocr_pages(rec, fid, {1: "x"}, read_by="fake-vision", actor="engineer")
    assert again == 0  # never a second AI reading


def test_the_ai_never_reads_over_a_text_layer_alone(rec):
    fid = files.add_file(rec, "t sample.pdf", sample_pdf([["Total 81450"]]), actor="engineer").id
    assert files.add_ocr_pages(rec, fid, {1: "x"}, read_by="fake-vision", actor="engineer") == 0


def test_a_long_thin_picture_is_detected_at_a_bounded_size():
    from PIL import Image

    detector = ocr_fakes.FakeDetector()
    engine = ocr_engine.Engine(detector, ocr_fakes.FakeRecogniser([]), ocr_fakes.CHARS)
    engine.detect(Image.new("RGB", (200, 100_000), "white"))
    _, _, h, w = detector.calls[0]
    assert max(h, w) <= ocr_engine.MAX_LONG and h % 32 == 0 and w % 32 == 0
    engine.detect(Image.new("RGB", (400, 200), "white"))  # a usual picture keeps 736 px
    assert min(detector.calls[1][2:]) == ocr_engine.MIN_SIDE
