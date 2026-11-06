"""Search in one project. Exact mode for codes and numbers; otherwise words and meaning lists,
fused by reciprocal rank fusion (RRF); no reranker (5 Nov 2026).

The embedding model stays behind the `Embedder` interface (meaning/onnx.py: multilingual-e5-small).
`arabic.normalise` runs exactly once on any text, on the index side and on the query side (its
light stemmer is not idempotent)."""

import json
import re
import struct
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

from qsone.records import arabic, qs_terms
from qsone.records.project import Records

LIST_SIZE = 50  # each words or meaning list
# A QS term's other names were written for it (qs_terms), so the lists they make weigh more than
# the words as typed: on the search bench (tests/search_bench.py) 1.5 brought Arabic questions
# to English files without losing same-language answers.
TERMS_WEIGHT = 1.5
ACTOR = "One"  # index upkeep changes no project data, so it writes no audit rows


class Embedder(Protocol):
    name: str  # model id and version, kept in meta
    dims: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...


Mode = Literal["auto", "exact", "meaning"]


@dataclass(frozen=True)
class Hit:
    chunk_id: int
    file_id: str
    file_name: str
    locator: dict
    text: str
    score: float  # exact: -bm25; hybrid: RRF
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


def rrf(
    lists: list[list[int]], k: int = 60, weights: Sequence[float] | None = None
) -> list[tuple[int, float]]:
    """Reciprocal rank fusion, best first; ties go to the lower chunk id. Each list counts
    once, or `weights[i]` times."""
    scores: dict[int, float] = {}
    for n, ids in enumerate(lists):
        weight = 1.0 if weights is None else weights[n]
        for rank, chunk_id in enumerate(ids, 1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + weight / (k + rank)
    return sorted(scores.items(), key=lambda s: (-s[1], s[0]))


INDEX_VERSION = "2"


def _index_table(conn):
    conn.execute(
        "CREATE TABLE IF NOT EXISTS search_text (chunk_id INTEGER PRIMARY KEY "
        "REFERENCES chunks(id) ON DELETE CASCADE, text TEXT NOT NULL)"
    )


def _file_text(conn, file_id):
    rows = conn.execute(
        "SELECT id, locator, text FROM chunks WHERE file_id=?", (file_id,)
    ).fetchall()
    pages = conn.execute("SELECT pages FROM files WHERE id=?", (file_id,)).fetchone()[0] or 0
    repeated = set()
    if pages >= 4:
        seen = {}
        for _, locator, text in rows:
            page = json.loads(locator).get("page")
            if page is None:
                continue
            for line in text.splitlines():
                key = re.sub(r"\d+", "#", " ".join(arabic.clean(line).split())).casefold()
                if key:
                    seen.setdefault(key, set()).add(page)
        repeated = {key for key, places in seen.items() if len(places) * 2 >= pages}
    return [
        (
            i,
            "\n".join(
                line
                for line in text.splitlines()
                if re.sub(r"\d+", "#", " ".join(arabic.clean(line).split())).casefold()
                not in repeated
            ).strip(),
        )
        for i, _, text in rows
    ]


def index_words(conn, chunks: Iterable[tuple[int, str]]) -> None:
    """Refresh affected files' index text; originals remain untouched, including on OCR updates."""
    _index_table(conn)
    files = set()
    supplied = dict(chunks)
    for chunk_id in supplied:
        row = conn.execute("SELECT file_id FROM chunks WHERE id=?", (chunk_id,)).fetchone()
        if row:
            files.add(row[0])
    has_vectors = conn.execute("SELECT 1 FROM sqlite_master WHERE name='chunk_vectors'").fetchone()
    for file_id in files:
        pages = conn.execute("SELECT pages FROM files WHERE id=?", (file_id,)).fetchone()[0] or 0
        rows = (
            _file_text(conn, file_id)
            if pages >= 4
            else [
                (i, text)
                for i, text in supplied.items()
                if conn.execute("SELECT file_id FROM chunks WHERE id=?", (i,)).fetchone()[0]
                == file_id
            ]
        )
        for chunk_id, text in rows:
            old = conn.execute(
                "SELECT text FROM search_text WHERE chunk_id=?", (chunk_id,)
            ).fetchone()
            conn.execute("DELETE FROM chunks_fts WHERE rowid=?", (chunk_id,))
            conn.execute("DELETE FROM search_text WHERE chunk_id=?", (chunk_id,))
            if has_vectors and (old is None or old[0] != text):
                conn.execute("DELETE FROM chunk_vectors WHERE chunk_id=?", (chunk_id,))
            if text:
                conn.execute("INSERT INTO search_text VALUES (?,?)", (chunk_id, text))
                conn.execute(
                    "INSERT INTO chunks_fts(rowid,norm) VALUES (?,?)",
                    (chunk_id, arabic.normalise(text)),
                )


def ensure_index(rec: Records) -> None:
    """Rebuild index-only text once, without extracting files again."""
    version = str(arabic.NORMALISER_VERSION)
    meta = rec.meta()
    if (
        meta.get("normaliser_version") == version
        and meta.get("search_index_version") == INDEX_VERSION
    ):
        return
    with rec.write(ACTOR, upkeep=True) as conn:
        conn.execute("INSERT INTO chunks_fts(chunks_fts) VALUES ('delete-all')")
        conn.execute("DROP TABLE IF EXISTS chunk_vectors")
        conn.execute("DELETE FROM meta WHERE key IN ('embed_model', 'embed_dims')")
        index_words(conn, conn.execute("SELECT id, text FROM chunks").fetchall())
        rec.set_meta(conn, "normaliser_version", version)
        rec.set_meta(conn, "search_index_version", INDEX_VERSION)


def _vectors_ready(conn, embedder: Embedder) -> bool:
    if conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'chunk_vectors'").fetchone() is None:
        return False
    meta = dict(conn.execute("SELECT key, value FROM meta WHERE key LIKE 'embed_%'"))
    return meta.get("embed_model") == embedder.name and meta.get("embed_dims") == str(embedder.dims)


def drop_stale_vectors(rec: Records, embedder: Embedder) -> bool:
    """Drops the vectors another model or size made, as the word index is rebuilt after a
    normaliser change (decisions §14.11); `index_vectors` then embeds every chunk again. Word
    search works all the while. True when it dropped them."""
    with rec.read() as conn:
        has = conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'chunk_vectors'").fetchone()
        if has is None or _vectors_ready(conn, embedder):
            return False
    with rec.write(ACTOR, upkeep=True) as conn:
        conn.execute("DROP TABLE IF EXISTS chunk_vectors")
        conn.execute("DELETE FROM meta WHERE key IN ('embed_model', 'embed_dims')")
    # Project files keep auto_vacuum off (0), so there is no incremental vacuum to run: the freed
    # pages stay in the file and the new, smaller vectors fill them.
    return True


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
    ensure_index(rec)
    dims = int(embedder.dims)
    with rec.write(ACTOR, upkeep=True) as conn:
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
                "SELECT chunk_id, text FROM search_text WHERE chunk_id > ?"
                " AND chunk_id NOT IN (SELECT chunk_id FROM chunk_vectors) "
                "ORDER BY chunk_id LIMIT ?",
                (last, batch),
            ).fetchall()
        if not todo:
            return done
        vectors = embedder.embed_documents([arabic.clean(text) for _, text in todo])
        with rec.write(ACTOR, upkeep=True) as conn:
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
    with rec.write(ACTOR, upkeep=True) as conn:
        _index_table(conn)
        (chunks,) = conn.execute("SELECT count(*) FROM search_text").fetchone()
        if not _vectors_ready(conn, embedder):
            return 0, chunks
        (vectors,) = conn.execute("SELECT count(*) FROM chunk_vectors").fetchone()
    return vectors, chunks


