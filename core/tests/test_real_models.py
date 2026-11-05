"""Opt-in: the real search model. Skipped unless QSONE_REAL_MODELS names a models folder.

The first run downloads the 135 MB of pinned files from huggingface.co into that folder (free);
later runs make no request. Run it alone, with no other heavy work: it peaks under 1 GB of RAM.
Every text here is synthetic sample data («عينة» / "sample"); no real tender file is read.

    QSONE_REAL_MODELS=/path/to/models node scripts/python.mjs -m pytest \
        core/tests/test_real_models.py -v -s
"""

import hashlib
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from qsone.meaning.download import default_client, download, folder, installed
from qsone.meaning.host import HostedEmbedder, ModelHost
from qsone.meaning.manifest import EMBEDDER, MODELS
from qsone.records.files import add_file
from qsone.records.project import Records
from qsone.records.search import index_vectors, search
from tests.samples import sample_pdf, sample_xlsx

pytestmark = pytest.mark.skipif(
    not os.environ.get("QSONE_REAL_MODELS"),
    reason="opt-in: set QSONE_REAL_MODELS to a models folder",
)

GB = 1_000_000_000
CORE = Path(__file__).resolve().parents[1]
BOQ_ROWS = [
    ["03/02", "خرسانه مسلّحه للأسقف - عينة", "م3", 120],
    ["03/20", "خرسانة عادية للأرضيات - عينة", "م3", 40],
    ["05/01", "عزل الرطوبة للأساسات بالبيتومين الساخن - عينة", "م2", 300],
    ["08/22", "بردورة خرسانية - عينة", "م.ط", 519],
    ["09/01", "حفر للأساسات - عينة", "م3", 75],
]
# An English specification with no word about waterproofing, so the Arabic row is the only answer.
SPEC_PAGES = [
    ["Section 03 Concrete - sample", "Plain concrete for blinding shall be grade C15."],
    ["Section 05 Steel - sample", "High-yield steel reinforcement bars to BS 4449 grade B500."],
    ["Section 09 Painting - sample", "Two coats of emulsion paint on plastered walls."],
]
# Three Arabic and three English QS lines, each the other's translation.
ARABIC = ["خرسانة مسلحة للأسقف", "عزل الرطوبة للأساسات بالبيتومين الساخن", "حفر للأساسات"]
ENGLISH = [
    "reinforced concrete for slabs",
    "damp proofing of foundations with hot bitumen",
    "excavation for foundations",
]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while piece := f.read(1 << 20):
            h.update(piece)
    return h.hexdigest()


@pytest.fixture(scope="module")
def models() -> Path:
    """The models folder: downloaded once with the real client, then every file rehashed in full."""
    root = Path(os.environ["QSONE_REAL_MODELS"])
    if not installed(MODELS, root):
        shown = [0.0]

        def progress(done: int, total: int) -> None:
            if time.monotonic() - shown[0] > 5 or done == total:
                shown[0] = time.monotonic()
                print(f"\ndownloading the search model: {done / 1e6:.0f} of {total / 1e6:.0f} MB")

        with default_client() as client:
            download(MODELS, root, client=client, stop=threading.Event(), on_progress=progress)
    for spec in MODELS:
        for f in spec.files:
            assert _sha256(folder(spec, root) / f.path) == f.sha256, f"{spec.id}/{f.path}"
    return root


@pytest.fixture
def rec(tmp_path):
    rec = Records.create(tmp_path / "p", name="تجربة - عينة", actor="engineer")
    yield rec
    rec.close()


def _load(models: Path, threads: int | None = None):
    from qsone.meaning.onnx import OnnxEmbedder

    return OnnxEmbedder.load(EMBEDDER, folder(EMBEDDER, models), threads=threads)


def test_files_match_their_pins(models):
    """The fixture rehashed both files in full; the folder is also marked installed."""
    assert installed(MODELS, models) and not list(models.rglob("*.part"))


def test_meaning_crosses_languages(models):
    """A line's nearest passage in the other language is mostly its translation. e5-small crosses
    languages weakly by vectors alone (spike §4), which is why the agents search in both: here
    "excavation for foundations" lands nearer «خرسانة مسلحة للأسقف» than «حفر للأساسات»."""
    import numpy as np

    emb = _load(models)
    nearest = {}
    for queries, passages in ((ARABIC, ENGLISH), (ENGLISH, ARABIC)):
        p = np.array(emb.embed_documents(passages))
        cosines = np.array([emb.embed_query(q) for q in queries]) @ p.T
        print("\n" + "\n".join(" ".join(f"{c:.3f}" for c in row) for row in cosines))
        nearest[queries[0]] = list(cosines.argmax(axis=1))
        assert p.shape == (3, 384) and np.allclose(np.linalg.norm(p, axis=1), 1.0)
        assert np.trace(cosines) / 3 > (cosines.sum() - np.trace(cosines)) / 6  # pairs are nearer
    assert nearest[ARABIC[0]] == [
        0,
        1,
        2,
    ]  # «خرسانة مسلحة للأسقف» → "reinforced concrete for slabs"
    assert nearest[ENGLISH[0]][:2] == [0, 1]


