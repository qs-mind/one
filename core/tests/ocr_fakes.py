"""Scripted stand-ins for the PP-OCR detector and recogniser sessions: ONE's own pipeline runs on
them as on the real models, and nothing downloads. Synthetic inputs only."""

import numpy as np

from qsone.records import ocr
from qsone.records.ocr_engine import Engine

CHARS = [
    "",
    *"0123456789.,:-()×%٠١٢٣٤٥٦٧٨٩٫٬",
    *"abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ",
    *map(chr, range(0x0621, 0x064B)),
    " ",
]


class _Port:
    def __init__(self, name: str, shape=None):
        self.name, self.shape = name, shape


class FakeDetector:
    """Marks text where `boxes` say (fractions of the picture: x0, y0, x1, y1)."""

    def __init__(self, boxes=((0.1, 0.1, 0.9, 0.3),)):
        self.boxes, self.calls = list(boxes), []

    def get_inputs(self):
        return [_Port("x")]

    def run(self, _, feeds):
        x = feeds["x"]
        self.calls.append(x.shape)
        h, w = x.shape[2:]
        prob = np.zeros((1, 1, h, w), np.float32)
        for x0, y0, x1, y1 in self.boxes:
            prob[0, 0, int(y0 * h) : int(y1 * h), int(x0 * w) : int(x1 * w)] = 0.9
        return [prob]


def logits(text: str, confidence: float = 0.99, chars=CHARS, steps: int = 0) -> np.ndarray:
    """One recogniser row reading `text` left to right on the picture (visual order), each
    character in its own column with blanks between."""
    steps = max(steps, 2 * len(text) + 1)
    row = np.zeros((steps, len(chars)), np.float32)
    row[:, 0] = 1.0
    for i, ch in enumerate(text):
        col = 2 * i + 1
        row[col, 0] = 1 - confidence
        row[col, chars.index(ch)] = confidence
    return row


class FakeRecogniser:
    """Reads each crop as the next of `texts` (visual order), at `confidence`."""

    def __init__(self, texts, confidence: float = 0.99, chars=CHARS, width: int | None = None):
        self.texts, self.confidence, self.chars = list(texts), confidence, chars
        self.width = len(chars) if width is None else width
        self.calls = []

    def get_inputs(self):
        return [_Port("x")]

    def get_outputs(self):
        return [_Port("y", [None, None, self.width])]

    def run(self, _, feeds):
        x = feeds["x"]
        self.calls.append(x.shape)
        texts = [self.texts.pop(0) if self.texts else "" for _ in range(x.shape[0])]
        steps = max(2 * len(t) + 1 for t in texts)
        rows = [logits(t, self.confidence, self.chars, steps) for t in texts]
        out = np.stack(rows)
        if self.width != len(self.chars):
            out = np.zeros((*out.shape[:2], self.width), np.float32)
        return [out]


def install(monkeypatch, tmp_path, detector=None, recogniser=None) -> Engine:
    """Makes the text reader for pictures ready, on scripted sessions."""
    engine = Engine(detector or FakeDetector(), recogniser or FakeRecogniser([]), CHARS)
    monkeypatch.setattr(ocr, "available", lambda: True)
    monkeypatch.setattr(ocr, "folder", lambda: tmp_path)
    monkeypatch.setattr(ocr, "_loaded", (tmp_path, engine))
    return engine


def picture(width: int = 400, height: int = 200) -> bytes:
    import io

    from PIL import Image

    out = io.BytesIO()
    Image.new("RGB", (width, height), "white").save(out, format="PNG")
    return out.getvalue()


def words(*texts, confidence: float = 95.0, boxes: int = 0):
    """A local reading made of these words, one line."""
    found = [ocr.Word(t, [10.0 * i, 10, 10.0 * i + 8, 20], confidence) for i, t in enumerate(texts)]
    return ocr.Page(found, False, boxes)
