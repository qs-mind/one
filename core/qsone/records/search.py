"""Search in one project. Exact mode for codes and numbers; otherwise words and meaning lists,
fused by reciprocal rank fusion (RRF) and, with a reranker, reordered at the top.

The embedding model and the reranker stay behind the `Embedder` and `Reranker` interfaces; the
real models come in Plan 2b. `arabic.normalise` runs exactly once on any text, on the index side
and on the query side (its light stemmer is not idempotent)."""

import json
import re
import struct
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, replace
from typing import Literal, Protocol

from qsone.records import arabic
from qsone.records.project import Records

LIST_SIZE = 50  # each words or meaning list
RERANK_TOP = 30
RERANK_SLICE = 4  # a newer rerank can stop an older one between slices
ACTOR = "One"  # index upkeep changes no project data, so it writes no audit rows


class Embedder(Protocol):
    name: str  # model id and version, kept in meta
    dims: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...


class Reranker(Protocol):
    name: str

    def rerank(self, query: str, texts: list[str]) -> list[float]: ...  # higher is better


Mode = Literal["auto", "exact", "meaning"]


class Superseded(Exception):
    """A newer rerank asked this one to stop."""


@dataclass(frozen=True)
class Hit:
    chunk_id: int
    file_id: str
    file_name: str
    locator: dict
    text: str
    score: float  # exact: -bm25; hybrid: RRF, or the reranker's score when it ran
    found_by: tuple[str, ...]  # "words", "meaning"


@dataclass(frozen=True)
class Result:
    mode: Literal["exact", "words", "hybrid"]
    hits: list[Hit]


_QUOTES = {'"': '"', "“": "”", "«": "»"}
_DIGIT = re.compile(r"\d")  # any decimal digit, Arabic-Indic too


def looks_exact(query: str) -> bool:
    """In quotes, or three words or fewer, one of them a code or number: a digit and at least
    two characters ("12", "03/02", "14.2"). A lone digit is no code."""
    s = query.strip()
    if len(s) >= 2 and _QUOTES.get(s[0]) == s[-1]:
        return True
    words = s.split()
    return 0 < len(words) <= 3 and any(len(w) >= 2 and _DIGIT.search(w) for w in words)


def _useful(norm: str) -> str:
    """The normalised words without lone digits: "1" is on every page of numbers, so it finds
    nothing worth showing."""
    return " ".join(w for w in norm.split() if not (len(w) == 1 and w.isdigit()))


