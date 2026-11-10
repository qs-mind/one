"""Reading text in pictures on this computer: PP-OCRv5's mobile detector and Arabic recogniser
(Apache-2.0) on the onnxruntime ONE ships, run by ONE's own numpy and Pillow pipeline
(`ocr_engine`, `ocr_lines`; decisions §17.19). The model files are setup's part "ocr".

Until that part is in place, or where onnxruntime has no wheel (Intel Macs, macOS 13), `ready()`
is false and scanned pages go to the engineer's AI page reader only.

A local reading is for search and locating only: its numbers are unchecked observations. Before
one is cited, imported or priced, the AI or the engineer reads it (`wants_ai` sends number pages
and weak pages on; `source_evidence` refuses a page that only a local reader read). Readings made
by the old Tesseract driver (`read_by` "tesseract") are kept and read as local readings.

Page images stay in memory. Importing this module loads no model runtime."""

import importlib.util
import io
import re
import struct
import threading
from dataclasses import dataclass
from pathlib import Path

READ_BY = "ppocr-v5"
LOCAL_READERS = frozenset({"tesseract", READ_BY})
MIN_CONFIDENCE = 60  # a word under this is marked `ocr_low_confidence`
# Routing (the spike's thresholds, from 19 pages): a weak page, then a number page.
WEAK_MEAN = 88
WEAK_SHARE = 0.08  # of words under MIN_CONFIDENCE
WEAK_WORDS = 5  # boxes found but fewer words read
NUMBERS = 8
DIGIT_SHARE = 0.03
TURNS = (180, 90, 270)  # tried in turn while a page reads weak
THREADS = 4

_LOCK = threading.Lock()  # one page at a time: about 750 MB at peak beside the search model
_loaded: tuple[Path, object] | None = None
_NUMBER = re.compile(r"[0-9٠-٩۰-۹]")
_MARKED = re.compile(r"[0-9٠-٩۰-۹][.,٫٬][0-9٠-٩۰-۹]")


@dataclass(frozen=True)
class Word:
    text: str
    box: list[float]  # x0, y0, x1, y1 in PDF points (or image pixels) from the top left
    confidence: float  # 0..100
    line: tuple[int, int, int] = (0, 0, 0)  # block, paragraph, line within this page


@dataclass(frozen=True)
class Page:
    words: list[Word]
    low_confidence: bool
    boxes: int = 0  # text boxes the detector found
    turned: int = 0  # degrees the picture was turned to read it

    def pieces(self, page: int, read_by: str = READ_BY):
        from qsone.records.extract import Piece

        common = {"page": page, "read_by": read_by}
        if reason := wants_ai(self):
            common["wants_ai"] = reason
        # Each citable piece owns exactly one box, in reading order.
        pieces = [
            Piece(
                common
                | {
                    "box": word.box,
                    "confidence": word.confidence,
                    "ocr_low_confidence": word.confidence < MIN_CONFIDENCE,
                },
                word.text,
            )
            for word in self.words
        ]
        return pieces or [Piece(common | {"ocr_low_confidence": True}, "")]


