"""Text in pictures read on this computer (records.ocr): synthetic inputs and scripted detector
and recogniser sessions only; no model downloads, no AI calls."""

import subprocess
import sys

import numpy as np
import pytest
from PIL import Image, ImageDraw

from qsone.records import arabic, ocr, ocr_lines
from qsone.records.ocr_engine import Engine, OcrError
from tests import ocr_fakes


def _logical(text: str) -> str:
    return "".join(c for c, _ in arabic.logical_order([(c, None) for c in text]))


@pytest.mark.parametrize(
    "visual, logical",
    [
        ("مس ٤٥ – مس ٢٠", "٢٠ سم – ٤٥ سم"),
        ("٢-١-١٢ دنبلا", "البند ١٢-١-٢"),
        ("12-1-2 دنبلا", "البند 12-1-2"),
        ("1:1 ةبسنب", "بنسبة 1:1"),
        ("(Frames) تاراطإلا", "الإطارات (Frames)"),
        ("ماظنلا ASTM C1152/C1152M", "ASTM C1152/C1152M النظام"),
        ("%29.29 31.85 سرام", "مارس 31.85 %29.29"),
        ("ASTM C 1152", "ASTM C 1152"),
    ],
)
def test_a_line_is_put_in_reading_order(visual, logical):
    assert _logical(visual) == logical


def test_boxes_come_from_the_probability_map():
    prob = np.zeros((100, 200), np.float32)
    prob[20:30, 10:110] = 0.9  # one line
    prob[60:70, 150:190] = 0.8  # another
    prob[90:91, 5:6] = 0.9  # a speck, too small to be text
    prob[45:50, 50:60] = 0.4  # too faint
    found = ocr_lines.boxes_from_map(prob)
    assert len(found) == 2
    (first, score), (second, _) = sorted(found, key=lambda f: f[0][0][1])
    xs, ys = [p[0] for p in first], [p[1] for p in first]
    assert min(xs) < 10 and max(xs) > 110 and min(ys) < 20 and max(ys) > 30
    assert max(xs) - min(xs) < 120 and 0.5 < score <= 0.9  # dilated edges count as 0
    assert min(p[0] for p in second) > 140


def test_a_long_line_is_cut_at_blank_gaps():
    line = Image.new("RGB", (400, 40), "white")
    draw = ImageDraw.Draw(line)
    for x in (5, 105, 205, 305):  # four inked words with blank gaps between
        draw.rectangle((x, 16, x + 80, 24), fill="black")
    cuts = ocr_lines.split_line(line)
    assert len(cuts) > 1 and cuts[0][0] == 0 and cuts[-1][1] == 400
    for _, end in cuts[:-1]:
        assert not np.any(np.asarray(line.convert("L"))[:, end] < 128)  # never through ink
    assert ocr_lines.split_line(Image.new("RGB", (150, 40), "white")) == [(0, 150)]


def test_scripted_logits_give_words_boxes_and_confidence():
    chars = ocr_fakes.CHARS
    pred = np.stack([ocr_fakes.logits("ab 12", 0.9, chars, steps=10)])
    read = ocr_lines.decode(pred, chars, [1.0])[0]
    assert "".join(c for c, _, _ in read) == "ab 12"
    assert all(0 < fx <= 1 for _, _, fx in read)
    quad = [[0, 0], [100, 0], [100, 10], [0, 10]]
    found = ocr_lines.words(read, quad)
    assert [w.text for w in found] == ["ab", "12"]
    assert found[0].box[2] <= found[1].box[0]  # left to right, each its own box
    assert found[0].confidence == pytest.approx(0.9)
    # Arabic read right to left: the words come in reading order, boxes stay on the page.
    arabic_read = ocr_lines.decode(np.stack([ocr_fakes.logits("ةناسرخ", 0.9)]), chars, [1.0])[0]
    assert [w.text for w in ocr_lines.words(arabic_read, quad)] == ["خرسانة"]


def test_a_page_is_read_through_the_detector_and_the_recogniser(monkeypatch, tmp_path):
    detector = ocr_fakes.FakeDetector([(0.1, 0.1, 0.9, 0.3)])
    recogniser = ocr_fakes.FakeRecogniser(["concrete works total"])
    ocr_fakes.install(monkeypatch, tmp_path, detector, recogniser)
    page = ocr.read_image(ocr_fakes.picture(400, 200), points=(200.0, 100.0))
    assert [w.text for w in page.words] == ["concrete", "works", "total"]
    assert page.boxes == 1 and len(detector.calls) >= 1
    assert detector.calls[0][2] % 32 == 0 and detector.calls[0][3] % 32 == 0
    assert recogniser.calls[0][2] == 48
    for word in page.words:  # boxes in the page's points, inside the marked line
        x0, y0, x1, y1 = word.box
        assert 0 <= x0 < x1 <= 200 and 0 <= y0 < y1 <= 100
    assert page.words[0].confidence == pytest.approx(99.0)
    pieces = page.pieces(3)
    assert {p.locator["read_by"] for p in pieces} == {"ppocr-v5"}
    assert all(p.locator["page"] == 3 and len(p.locator["box"]) == 4 for p in pieces)


def test_a_weak_page_is_read_again_turned(monkeypatch, tmp_path):
    # Upright it reads as nonsense at low confidence; turned 180° it reads well.
    texts = iter([("xx", 0.3), ("concrete works for the sample building", 0.99)])

    class Turning(ocr_fakes.FakeRecogniser):
        def run(self, _, feeds):
            text, self.confidence = next(texts, ("", 0.99))
            self.texts = [text]
            return super().run(_, feeds)

    ocr_fakes.install(monkeypatch, tmp_path, recogniser=Turning([]))
    page = ocr.read_image(ocr_fakes.picture(400, 200), points=(400.0, 200.0))
    assert page.turned == 180 and len(page.words) == 6
    for word in page.words:  # mapped back onto the picture as it is: the line near the bottom
        assert word.box[1] >= 100