def rrf(lists: list[list[int]], k: int = 60) -> list[tuple[int, float]]:
    """Reciprocal rank fusion, best first; ties go to the lower chunk id."""
    scores: dict[int, float] = {}
    for ids in lists:
        for rank, chunk_id in enumerate(ids, 1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1 / (k + rank)
    return sorted(scores.items(), key=lambda s: (-s[1], s[0]))


def index_words(conn, chunks: Iterable[tuple[int, str]]) -> None:
    """Adds (chunk id, display text) rows to the word index. Inside `Records.write`."""
    conn.executemany(
        "INSERT INTO chunks_fts(rowid, norm) VALUES (?, ?)",
        ((chunk_id, arabic.normalise(text)) for chunk_id, text in chunks),
    )


def ensure_index(rec: Records) -> None:
    """Rebuilds the word index when it was made by another normaliser version."""
    version = str(arabic.NORMALISER_VERSION)
    if rec.meta().get("normaliser_version") == version:
        return
    with rec.write(ACTOR) as conn:
        conn.execute("INSERT INTO chunks_fts(chunks_fts) VALUES ('delete-all')")
        index_words(conn, conn.execute("SELECT id, text FROM chunks").fetchall())
        rec.set_meta(conn, "normaliser_version", version)


def _vectors_ready(conn, embedder: Embedder) -> bool:
    if conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'chunk_vectors'").fetchone() is None:
        return False
    meta = dict(conn.execute("SELECT key, value FROM meta WHERE key LIKE 'embed_%'"))
    return meta.get("embed_model") == embedder.name and meta.get("embed_dims") == str(embedder.dims)


def _pack(vector: list[float], dims: int) -> bytes:
    return struct.pack(f"{dims}f", *vector)


def index_vectors(
    rec: Records,
    embedder: Embedder,
    batch: int = 16,
    *,
    should_stop: Callable[[], bool] = lambda: False,
    progress: Callable[[int], None] = lambda done: None,
) -> int:
    """Embeds the chunks that have no vector yet; each batch is committed on its own, so a stopped
    run resumes where it left off. A new model or size rebuilds the table. `should_stop` is asked
    before each batch, `progress(done)` told after each commit. Returns how many."""
    dims = int(embedder.dims)
    with rec.write(ACTOR) as conn:
        if not _vectors_ready(conn, embedder):
            conn.execute("DROP TABLE IF EXISTS chunk_vectors")
            conn.execute(
                "CREATE VIRTUAL TABLE chunk_vectors USING vec0(chunk_id INTEGER PRIMARY KEY,"
                f" embedding float[{dims}] distance_metric=cosine)"
            )
            rec.set_meta(conn, "embed_model", embedder.name)
            rec.set_meta(conn, "embed_dims", str(dims))
    done, last = 0, 0
    while not should_stop():
        with rec.read() as conn:
            todo = conn.execute(
                "SELECT id, text FROM chunks WHERE id > ?"
                " AND id NOT IN (SELECT chunk_id FROM chunk_vectors) ORDER BY id LIMIT ?",
                (last, batch),
            ).fetchall()
        if not todo:
            return done
        vectors = embedder.embed_documents([arabic.clean(text) for _, text in todo])
        with rec.write(ACTOR) as conn:
            conn.executemany(
                "INSERT INTO chunk_vectors(chunk_id, embedding) VALUES (?, ?)",
                [(i, _pack(v, dims)) for (i, _), v in zip(todo, vectors, strict=True)],
            )
        done += len(todo)
        last = todo[-1][0]
        progress(done)
    return done


def vector_counts(rec: Records, embedder: Embedder) -> tuple[int, int]:
    """(chunks with a vector from this model, all chunks)."""
    with rec.read() as conn:
        (chunks,) = conn.execute("SELECT count(*) FROM chunks").fetchone()
        if not _vectors_ready(conn, embedder):
            return 0, chunks
        (vectors,) = conn.execute("SELECT count(*) FROM chunk_vectors").fetchone()
    return vectors, chunks


def _words(conn, match: str, include_old: bool, limit: int) -> list[tuple[int, float]]:
    rows = conn.execute(
        "SELECT c.id, bm25(chunks_fts) FROM chunks_fts"
        " JOIN chunks c ON c.id = chunks_fts.rowid JOIN files f ON f.id = c.file_id"
        " WHERE chunks_fts MATCH ? AND (? OR f.valid_until IS NULL)"
        " ORDER BY bm25(chunks_fts), c.id LIMIT ?",
        (match, include_old, limit),
    )
    return [(chunk_id, -score) for chunk_id, score in rows]


def _meaning(conn, vector: list[float], dims: int, include_old: bool) -> list[int]:
    """Top KNN first, then only chunks of current files (unless `include_old`). MATERIALIZED keeps
    the KNN apart, as vec0 refuses any other ORDER BY term in its own query."""
    rows = conn.execute(
        "WITH knn AS MATERIALIZED (SELECT chunk_id, distance FROM chunk_vectors"
        " WHERE embedding MATCH ? AND k = ?)"
        " SELECT knn.chunk_id FROM knn JOIN chunks c ON c.id = knn.chunk_id"
        " JOIN files f ON f.id = c.file_id WHERE ? OR f.valid_until IS NULL"
        " ORDER BY knn.distance, knn.chunk_id",
        (_pack(vector, dims), LIST_SIZE, include_old),
    )
    return [chunk_id for (chunk_id,) in rows]


def _hits(conn, scored: list[tuple[int, float]], found_by: dict[int, tuple[str, ...]]) -> list[Hit]:
    if not scored:
        return []
    ids = [chunk_id for chunk_id, _ in scored]
    rows = conn.execute(
        "SELECT c.id, c.file_id, f.name, c.locator, c.text FROM chunks c"
        f" JOIN files f ON f.id = c.file_id WHERE c.id IN ({','.join('?' * len(ids))})",
        ids,
    )
    found = {row[0]: row for row in rows}
    return [
        Hit(i, found[i][1], found[i][2], json.loads(found[i][3]), found[i][4], score, found_by[i])
        for i, score in scored
        if i in found
    ]


def _quoted(norm: str) -> list[str]:
    """Normalised text is `\\w+` tokens joined by spaces, so no quote can get inside a phrase and
    a query can never inject FTS5 syntax."""
    return [f'"{token}"' for token in norm.split()]


def search(
    rec: Records,
    query: str,
    *,
    also: Sequence[str] = (),
    mode: Mode = "auto",
    k: int = 10,
    include_old: bool = False,
    embedder: Embedder | None = None,
    reranker: Reranker | None = None,
) -> Result:
    """`also` holds the same question in other words (the agent writes the other language)."""
    texts = [query, *also]
    norms = [arabic.normalise(t) for t in texts]
    exact = mode == "exact" or (mode == "auto" and looks_exact(query))
    hybrid = "words" if embedder is None else "hybrid"
    if not norms[0]:
        return Result("exact" if exact else hybrid, [])

    if exact:
        with rec.read() as conn:
            scored = _words(conn, f'"{norms[0]}"', include_old, k)
            if scored or mode == "exact":
                return Result("exact", _hits(conn, scored, {i: ("words",) for i, _ in scored}))

    norms = [_useful(n) for n in norms]
    vectors = []
    if embedder is not None:
        with rec.read() as conn:
            ready = _vectors_ready(conn, embedder)
        if ready:
            vectors = [
                embedder.embed_query(arabic.clean(t))
                for t, n in zip(texts, norms, strict=True)
                if n
            ]

    lists: list[tuple[str, list[int]]] = []
    with rec.read() as conn:
        for norm in norms:
            if norm:
                found = _words(conn, " OR ".join(_quoted(norm)), include_old, LIST_SIZE)
                lists.append(("words", [chunk_id for chunk_id, _ in found]))
        for vector in vectors:
            lists.append(("meaning", _meaning(conn, vector, int(embedder.dims), include_old)))
        found_by: dict[int, tuple[str, ...]] = {}  # words lists come first, so ("words", "meaning")
        for kind, ids in lists:
            for i in ids:
                if kind not in found_by.get(i, ()):
                    found_by[i] = (*found_by.get(i, ()), kind)
        fused = rrf([ids for _, ids in lists])[: max(k, RERANK_TOP) if reranker else k]
        hits = _hits(conn, fused, found_by)

    if reranker is not None and hits:
        top, rest = hits[:RERANK_TOP], hits[RERANK_TOP:]
        hits = _reorder(top, reranker.rerank(query, [h.text for h in top])) + rest
    return Result(hybrid, hits[:k])


def _reorder(hits: list[Hit], scores: Sequence[float]) -> list[Hit]:
    """Best score first; the sort is stable, so ties keep the order they came in."""
    order = sorted(range(len(hits)), key=lambda i: -scores[i])
    return [replace(hits[i], score=float(scores[i])) for i in order]


def rerank_hits(
    rec: Records,
    query: str,
    chunk_ids: Sequence[int],
    reranker: Reranker,
    *,
    should_stop: Callable[[], bool] = lambda: False,
) -> list[Hit]:
    """The given chunks of this project in reranked order; unknown ids are dropped. The reranker
    runs on slices of `RERANK_SLICE`; `should_stop` before each slice raises `Superseded`."""
    ids = list(dict.fromkeys(chunk_ids))
    with rec.read() as conn:
        hits = _hits(conn, [(i, 0.0) for i in ids], dict.fromkeys(ids, ()))
    scores: list[float] = []
    for start in range(0, len(hits), RERANK_SLICE):
        if should_stop():
            raise Superseded
        scores += reranker.rerank(query, [h.text for h in hits[start : start + RERANK_SLICE]])
    return _reorder(hits, scores)
