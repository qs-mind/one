"""Every part ONE needs beyond the installer, each file pinned by URL, size and SHA-256.

A part is one of three kinds:
- `model`: files fetched into `<data>/models/<folder>/<revision>/` (the search models' folder);
- `sandbox`: the Sandbox's Python, fetched and unpacked by `sandbox.runtime.install`;
- `bundled`: shipped with the installer and only checked, so nothing downloads and its size is 0.

The search model's and the Sandbox's files are read from their own modules, so each is pinned in
one place. The OCR files are PaddlePaddle's own ONNX exports on Hugging Face (Apache-2.0), as the
OCR spike pinned them (research_notes/2026-11-10-phase1-spikes/ocr.md); their sizes and digests
were checked against Hugging Face on 10 Nov 2026.
"""

from dataclasses import dataclass
from typing import Literal

from qsone import copy
from qsone.meaning.manifest import EMBEDDER
from qsone.sandbox import runtime

Kind = Literal["model", "sandbox", "bundled"]


@dataclass(frozen=True)
class PartFile:
    path: str  # inside the part's folder
    url: str
    size: int
    sha256: str


@dataclass(frozen=True)
class Part:
    id: str
    kind: Kind
    title: dict[str, str]
    affects: dict[str, str]  # what does not work without it
    cannot_run: dict[str, str]  # the reason when it cannot run on this computer
    files: tuple[PartFile, ...] = ()
    folder: str = ""  # under the kind's root: `<folder>/<revision>/`
    revision: str = ""

    @property
    def size(self) -> int:
        return sum(f.size for f in self.files)


SEARCH_MODEL = Part(
    id="search-model",
    kind="model",
    title=copy.SETUP_SEARCH_MODEL,
    affects=copy.SETUP_SEARCH_MODEL_AFFECTS,
    cannot_run=copy.MEANING_NOT_ON_THIS_COMPUTER,
    files=tuple(PartFile(f.path, EMBEDDER.url(f), f.size, f.sha256) for f in EMBEDDER.files),
    folder=EMBEDDER.id,
    revision=EMBEDDER.revision,
)

SANDBOX_RUNTIME = Part(
    id="sandbox-runtime",
    kind="sandbox",
    title=copy.SETUP_SANDBOX,
    affects=copy.SETUP_SANDBOX_AFFECTS,
    cannot_run=copy.SETUP_SANDBOX_NOT_HERE,
    files=tuple(PartFile(f.name, f.url, f.size, f.sha256) for f in runtime.FILES),
    folder="cpython-wasi",
    revision=runtime.VERSION,
)

# The `drawings/` helper (acadrust), shipped beside the core; checked by its `--version` answer.
DWG_READER = Part(
    id="dwg-reader",
    kind="bundled",
    title=copy.SETUP_DWG,
    affects=copy.SETUP_DWG_AFFECTS,
    cannot_run=copy.SETUP_DWG_MISSING,
)

_HF = "https://huggingface.co"
_DET = (
    f"{_HF}/PaddlePaddle/PP-OCRv5_mobile_det_onnx/resolve/e6f4fa85f00e168c862bc462aebca69eef9b3d3d"
)
_REC = (
    f"{_HF}/PaddlePaddle/arabic_PP-OCRv5_mobile_rec_onnx/resolve/"
    "14aaedcd75825982689ecf5cd64ab33ee083215a"
)

# PP-OCRv5 mobile detector and Arabic mobile recogniser; `rec/inference.yml` holds its 747
# characters. 12,832,533 bytes in all.
OCR = Part(
    id="ocr",
    kind="model",
    title=copy.SETUP_OCR,
    affects=copy.SETUP_OCR_AFFECTS,
    cannot_run=copy.SETUP_OCR_NOT_HERE,
    files=(
        PartFile(
            "det/inference.onnx",
            f"{_DET}/inference.onnx",
            4_826_518,
            "a431985659dc921974177a95adcfbb90fd9e51989a5e04d70d0b75f597b6e61d",
        ),
        PartFile(
            "det/inference.yml",
            f"{_DET}/inference.yml",
            903,
            "98069072e1b6b37d727fd9d9f11725faa46d6ea0de012f2ed26caea011c37699",
        ),
        PartFile(
            "rec/inference.onnx",
            f"{_REC}/inference.onnx",
            7_998_947,
            "799113ebf267fbe742deb99eb36e8d42c9ddc5291ceacf92add41b4d52a59110",
        ),
        PartFile(
            "rec/inference.yml",
            f"{_REC}/inference.yml",
            6_165,
            "21368419e6c016c31db55d316d59e11c128e1913e6e6fe10287084710043d3a6",
        ),
    ),
    folder="ppocr-v5-mobile-arabic",
    revision="det-e6f4fa85f00e-rec-14aaedcd7582",
)

PARTS: tuple[Part, ...] = (SEARCH_MODEL, SANDBOX_RUNTIME, DWG_READER, OCR)