def test_turned_boxes_map_back():
    # A box read on the turned picture of a 100 x 200 page, back on the page as it is.
    assert ocr._back([10, 20, 30, 40], 0, (100, 200)) == [10, 20, 30, 40]
    assert ocr._back([10, 20, 30, 40], 180, (100, 200)) == [70, 160, 90, 180]
    assert ocr._back([10, 20, 30, 40], 90, (100, 200)) == [60, 10, 80, 30]
    assert ocr._back([10, 20, 30, 40], 270, (100, 200)) == [20, 170, 40, 190]


def test_a_crop_is_read_by_the_recogniser_alone(monkeypatch, tmp_path):
    class NoDetector(ocr_fakes.FakeDetector):
        def run(self, *_):
            raise AssertionError("a crop never goes through the detector")

    ocr_fakes.install(monkeypatch, tmp_path, NoDetector(), ocr_fakes.FakeRecogniser(["١٥٠"]))
    page = ocr.read_crop(ocr_fakes.picture(60, 20), points=(20.0, 6.67))
    assert [w.text for w in page.words] == ["١٥٠"]


def test_the_character_list_must_fit_the_model(monkeypatch, tmp_path):
    with pytest.raises(OcrError):
        Engine(ocr_fakes.FakeDetector(), ocr_fakes.FakeRecogniser([], width=10), ocr_fakes.CHARS)
    wrong = ocr_fakes.FakeRecogniser(["ab"], width=10)
    wrong.get_outputs = lambda: [ocr_fakes._Port("y", [None, None, "classes"])]  # unknown here
    ocr_fakes.install(monkeypatch, tmp_path, recogniser=wrong)
    with pytest.raises(OcrError):
        ocr.read_image(ocr_fakes.picture(), points=(10.0, 10.0))


def test_the_characters_come_from_the_recogniser_yml(tmp_path):
    from qsone.records.ocr_engine import characters

    (tmp_path / "rec").mkdir()
    (tmp_path / "rec" / "inference.yml").write_text(
        "PostProcess:\n  name: CTCLabelDecode\n  character_dict:\n  - '0'\n  - ب\n  - ':'\n",
        encoding="utf-8",
    )
    assert characters(tmp_path) == ["", "0", "ب", ":", " "]


def test_the_ocr_part_comes_from_setup(tmp_path, monkeypatch):
    import dataclasses
    import hashlib

    import httpx

    from qsone.setup import manifest, runner

    body = b"synthetic model sample"
    digest = hashlib.sha256(body).hexdigest()
    part = dataclasses.replace(
        manifest.OCR,
        files=tuple(
            manifest.PartFile(f.path, f"https://huggingface.co/sample/{f.path}", len(body), digest)
            for f in manifest.OCR.files
        ),
    )
    hub = []

    def respond(request):
        hub.append(request.url.host)
        return httpx.Response(200, content=body)

    setup = runner.Setup(
        tmp_path / "models",
        tmp_path / "sandbox",
        parts=(part,),
        client=lambda: httpx.Client(transport=httpx.MockTransport(respond)),
        runs_here=lambda p: True,
    )
    monkeypatch.setattr(runner, "part_path", setup.part_path)
    monkeypatch.setattr(ocr, "available", lambda: True)
    assert not ocr.ready()  # not fetched yet: scanned pages go to the AI page reader
    setup.ensure()
    assert set(hub) == {"huggingface.co"} and ocr.ready()
    assert (ocr.folder() / "rec" / "inference.yml").read_bytes() == body
    monkeypatch.setattr(ocr, "available", lambda: False)  # no onnxruntime here
    assert not ocr.ready()


def _page(*texts, confidence=95.0, boxes=0):
    return ocr_fakes.words(*texts, confidence=confidence, boxes=boxes)


def test_number_pages_and_weak_pages_go_on_and_clean_prose_stays():
    prose = "The contractor shall keep the site clean and safe at all times during works".split()
    assert ocr.wants_ai(_page(*prose)) is None
    assert ocr.wants_ai(_page(*prose, "12.5")) == "numbers"  # a decimal mark read locally
    assert ocr.wants_ai(_page(*[str(n) for n in range(10, 18)], *prose)) == "numbers"
    assert ocr.wants_ai(_page(*prose, confidence=70)) == "weak"
    assert ocr.wants_ai(_page("stamp", boxes=3)) == "weak"
    assert ocr.wants_ai(ocr.Page([], True, 0)) is None  # a blank page
    many_low = [ocr.Word(t, [0, 0, 1, 1], 99) for t in prose] + [
        ocr.Word("x", [0, 0, 1, 1], 40)
    ] * 2
    assert ocr.wants_ai(ocr.Page(many_low, False)) == "weak"
    piece = _page("1", "2", "3", "4", "5", "6", "7", "8").pieces(1)[0]
    assert piece.locator["wants_ai"] == "numbers"


def test_importing_the_reader_loads_no_opencv_bidi_rapidocr_or_runtime():
    code = (
        "import sys, qsone.records.ocr, qsone.tools.files, qsone.records.mapping.worker; "
        "print([m for m in ('cv2', 'bidi', 'rapidocr', 'onnxruntime', 'pyclipper', 'shapely')"
        " if m in sys.modules])"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "[]"
