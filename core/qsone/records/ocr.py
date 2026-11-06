"""Local word OCR, using the external Apache-2.0 Tesseract program.

Page images stay in memory. Models use the search downloader's size, SHA-256,
resume, free-space and atomic publication checks; no project data is sent to it.
"""

import csv
import io
import math
import os
import shutil
import struct
import subprocess
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path

from qsone import settings
from qsone.meaning import download
from qsone.meaning.manifest import ModelFile, ModelSpec

# Policy threshold, not a calibrated probability: any uncertain word requires review.
MIN_CONFIDENCE = 60
_MODEL_LOCK = threading.Lock()


class TessdataSpec(ModelSpec):
    def url(self, f: ModelFile) -> str:
        return f"https://raw.githubusercontent.com/{self.repo}/{self.revision}/{f.path}"


# Official tessdata_fast 4.1.0 (Apache-2.0). Sizes corroborated by Gentoo's
# app-text/tessdata_fast/Manifest; English SHA-256 by Homebrew's tesseract formula;
# Arabic SHA-256 by lm-kit/tessdata-fast's LFS pointer;
# the live download must match this digest.
MODELS = TessdataSpec(
    id="tessdata-fast",
    repo="tesseract-ocr/tessdata_fast",
    revision="4.1.0",
    files=(
        ModelFile(
            "ara.traineddata",
            1432056,
            "e3206d3dc87fd50c24a0fb9f01838615911d25168f4e64415244b67d2bb3e729",
        ),
        ModelFile(
            "eng.traineddata",
            4113088,
            "7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2",
        ),
    ),
    licence="Apache-2.0",
    dims=0,
    ram_bytes=0,
)


def ensure_models() -> Path:
    root = settings.data_dir() / "models"
    with _MODEL_LOCK:
        if not download.installed((MODELS,), root):
            with download.default_client() as client:
                download.download((MODELS,), root, client=client, stop=threading.Event())
    return download.folder(MODELS, root)


def find_tesseract() -> str | None:
    found = shutil.which("tesseract")
    if found:
        return found
    candidates = [
        Path("/opt/homebrew/bin/tesseract"),
        Path("/usr/local/bin/tesseract"),
        Path("/opt/local/bin/tesseract"),
    ]
    for name in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
        if base := os.environ.get(name):
            candidates.append(Path(base) / "Tesseract-OCR" / "tesseract.exe")
            candidates.append(Path(base) / "Programs" / "Tesseract-OCR" / "tesseract.exe")
    return next((str(p) for p in candidates if p.is_file() and os.access(p, os.X_OK)), None)


@dataclass(frozen=True)
class Word:
    text: str
    box: list[float]
    confidence: float
    line: tuple[int, int, int] = (0, 0, 0)  # block, paragraph, line within this page


@dataclass(frozen=True)
class Page:
    words: list[Word]
    low_confidence: bool

    def pieces(self, page: int):
        from qsone.records.extract import Piece

        common = {"page": page, "read_by": "tesseract"}
        lines: dict[tuple[int, int, int], list[Word]] = {}
        # TSV words already follow Tesseract's reading order, including RTL and mixed
        # text. Preserve that order instead of sorting by x or reversing Arabic letters.
        for word in self.words:
            lines.setdefault(word.line, []).append(word)
        pieces = []
        for words in lines.values():
            confidence = min(w.confidence for w in words)
            box = [
                min(w.box[0] for w in words),
                min(w.box[1] for w in words),
                max(w.box[2] for w in words),
                max(w.box[3] for w in words),
            ]
            pieces.append(
                Piece(
                    common
                    | {
                        "box": box,
                        "confidence": confidence,
                        "ocr_low_confidence": confidence < MIN_CONFIDENCE,
                    },
                    " ".join(w.text for w in words),
                )
            )
        return pieces or [Piece(common | {"ocr_low_confidence": True}, "")]


def png_size(png: bytes) -> tuple[int, int]:
    if png[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("expected a PNG image")
    return struct.unpack(">II", png[16:24])


def parse_tsv(tsv: str, *, pixels: tuple[int, int], points: tuple[float, float]) -> Page:
    sx, sy = points[0] / pixels[0], points[1] / pixels[1]
    words = []
    for row in csv.DictReader(io.StringIO(tsv), delimiter="\t", quoting=csv.QUOTE_NONE):
        if row["level"] != "5" or not row["text"].strip():
            continue
        x, y, w, h = (int(row[k]) for k in ("left", "top", "width", "height"))
        confidence = float(row["conf"])
        if not math.isfinite(confidence) or not 0 <= confidence <= 100:
            raise ValueError("invalid OCR confidence")
        if not (0 <= x < x + w <= pixels[0] and 0 <= y < y + h <= pixels[1]):
            raise ValueError("invalid OCR box")
        line = tuple(int(row[k]) for k in ("block_num", "par_num", "line_num"))
        words.append(
            Word(row["text"], [x * sx, y * sy, (x + w) * sx, (y + h) * sy], confidence, line)
        )
    return Page(words, not words or any(w.confidence < MIN_CONFIDENCE for w in words))


def read_image(
    png: bytes,
    *,
    points: tuple[float, float],
    executable: str,
    tessdata: Path,
    languages: str = "ara+eng",
) -> Page:
    # Set the TSV variable directly: our model folder needs no installed configs/tsv file.
    command = [
        executable,
        "stdin",
        "stdout",
        "--tessdata-dir",
        str(tessdata),
        "-l",
        languages,
        "--oem",
        "1",
        "-c",
        "tessedit_create_tsv=1",
    ]
    try:
        result = subprocess.run(command, input=png, capture_output=True, timeout=120, check=True)
    except subprocess.CalledProcessError as error:
        # Only an explicit stdin-read failure permits the brief's temporary-image exception.
        message = (error.stderr or b"").lower()
        if b"stdin" not in message or not any(
            phrase in message for phrase in (b"cannot read", b"failed to read", b"cannot open")
        ):
            raise
        with tempfile.TemporaryDirectory(prefix="one-ocr-") as temporary:
            path = Path(temporary) / "page.png"
            path.write_bytes(png)
            command[1] = str(path)
            result = subprocess.run(command, capture_output=True, timeout=120, check=True)
    return parse_tsv(result.stdout.decode("utf-8"), pixels=png_size(png), points=points)