def test_hybrid_search_end_to_end(models, rec):
    """As the agents search: the question in both languages."""
    add_file(rec, "جدول الكميات - عينة.xlsx", sample_xlsx({"BOQ": BOQ_ROWS}), actor="engineer")
    add_file(rec, "Specification - sample.pdf", sample_pdf(SPEC_PAGES), actor="engineer")
    host = ModelHost(
        {"embedder": lambda: _load(models)}, {"embedder": EMBEDDER.ram_bytes}, ram=8 * GB
    )
    embedder = HostedEmbedder(host, EMBEDDER)
    try:
        assert index_vectors(rec, embedder) > 0

        q, also = "waterproofing for the foundations", ["عزل الرطوبة للأساسات"]
        r = search(rec, q, also=also, embedder=embedder)
        assert r.mode == "hybrid"
        row3 = next(h for h in r.hits if h.locator == {"sheet": "BOQ", "row": 3})
        assert r.hits.index(row3) < 3 and "meaning" in row3.found_by

        q, also = "مواصفات حديد التسليح", ["steel reinforcement bars specification"]
        back = search(rec, q, also=also, embedder=embedder)
        assert {"page": 2} in [h.locator for h in back.hits[:3]]  # Arabic finds English
    finally:
        host.unload_all()


# Sample chunks shaped like real ones: short BOQ rows and specification paragraphs up to 800 chars.
_ROWS = [
    "{n:02}/01 | خرسانة مسلحة للأسقف والكمرات بإجهاد ٣٠٠ كجم/سم٢ - عينة | م3 | {n}",
    "{n:02}/02 | Supply and fix high-yield steel reinforcement bars, sample item {n} | ton | {n}",
    "{n:02}/03 | عزل الرطوبة للأساسات بطبقتين من البيتومين الساخن - عينة | م2 | {n}",
    "{n:02}/04 | Ceramic floor tiles 60x60 cm on cement mortar bed, sample {n} | m2 | {n}",
]
_PARAGRAPH = (
    "Clause {n} - sample. The Contractor shall submit samples of all materials for the Engineer's "
    "approval before ordering. Concrete shall be placed within 90 minutes of mixing and compacted "
    "with poker vibrators; no water shall be added on site. "
    "البند {n} - عينة: على المقاول تقديم عينات من جميع المواد لاعتماد المهندس قبل التوريد، ويتم صب "
    "الخرسانة خلال تسعين دقيقة من الخلط مع الدمك بالهزاز الميكانيكي، "
    "ولا يسمح بإضافة مياه في الموقع. "
)


def sample_chunks(count: int) -> list[str]:
    out = []
    for n in range(count):
        if n % 2:
            out.append(_ROWS[n % 4].format(n=n))
        else:
            out.append((_PARAGRAPH.format(n=n) * 2)[: 300 + (n * 37) % 500])
    return out


def _rss() -> int | None:
    """Resident memory now, Linux only."""
    try:
        pages = int(Path("/proc/self/statm").read_text().split()[1])
    except OSError:
        return None
    return pages * os.sysconf("SC_PAGE_SIZE")


def _peak() -> int:
    import resource

    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak if sys.platform == "darwin" else peak * 1024  # bytes on macOS, KiB on Linux


def _measure(root: str) -> None:
    """Runs in a child process, so the model's peak is its own. Prints one JSON line."""
    baseline = _rss() or _peak()
    timings: dict[str, float] = {}

    def load():
        started = time.perf_counter()
        loaded = _load(Path(root), threads=4)
        timings["load_s"] = time.perf_counter() - started
        return loaded

    host = ModelHost({"embedder": load}, {"embedder": EMBEDDER.ram_bytes}, ram=8 * GB)
    chunks = sample_chunks(200)
    hosted = HostedEmbedder(host, EMBEDDER)
    hosted.embed_query("warm up")
    started = time.perf_counter()
    hosted.embed_documents(chunks)
    timings["index_s_per_1000"] = (time.perf_counter() - started) * 1000 / len(chunks)
    started = time.perf_counter()
    for q in ("damp proofing of foundations", "حديد التسليح", "concrete grade C30"):
        hosted.embed_query(q)
    timings["query_ms"] = (time.perf_counter() - started) * 1000 / 3
    loaded = _rss()
    host.unload_all()
    after = _rss()
    print(
        json.dumps(
            {"baseline": baseline, "peak": _peak(), "loaded": loaded, "after": after} | timings
        )
    )


def _child(models: Path) -> dict:
    out = subprocess.run(
        [
            sys.executable,
            "-c",
            f"from tests.test_real_models import _measure; _measure({str(models)!r})",
        ],
        capture_output=True,
        text=True,
        cwd=CORE,
        check=True,
    )
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_memory_and_speed(models):
    if sys.platform == "win32":
        pytest.skip("peak memory is read with the resource module")
    m = _child(models)
    over = m["peak"] - m["baseline"]
    shown = {k: round(v, 2) for k, v in m.items() if k.endswith(("_s", "_ms", "_1000"))}
    print(f"\nembedder: peak {over / GB:.2f} GB over the baseline; {shown}")
    if m["loaded"] is not None:
        print(
            f"embedder: resident {m['loaded'] / GB:.2f} GB loaded, {m['after'] / GB:.2f} GB "
            f"after unloading (baseline {m['baseline'] / GB:.2f} GB)"
        )
    assert over < EMBEDDER.ram_bytes
    if m["loaded"] is not None:  # Linux: unloading gives the memory back to the system
        assert m["after"] - m["baseline"] < 0.15 * GB < m["loaded"] - m["after"]
