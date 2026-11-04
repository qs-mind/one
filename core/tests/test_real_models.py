"""Opt-in: the real search models. Skipped unless QSONE_REAL_MODELS names a models folder.

The first run downloads the 1.17 GB of pinned files from huggingface.co into that folder (free);
later runs make no request. Run it alone, with no other heavy work: it peaks near 4 GB of RAM.
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
from qsone.meaning.host import HostedEmbedder, HostedReranker, ModelHost
from qsone.meaning.manifest import EMBEDDER, MODELS, RERANKER
from qsone.records.files import add_file
from qsone.records.project import Records
from qsone.records.search import index_vectors, rerank_hits, search
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
                print(f"\ndownloading the search models: {done / 1e6:.0f} of {total / 1e6:.0f} MB")

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


def _host(models: Path, seen: list) -> ModelHost:
    """An 8 GB laptop's host; `seen` records what was in memory each time a model loaded."""
    from qsone.meaning.onnx import OnnxEmbedder, OnnxReranker

    def loader(model, spec):
        def load():
            seen.append(host.loaded())
            return model.load(spec, folder(spec, models))

        return load

    host = ModelHost(
        {"embedder": loader(OnnxEmbedder, EMBEDDER), "reranker": loader(OnnxReranker, RERANKER)},
        {"embedder": EMBEDDER.ram_bytes, "reranker": RERANKER.ram_bytes},
        ram=8 * GB,
    )
    return host


def test_files_match_their_pins(models):
    """The fixture rehashed all four files in full; the folder is also marked installed."""
    assert installed(MODELS, models) and not list(models.rglob("*.part"))


def test_meaning_crosses_languages(models):
    import numpy as np

    from qsone.meaning.onnx import OnnxEmbedder

    emb = OnnxEmbedder.load(EMBEDDER, folder(EMBEDDER, models))
    docs = [
        "عزل الرطوبة للأساسات بالبيتومين الساخن - عينة",
        "خرسانة عادية للأرضيات - عينة",
        "Supply and fix high-yield steel reinforcement bars - sample",
    ]
    d = np.array(emb.embed_documents(docs))
    assert int(np.argmax(d @ np.array(emb.embed_query("damp proofing of foundations")))) == 0
    assert int(np.argmax(d @ np.array(emb.embed_query("حديد التسليح")))) == 2


def test_reranker_puts_the_answer_first(models):
    from qsone.meaning.onnx import OnnxReranker

    rr = OnnxReranker.load(RERANKER, folder(RERANKER, models))
    texts = [
        "Paint the steel doors with two coats of enamel - sample",
        "Line the water tank with a waterproof membrane - sample",
        "Lay ceramic floor tiles on cement mortar - sample",
    ]
    scores = rr.rerank("تبطين الخزان بغشاء عازل", texts)
    assert len(scores) == 3 and max(range(3), key=scores.__getitem__) == 1


def test_hybrid_search_end_to_end(models, rec):
    add_file(rec, "جدول الكميات - عينة.xlsx", sample_xlsx({"BOQ": BOQ_ROWS}), actor="engineer")
    add_file(rec, "Specification - sample.pdf", sample_pdf(SPEC_PAGES), actor="engineer")
    seen: list = []
    host = _host(models, seen)
    embedder, reranker = HostedEmbedder(host, EMBEDDER), HostedReranker(host, RERANKER)
    try:
        assert index_vectors(rec, embedder) > 0

        r = search(rec, "waterproofing for the foundations", k=30, embedder=embedder)
        assert r.mode == "hybrid"
        row3 = next(h for h in r.hits if h.locator == {"sheet": "BOQ", "row": 3})
        assert r.hits.index(row3) < 3 and "meaning" in row3.found_by

        back = search(rec, "مواصفات حديد التسليح", k=30, embedder=embedder)
        assert {"page": 2} in [
            h.locator for h in back.hits[:3]
        ]  # the reverse: Arabic finds English

        hits = rerank_hits(
            rec, "waterproofing for the foundations", [h.chunk_id for h in r.hits], reranker
        )
        assert hits[0].locator == {"sheet": "BOQ", "row": 3}
        assert all(len(loaded) == 0 for loaded in seen)  # each load found the other one gone
        assert len(host.loaded()) == 1
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


def _measure(kind: str, root: str) -> None:
    """Runs in a child process, so each model's peak is its own. Prints one JSON line."""
    baseline = _rss() or _peak()
    from qsone.meaning import onnx

    spec = EMBEDDER if kind == "embedder" else RERANKER
    model = onnx.OnnxEmbedder if kind == "embedder" else onnx.OnnxReranker
    timings: dict[str, float] = {}

    def load():
        started = time.perf_counter()
        loaded = model.load(spec, folder(spec, Path(root)), threads=4)
        timings["load_s"] = time.perf_counter() - started
        return loaded

    host = ModelHost({kind: load}, {kind: spec.ram_bytes}, ram=8 * GB)
    chunks = sample_chunks(200)
    if kind == "embedder":
        hosted = HostedEmbedder(host, spec)
        hosted.embed_query("warm up")
        started = time.perf_counter()
        hosted.embed_documents(chunks)
        timings["index_s_per_1000"] = (time.perf_counter() - started) * 1000 / len(chunks)
        started = time.perf_counter()
        for q in ("damp proofing of foundations", "حديد التسليح", "concrete grade C30"):
            hosted.embed_query(q)
        timings["query_ms"] = (time.perf_counter() - started) * 1000 / 3
    else:
        hosted = HostedReranker(host, spec)
        hosted.rerank("warm up", chunks[:4])
        started = time.perf_counter()
        hosted.rerank("عزل الرطوبة للأساسات", chunks[:30])
        timings["rerank_30_s"] = time.perf_counter() - started
    loaded = _rss()
    host.unload_all()
    after = _rss()
    print(
        json.dumps(
            {"baseline": baseline, "peak": _peak(), "loaded": loaded, "after": after} | timings
        )
    )


def _child(kind: str, models: Path) -> dict:
    out = subprocess.run(
        [
            sys.executable,
            "-c",
            f"from tests.test_real_models import _measure; _measure({kind!r}, {str(models)!r})",
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
    limits = {"embedder": 2.3 * GB, "reranker": 2.2 * GB}
    for kind in ("embedder", "reranker"):  # one model at a time, each in its own process
        m = _child(kind, models)
        over = m["peak"] - m["baseline"]
        shown = {k: round(v, 2) for k, v in m.items() if k.endswith(("_s", "_ms", "_1000"))}
        print(f"\n{kind}: peak {over / GB:.2f} GB over the baseline; {shown}")
        if m["loaded"] is not None:
            print(
                f"{kind}: resident {m['loaded'] / GB:.2f} GB loaded, {m['after'] / GB:.2f} GB "
                f"after unloading (baseline {m['baseline'] / GB:.2f} GB)"
            )
        assert over < limits[kind]
        if m["loaded"] is not None:  # Linux: unloading gives the memory back to the system
            assert m["after"] - m["baseline"] < 0.3 * GB < m["loaded"] - m["after"]