def _words(
    conn, match: str, include_old: bool, limit: int, file_ids=None
) -> list[tuple[int, float]]:
    rows = conn.execute(
        "SELECT c.id, bm25(chunks_fts), c.file_id, c.locator FROM chunks_fts"
        " JOIN chunks c ON c.id = chunks_fts.rowid JOIN files f ON f.id = c.file_id"
        " WHERE chunks_fts MATCH ? AND (? OR f.valid_until IS NULL)"
        " ORDER BY bm25(chunks_fts), c.id",
        (match, include_old),
    )
    found, seen = [], set()
    for chunk_id, score, file_id, locator in rows:
        if file_ids is not None and file_id not in file_ids:
            continue
        key = _place_key(chunk_id, file_id, json.loads(locator))
        if key in seen:
            continue
        seen.add(key)
        found.append((chunk_id, -score))
        if len(found) >= limit:
            break
    return found


def _meaning(
    conn,
    vector: list[float],
    dims: int,
    include_old: bool,
    language: str | None = None,
    file_ids=None,
) -> list[int]:
    """Top KNN first, then only chunks of current files (unless `include_old`) and, with
    `language`, only chunks written in it. MATERIALIZED keeps the KNN apart, as vec0 refuses any
    other ORDER BY term in its own query."""
    (total,) = conn.execute("SELECT count(*) FROM chunk_vectors").fetchone()
    candidates = min(LIST_SIZE, total)
    while candidates:
        if candidates > 4096:  # vec0's KNN ceiling; keep looking beyond dense/old pages
            candidates = total
            rows = conn.execute(
                "SELECT v.chunk_id, c.text, c.file_id, c.locator FROM chunk_vectors v"
                " JOIN chunks c ON c.id = v.chunk_id JOIN files f ON f.id = c.file_id"
                " WHERE ? OR f.valid_until IS NULL"
                " ORDER BY vec_distance_cosine(v.embedding, ?), v.chunk_id",
                (include_old, _pack(vector, dims)),
            )
        else:
            rows = conn.execute(
                "WITH knn AS MATERIALIZED (SELECT chunk_id, distance FROM chunk_vectors"
                " WHERE embedding MATCH ? AND k = ?)"
                " SELECT knn.chunk_id, c.text, c.file_id, c.locator FROM knn"
                " JOIN chunks c ON c.id = knn.chunk_id"
                " JOIN files f ON f.id = c.file_id WHERE ? OR f.valid_until IS NULL"
                " ORDER BY knn.distance, knn.chunk_id",
                (_pack(vector, dims), candidates, include_old),
            )
        found, seen = [], set()
        for i, text, file_id, locator in rows:
            if file_ids is not None and file_id not in file_ids:
                continue
            if language is not None and qs_terms.language(text) != language:
                continue
            key = _place_key(i, file_id, json.loads(locator))
            if key not in seen:
                seen.add(key)
                found.append(i)
            if len(found) == LIST_SIZE:
                return found
        if candidates == total:
            return found
        candidates = min(candidates * 2, total)
    return []


