"""The search bench: real QS questions over real tender files (search_bench.json), in Arabic and
English, scored by hit@5 and MRR for words only, meaning only and both fused.

The files live in the private docs repo, so the bench runs only where they are: QSONE_TEST_FILES
names the folder (default: docs/test-files in the main checkout). Meaning needs the real search
model too (QSONE_REAL_MODELS, as in test_real_models.py). Run it alone, with no other heavy work:
reading the files and embedding about 1,900 passages takes about a minute on a laptop.

    QSONE_REAL_MODELS=/path/to/models node scripts/python.mjs -m tests.search_bench
"""

import argparse
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from qsone.records import arabic, qs_terms, search
from qsone.records.files import add_file
from qsone.records.project import Records

CORE = Path(__file__).resolve().parents[1]
FIXTURE = Path(__file__).with_name("search_bench.json")
K = 10  # MRR looks this far; hit@5 the first five
METHODS = ("words", "meaning", "fused", "agent")  # agent: fused, with the other language in `also`
CATEGORIES = ("ar→en", "en→ar", "ar→ar", "en→en")


def load() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_files() -> Path | None:
    """QSONE_TEST_FILES, or docs/test-files of the main checkout (a worktree has no docs/)."""
    if os.environ.get("QSONE_TEST_FILES"):
        return Path(os.environ["QSONE_TEST_FILES"])
    try:
        common = subprocess.run(
            ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
            cwd=CORE,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None
    folder = Path(common).parent / "docs" / "test-files"
    return folder if folder.is_dir() else None


def build(
    root: Path, files: Path, embedder: search.Embedder | None = None, *, together: bool = False
) -> dict[str, Records]:
    """One project per tender, as an engineer keeps them (or all files in one, "all", with
    `together`), each made in `root`, its files read and embedded when `embedder` is given."""
    bench = load()
    projects = {"all": list(bench["files"])} if together else bench["projects"]
    out = {}
    for name, keys in projects.items():
        rec = out[name] = Records.create(root / name, name=f"search bench {name}", actor="engineer")
        for key in keys:
            path = bench["files"][key]
            add_file(rec, Path(path).name, (files / path).read_bytes(), actor="engineer")
        if embedder is not None:
            search.index_vectors(rec, embedder)
    return out


@dataclass(frozen=True)
class Query:
    id: str
    lang: str  # the language it is asked in
    text: str
    other: str  # the same question in the other language, as the agent writes it in `also`
    category: str
    project: str
    file: str
    where: frozenset  # pages, or (sheet, row) pairs

    def answers(self, hit: search.Hit) -> bool:
        if hit.file_name != self.file:
            return False
        loc = hit.locator
        return (loc.get("page") if "page" in loc else (loc.get("sheet"), loc.get("row"))) in (
            self.where
        )


def queries() -> list[Query]:
    bench = load()
    project = {key: name for name, keys in bench["projects"].items() for key in keys}
    out = []
    for c in bench["concepts"]:
        target = bench["languages"][c["file"]]
        where = frozenset(c["pages"]) if "pages" in c else frozenset(map(tuple, c["rows"]))
        name = Path(bench["files"][c["file"]]).name
        for lang, other in (("ar", "en"), ("en", "ar")):
            category = f"{lang}→{target}"
            out.append(
                Query(c["id"], lang, c[lang], c[other], category, project[c["file"]], name, where)
            )
    return out


def _meaning_only(rec: Records, q: Query, embedder: search.Embedder) -> list[search.Hit]:
    """The meaning lists alone, for the same texts the fused search embeds."""
    plan = search._plan([q.text])
    texts = [(t, 1.0, None) for t in plan.typed]
    texts += [(t, search.TERMS_WEIGHT, qs_terms.language(t)) for t in plan.other]
    with rec.read() as conn:
        lists = [
            search._meaning(conn, embedder.embed_query(arabic.clean(t)), embedder.dims, False, lang)
            for t, _, lang in texts
        ]
        fused = search.rrf(lists, weights=[w for _, w, _ in texts])[:K]
        return search._hits(conn, fused, {i: ("meaning",) for i, _ in fused})


def ranked(rec: Records, q: Query, method: str, embedder: search.Embedder | None):
    if method == "words":
        return search.search(rec, q.text, k=K).hits
    if method == "meaning":
        return _meaning_only(rec, q, embedder)
    also = (q.other,) if method == "agent" else ()
    return search.search(rec, q.text, also=also, k=K, embedder=embedder).hits


def rank(q: Query, hits: list[search.Hit]) -> int | None:
    """1-based rank of the first hit that answers, within K."""
    return next((n for n, h in enumerate(hits[:K], 1) if q.answers(h)), None)


def score(ranks: list[int | None]) -> tuple[float, float]:
    """(hit@5, MRR@10)."""
    if not ranks:
        return 0.0, 0.0
    hit5 = sum(1 for r in ranks if r is not None and r <= 5) / len(ranks)
    mrr = sum(1 / r for r in ranks if r is not None) / len(ranks)
    return hit5, mrr


def _ranks(recs: dict[str, Records], method: str, embedder) -> list[tuple[Query, int | None]]:
    out = []
    for q in queries():
        rec = recs.get(q.project) or recs["all"]
        out.append((q, rank(q, ranked(rec, q, method, embedder))))
    return out


def run(
    recs: dict[str, Records], embedder: search.Embedder | None, methods=METHODS
) -> dict[str, dict[str, tuple[float, float, int]]]:
    """{method: {category: (hit@5, MRR, queries)}}; meaning methods need `embedder`."""
    out = {}
    for method in methods:
        if method != "words" and embedder is None:
            continue
        by: dict[str, list] = {}
        for q, r in _ranks(recs, method, embedder):
            by.setdefault(q.category, []).append(r)
        out[method] = {c: (*score(by[c]), len(by[c])) for c in CATEGORIES if c in by}
    return out


def misses(recs: dict[str, Records], embedder, method: str) -> list[tuple[Query, int | None]]:
    """The queries whose answer is not in the first five, with its rank."""
    return [(q, r) for q, r in _ranks(recs, method, embedder) if r is None or r > 5]


def table(result: dict) -> str:
    lines = [f"{'method':8} " + " ".join(f"{c:>15}" for c in CATEGORIES)]
    for method, cats in result.items():
        cells = [
            f"{cats[c][0]:.2f} / {cats[c][1]:.2f}".rjust(15) if c in cats else " " * 15
            for c in CATEGORIES
        ]
        lines.append(f"{method:8} " + " ".join(cells))
    return "\n".join(lines) + "\n(hit@5 / MRR@10)"


def load_embedder(models: Path) -> search.Embedder:
    from qsone.meaning.download import folder
    from qsone.meaning.manifest import EMBEDDER
    from qsone.meaning.onnx import OnnxEmbedder

    return OnnxEmbedder.load(EMBEDDER, folder(EMBEDDER, models))


def main() -> None:
    import tempfile

    import keyring

    from tests.conftest import MemoryKeyring

    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--models", default=os.environ.get("QSONE_REAL_MODELS"))
    parser.add_argument("--misses", action="store_true", help="list the queries missed")
    parser.add_argument("--together", action="store_true", help="all files in one project")
    args = parser.parse_args()
    files = test_files()
    if files is None:
        raise SystemExit("no test files: set QSONE_TEST_FILES")
    keyring.set_keyring(MemoryKeyring())  # the bench project's key never reaches the system
    embedder = load_embedder(Path(args.models)) if args.models else None
    with tempfile.TemporaryDirectory(prefix="qsone-search-bench-") as tmp:
        recs = build(Path(tmp), files, embedder, together=args.together)
        try:
            print(table(run(recs, embedder)))
            if args.misses:
                for q, r in misses(recs, embedder, "fused" if embedder else "words"):
                    print(f"{q.category} {q.id:22} rank {r}: {q.text}")
        finally:
            for rec in recs.values():
                rec.close()


if __name__ == "__main__":
    main()
