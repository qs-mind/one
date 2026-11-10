"""PP-OCRv5 on onnxruntime: the mobile detector finds the lines, the Arabic mobile recogniser reads
them (it reads Western digits and Latin letters too). Imported only when a page is read, so the
rest of ONE never loads onnxruntime for it.

The detector takes the page at most `MAX_SIDE` px on its long side, in multiples of 32,
(x/255 - 0.5)/0.5 in BGR order, as the models were trained; the recogniser takes lines 48 px high.
"""

import math
from pathlib import Path

import numpy as np
from PIL import Image

from qsone.records import ocr_lines

MAX_SIDE = 2000  # the detector's long side: a 1,600 px wide A4 page (the spike's held-out pages)
MIN_SIDE = 736
HEIGHT = 48  # the recogniser's line height
BATCH = 6


class OcrError(ValueError):
    """The model files do not fit this code (a wrong or changed file)."""


def characters(folder: Path) -> list[str]:
    """The recogniser's characters from its `inference.yml`, with the CTC blank first and a space
    last, as PaddleOCR decodes them."""
    import yaml  # PyYAML is already in ONE (runtime.lock)

    config = yaml.safe_load((folder / "rec" / "inference.yml").read_text(encoding="utf-8"))
    return ["", *(str(c) for c in config["PostProcess"]["character_dict"]), " "]


def _session(path: Path, threads: int):
    import onnxruntime as ort

    from qsone.meaning.onnx import session_options

    options = session_options(threads)
    options.log_severity_level = 4
    return ort.InferenceSession(str(path), options, providers=["CPUExecutionProvider"])


def _round32(v: float) -> int:
    return max(32, int(round(v / 32) * 32))


def _bgr(image: Image.Image) -> np.ndarray:
    a = np.asarray(image, dtype=np.float32)[:, :, ::-1] / 255.0
    return (a - 0.5) / 0.5


class Engine:
    def __init__(self, detector, recogniser, chars: list[str]):
        width = recogniser.get_outputs()[0].shape[-1]
        if isinstance(width, int) and width != len(chars):
            raise OcrError("the recogniser's output does not fit its character list")
        self.det, self.rec, self.chars = detector, recogniser, chars

    @classmethod
    def load(cls, folder: Path, threads: int) -> "Engine":
        chars = characters(folder)
        det = _session(folder / "det" / "inference.onnx", threads)
        return cls(det, _session(folder / "rec" / "inference.onnx", threads), chars)

    def detect(self, image: Image.Image) -> list[list[list[float]]]:
        w, h = image.size
        ratio = min(1.0, MAX_SIDE / max(w, h))
        if min(w, h) * ratio < MIN_SIDE:
            ratio = MIN_SIDE / min(w, h)
        dw, dh = _round32(w * ratio), _round32(h * ratio)
        small = image if (dw, dh) == (w, h) else image.resize((dw, dh), Image.BILINEAR)
        x = np.ascontiguousarray(_bgr(small).transpose(2, 0, 1)[None])
        prob = self.det.run(None, {self.det.get_inputs()[0].name: x})[0][0, 0]
        quads = []
        for quad, _ in ocr_lines.boxes_from_map(prob):
            quads.append(
                [
                    [min(max(px * w / dw, 0), w - 1), min(max(py * h / dh, 0), h - 1)]
                    for px, py in quad
                ]
            )
        return quads

    def _recognise(self, crops: list[Image.Image]):
        order = np.argsort([c.width / c.height for c in crops])
        out = [None] * len(crops)
        name = self.rec.get_inputs()[0].name
        for start in range(0, len(crops), BATCH):
            idx = order[start : start + BATCH]
            ratios = [crops[i].width / crops[i].height for i in idx]
            width = int(HEIGHT * max(320 / HEIGHT, *ratios))
            x = np.zeros((len(idx), 3, HEIGHT, width), np.float32)
            used = []
            for row, i in enumerate(idx):
                rw = min(width, int(math.ceil(HEIGHT * ratios[row])))
                x[row, :, :, :rw] = _bgr(crops[i].resize((rw, HEIGHT), Image.BILINEAR)).transpose(
                    2, 0, 1
                )
                used.append(rw / width)
            pred = self.rec.run(None, {name: x})[0]
            if pred.shape[-1] != len(self.chars):
                raise OcrError("the recogniser's output does not fit its character list")
            for row, chars in zip(idx, ocr_lines.decode(pred, self.chars, used), strict=True):
                out[row] = chars
        return out

    def recognise(self, crops: list[Image.Image]):
        """Per crop, its characters (visual order) with probability and x fraction; a long line
        is cut at blank gaps and its pieces read on their own."""
        pieces, owner = [], []
        for i, line in enumerate(crops):
            for x0, x1 in ocr_lines.split_line(line):
                pieces.append(line.crop((x0, 0, x1, line.height)))
                owner.append((i, x0, x1))
        out = [[] for _ in crops]
        for (i, x0, x1), chars in zip(
            owner, self._recognise(pieces) if pieces else [], strict=True
        ):
            w = crops[i].width
            if out[i] and chars:
                out[i].append((" ", 1.0, x0 / w))
            out[i] += [(c, p, (x0 + fx * (x1 - x0)) / w) for c, p, fx in chars]
        return out

    def read(self, image: Image.Image) -> tuple[list[ocr_lines.Line], int]:
        """The page's lines in reading order, and how many text boxes the detector found."""
        quads = self.detect(image)
        made = [ocr_lines.crop(image, q) for q in quads]
        read = self.recognise([c for c, _ in made]) if made else []
        lines = []
        for quad, (_, turned), chars in zip(quads, made, read, strict=True):
            found = ocr_lines.words(chars, quad, turned)
            if found:
                lines.append(ocr_lines.Line(quad, found))
        return ocr_lines.sort_lines(lines), len(quads)

    def read_line(self, image: Image.Image) -> list[ocr_lines.Word]:
        """A small crop read as one line by the recogniser alone (the detector finds nothing in
        many single-number crops)."""
        w, h = image.size
        quad = [[0.0, 0.0], [float(w), 0.0], [float(w), float(h)], [0.0, float(h)]]
        return ocr_lines.words(self.recognise([image])[0], quad)