def png_size(png: bytes) -> tuple[int, int]:
    if png[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("expected a PNG image")
    return struct.unpack(">II", png[16:24])


def available() -> bool:
    """onnxruntime is on this computer (no wheel for Intel Macs or macOS 13)."""
    return importlib.util.find_spec("onnxruntime") is not None


def folder() -> Path | None:
    """The model files, when setup has them in place."""
    from qsone.setup import runner

    return runner.part_path("ocr")


def ready() -> bool:
    return available() and folder() is not None


def is_local(locator: dict) -> bool:
    return locator.get("read_by") in LOCAL_READERS


def _mean(page: Page) -> float:
    return sum(w.confidence for w in page.words) / len(page.words) if page.words else 0.0


def weak(page: Page) -> bool:
    """Handwriting, stamps, drawings, bad or turned scans: too unsure for search."""
    if not page.words:
        return page.boxes > 0
    low = sum(w.confidence < MIN_CONFIDENCE for w in page.words) / len(page.words)
    return (
        _mean(page) < WEAK_MEAN
        or low >= WEAK_SHARE
        or (page.boxes > 0 and len(page.words) < WEAK_WORDS)
    )


def wants_ai(page: Page) -> str | None:
    """Why a locally read page goes on to the engineer's AI page reader: "weak", "numbers" (a
    BOQ, a price list, a table: 8 numbers or more, digits 3% of its characters, or any decimal
    or thousands mark read locally), or None for clean prose that stays local."""
    if weak(page):
        return "weak"
    text = "".join(w.text for w in page.words)
    numbers = [w.text for w in page.words if _NUMBER.search(w.text)]
    digits = len(_NUMBER.findall(text))
    if (
        len(numbers) >= NUMBERS
        or (text and digits / len(text) >= DIGIT_SHARE)
        or any(_MARKED.search(n) for n in numbers)
    ):
        return "numbers"
    return None


def preferred(chunks: list[tuple[dict, str]]) -> list[tuple[dict, str]]:
    """One reading per page: where the AI read a page that a local reader read too, the AI's."""
    by_ai = {loc.get("page") for loc, _ in chunks if loc.get("read_by") and not is_local(loc)}
    return [(loc, t) for loc, t in chunks if not (is_local(loc) and loc.get("page") in by_ai)]


def _engine():
    global _loaded
    where = folder()
    if where is None or not available():
        raise FileNotFoundError("the text reader for pictures is not in place")
    if _loaded is None or _loaded[0] != where:
        from qsone.records.ocr_engine import Engine

        _loaded = (where, Engine.load(where, THREADS))
    return _loaded[1]


def _picture(png: bytes):
    from PIL import Image

    with Image.open(io.BytesIO(png)) as image:
        return image.convert("RGB")


def _turned(image, turned: int):
    from PIL import Image

    turn = {180: Image.Transpose.ROTATE_180, 90: Image.Transpose.ROTATE_90}
    return image.transpose(turn.get(turned, Image.Transpose.ROTATE_270))


def _back(box: list[float], turned: int, size: tuple[int, int]) -> list[float]:
    """A box read on the picture turned by `turned` degrees (counter-clockwise), on the
    picture as it is (`size`)."""
    w, h = size
    a, b, c, d = box
    if turned == 180:
        return [w - c, h - d, w - a, h - b]
    if turned == 90:
        return [w - d, a, w - b, c]
    if turned == 270:
        return [b, h - c, d, h - a]
    return box


def _page(lines, boxes: int, turned: int, size, scale) -> Page:
    sx, sy = scale
    found = []
    for n, line in enumerate(lines, 1):
        for word in line.words:
            x0, y0, x1, y1 = _back(word.box, turned, size)
            box = [round(x0 * sx, 2), round(y0 * sy, 2), round(x1 * sx, 2), round(y1 * sy, 2)]
            found.append(Word(word.text, box, round(word.confidence * 100, 1), (1, 1, n)))
    page = Page(found, False, boxes, turned)
    return Page(found, weak(page) or not found, boxes, turned)


def read_image(png: bytes, *, points: tuple[float, float]) -> Page:
    """Reads a page picture; boxes in `points` (the page's size in PDF points, or the picture's
    in pixels). A page that reads weak is read again turned 180°, 90° and 270°, and the reading
    with the best mean confidence is kept. Raises FileNotFoundError when `ready()` is false."""
    image = _picture(png)
    size = image.size
    scale = (points[0] / size[0], points[1] / size[1])
    with _LOCK:
        engine = _engine()
        best = _page(*engine.read(image), 0, size, scale)
        for turned in TURNS:
            if not weak(best):
                break
            again = _page(*engine.read(_turned(image, turned)), turned, size, scale)
            if _mean(again) > _mean(best):
                best = again
    return best


def read_crop(png: bytes, *, points: tuple[float, float]) -> Page:
    """A small crop (one number, one stamp line) read by the recogniser alone."""
    image = _picture(png)
    scale = (points[0] / image.size[0], points[1] / image.size[1])
    with _LOCK:
        words = _engine().read_line(image)
    from qsone.records.ocr_lines import Line

    return _page([Line([], words)], 1, 0, image.size, scale)
