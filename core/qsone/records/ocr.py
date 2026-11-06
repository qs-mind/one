"""Local word OCR, using the external Apache-2.0 Tesseract program.

Page images stay in memory. Missing languages use ONE's verified model downloader.
"""

import csv
import io
import math
import os
import re
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


def model_folder() -> Path:
    return download.folder(MODELS, settings.data_dir() / "models")


def system_folders(executable: str) -> list[Path]:
    # Ask the installed binary for its compiled-in folder, ignoring the user's override.
    env = {k: v for k, v in os.environ.items() if k != "TESSDATA_PREFIX"}
    try:
        result = subprocess.run(
            [executable, "--list-langs"],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
            env=env,
        )
        match = re.search(r'List of available languages in "([^"]+)"', result.stdout)
        if match:
            return [Path(match[1])]
    except (OSError, subprocess.SubprocessError):
        pass
    return [
        Path(executable).parent / "tessdata",
        Path("/usr/share/tessdata"),
        Path("/usr/share/tesseract-ocr/5/tessdata"),
        Path("/usr/local/share/tessdata"),
        Path("/opt/homebrew/share/tessdata"),
    ]


def find_languages(executable: str) -> tuple[Path, str] | None:
    folders = []
    if prefix := os.environ.get("TESSDATA_PREFIX"):
        folders.append(Path(prefix))
    folders.append(model_folder())
    system = system_folders(executable)
    folders.extend(system)
    for folder in folders:
        if all((folder / f"{lang}.traineddata").is_file() for lang in ("ara", "eng")):
            return folder, "ara+eng"
    try:
        return ensure_models(), "ara+eng"
    except (download.DownloadError, OSError):
        # Offline or no space: keep reading English with installed system data.
        english = next((p for p in system if (p / "eng.traineddata").is_file()), None)
        return (english, "eng") if english is not None else None


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
        # TSV already supplies reading order. Each citable piece owns exactly one box.
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