def _place_key(chunk_id: int, file_id: str, locator: dict) -> tuple:
    """PDF chunks share a page; spreadsheet rows and other passages stay separate."""
    if "page" in locator:
        return (file_id, locator["page"])
    return (chunk_id,)


def _distinct_hits(hits: list[Hit], k: int) -> list[Hit]:
    found, seen = [], set()
    for hit in hits:
        key = _place_key(hit.chunk_id, hit.file_id, hit.locator)
        if key not in seen:
            seen.add(key)
            found.append(hit)
    return found[:k]


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


@dataclass(frozen=True)
class _Plan:
    """What one search looks up (qs_terms for the QS terms the texts name)."""

    norms: list[str]  # the useful words of each text, for a words list each
    typed: list[str]  # the texts with words, to embed
    other: list[str]  # those terms in the language none of the texts is in, to embed
    phrases: list[str]  # every name of those terms, for one more words list


def _plan(texts: list[str]) -> _Plan:
    norms = [_useful(arabic.normalise(t)) for t in texts]
    other, phrases = qs_terms.expand(texts)
    return _Plan(norms, [t for t, n in zip(texts, norms, strict=True) if n], other, phrases)


def search(
    rec: Records,
    query: str,
    *,
    also: Sequence[str] = (),
    mode: Mode = "auto",
    k: int = 10,
    include_old: bool = False,
    embedder: Embedder | None = None,
    file_ids: set[str] | None = None,
) -> Result:
    """`also` holds the same question in other words (the agent writes the other language). The
    QS terms a query names are also looked up under their other names, Arabic and English."""
    texts = [query, *also]
    norms = [arabic.normalise(t) for t in texts]
    exact = mode == "exact" or (mode == "auto" and looks_exact(query))
    hybrid = "words" if embedder is None else "hybrid"
    if not norms[0]:
        return Result("exact" if exact else hybrid, [])

    if exact:
        with rec.read() as conn:
            scored = _words(conn, f'"{norms[0]}"', include_old, k, file_ids)
            if scored or mode == "exact":
                return Result("exact", _hits(conn, scored, {i: ("words",) for i, _ in scored}))

    plan = _plan(texts)
    # (vector, weight, language): a term list in the other language looks for passages in it
    # only; in a project without that language it would bring noise.
    vectors: list[tuple[list[float], float, str | None]] = []
    if embedder is not None:
        with rec.read() as conn:
            ready = _vectors_ready(conn, embedder)
        if ready:
            vectors = [(embedder.embed_query(arabic.clean(t)), 1.0, None) for t in plan.typed]
            vectors += [
                (embedder.embed_query(arabic.clean(t)), TERMS_WEIGHT, qs_terms.language(t))
                for t in plan.other
            ]

    matches = [(" OR ".join(_quoted(norm)), 1.0) for norm in plan.norms if norm]
    if plan.phrases:  # each name a phrase; its last word may go on ("payment" finds "payments")
        matches.append((" OR ".join(f'"{p}"*' for p in plan.phrases), TERMS_WEIGHT))
    # A complete phrase/near match outweighs isolated query words.
    matches += [(" AND ".join(_quoted(norm)), 2.0) for norm in plan.norms if len(norm.split()) > 1]
    lists: list[tuple[str, list[int], float]] = []
    with rec.read() as conn:
        for match, weight in matches:
            found = _words(conn, match, include_old, LIST_SIZE, file_ids)
            lists.append(("words", [chunk_id for chunk_id, _ in found], weight))
        for vector, weight, language in vectors:
            ids = (
                _meaning(conn, vector, int(embedder.dims), include_old, language)
                if file_ids is None
                else _meaning(conn, vector, int(embedder.dims), include_old, language, file_ids)
            )
            lists.append(("meaning", ids, weight))
        found_by: dict[int, tuple[str, ...]] = {}  # words lists come first, so ("words", "meaning")
        for kind, ids, _ in lists:
            for i in ids:
                if kind not in found_by.get(i, ()):
                    found_by[i] = (*found_by.get(i, ()), kind)
        fused = rrf([ids for _, ids, _ in lists], weights=[w for *_, w in lists])
        hits = _distinct_hits(
            [h for h in _hits(conn, fused, found_by) if file_ids is None or h.file_id in file_ids],
            k,
        )

    return Result(hybrid, hits[:k])
