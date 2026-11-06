"""The search bench as floors (tests/search_bench.py): the real tender files, so it runs only where
they are (the private docs repo); meaning also needs the real model (QSONE_REAL_MODELS). Measured
6 Nov 2026 (hit@5, one project per tender): words 0.90 / 0.87 / 1.00 / 0.95 and fused 1.00 / 0.87 /
1.00 / 0.95 for ar→en / en→ar / ar→ar / en→en; before the QS terms, fused was 0.15 / 0.40 / 1.00 /
0.90. A floor is a little under what was measured, so a change that loses answers fails here.

    QSONE_REAL_MODELS=/path/to/models node scripts/python.mjs -m pytest \
        core/tests/test_search_bench.py -v
"""

import os
from pathlib import Path

import keyring
import pytest

from qsone.records import search
from tests import search_bench as bench
from tests.conftest import MemoryKeyring

FILES = bench.test_files()
pytestmark = pytest.mark.skipif(FILES is None, reason="the tender files are not here")

WORDS_FLOOR = {"ar→en": 0.85, "en→ar": 0.8, "ar→ar": 0.95, "en→en": 0.9}
FUSED_FLOOR = {"ar→en": 0.9, "en→ar": 0.8, "ar→ar": 0.95, "en→en": 0.9}


@pytest.fixture(scope="module")
def recs(tmp_path_factory):
    previous = keyring.get_keyring()  # module scope: before the autouse memory key store
    keyring.set_keyring(MemoryKeyring())
    recs = bench.build(tmp_path_factory.mktemp("search-bench"), FILES)
    yield recs
    for rec in recs.values():
        rec.close()
    keyring.set_keyring(previous)


@pytest.fixture(scope="module")
def embedder(recs):
    if not os.environ.get("QSONE_REAL_MODELS"):
        pytest.skip("opt-in: set QSONE_REAL_MODELS to a models folder")
    emb = bench.load_embedder(Path(os.environ["QSONE_REAL_MODELS"]))
    for rec in recs.values():
        search.index_vectors(rec, emb)
    return emb


def test_the_bench_has_both_languages_both_ways():
    qs = bench.queries()
    assert len(qs) >= 30
    for category in bench.CATEGORIES:
        assert sum(q.category == category for q in qs) >= 10, category


def _hit5(result: dict, method: str) -> dict[str, float]:
    return {c: round(v[0], 2) for c, v in result[method].items()}


def test_words_floor(recs):
    got = _hit5(bench.run(recs, None, methods=("words",)), "words")
    assert all(got[c] >= floor for c, floor in WORDS_FLOOR.items()), got


def test_fused_floor(recs, embedder):
    got = _hit5(bench.run(recs, embedder, methods=("fused",)), "fused")
    assert all(got[c] >= floor for c, floor in FUSED_FLOOR.items()), got


@pytest.mark.parametrize("query", ["نسبة المحتجز من المستخلصات", "غرامة التأخير"])
def test_the_real_walk_questions_reach_page_58(recs, embedder, query):
    """The 6 Nov walk: neither question reached the Particular Conditions table on vol1 p58."""
    hits = search.search(recs["brissa"], query, embedder=embedder).hits[:5]
    assert ("brissa_vol1_bidding_conditions_fidic2017_pc.pdf", {"page": 58}) in [
        (h.file_name, h.locator) for h in hits
    ]
