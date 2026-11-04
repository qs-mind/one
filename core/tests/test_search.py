"""Search: exact mode for codes and numbers, words for Arabic spellings, meaning through the
Embedder interface (test doubles only, no model), RRF fusion and the Reranker interface."""

import pytest

from qsone.records.files import add_file
from qsone.records.project import Records
from qsone.records.search import ensure_index, index_vectors, looks_exact, rrf, search
from tests.doubles import ConceptEmbedder, PreferReranker
from tests.samples import sample_pdf, sample_xlsx


@pytest.fixture
def rec(tmp_path):
    rec = Records.create(tmp_path / "p", name="مشروع - عينة", actor="engineer")
    yield rec
    rec.close()


@pytest.fixture
def boq(rec):
    rows = [
        ["03/02", "خرسانه مسلّحه للأسقف", "م3", 120],
        ["03/20", "خرسانة عادية للأرضيات", "م3", 40],
        ["05/01", "عزل الرطوبة للأساسات", "م2", 300],
        ["08/22", "بردورة خرسانية", "م.ط", "٥١٩٣"],
    ]
    add_file(rec, "جدول الكميات - عينة.xlsx", sample_xlsx({"BOQ": rows}), actor="engineer")
    pdf = sample_pdf([["Sub-Clause 14.2 Advance Payment"]])
    add_file(rec, "Conditions - sample.pdf", pdf, actor="engineer")
    return rec


class FlatEmbedder:
    """Another model: other name, other size."""

    name = "test-flat-1"
    dims = 3

    def embed_documents(self, texts):
        return [[1.0, 0.0, 0.0] for _ in texts]

    def embed_query(self, text):
        return [1.0, 0.0, 0.0]


def test_codes_use_exact_mode(boq):
    r = search(boq, "03/02")
    assert r.mode == "exact"
    assert [h.locator for h in r.hits] == [{"sheet": "BOQ", "row": 1}]
    assert r.hits[0].file_name == "جدول الكميات - عينة.xlsx" and r.hits[0].found_by == ("words",)
    hit = search(boq, "Sub-Clause 14.2").hits[0]
    assert hit.locator == {"page": 1} and hit.file_name == "Conditions - sample.pdf"


def test_exact_mode_finding_nothing_falls_back_to_words(boq):
    r = search(boq, "خرسانة 99")
    assert r.mode == "words" and r.hits


def test_arabic_words_match_across_spellings(boq):
    r = search(boq, "الخرسانة المسلحة")
    assert r.mode == "words"
    assert r.hits[0].locator == {"sheet": "BOQ", "row": 1}
    assert r.hits[0].text == "03/02 | خرسانه مسلّحه للأسقف | م3 | 120"


def test_digits_match_both_ways(boq):
    assert [h.locator for h in search(boq, "5193").hits] == [{"sheet": "BOQ", "row": 4}]
    assert [h.locator for h in search(boq, "٥١٩٣").hits] == [{"sheet": "BOQ", "row": 4}]


def test_meaning_finds_the_other_language(boq):
    emb = ConceptEmbedder()
    assert index_vectors(boq, emb) == 5
    r = search(boq, "waterproofing for the foundations", embedder=emb)
    assert r.mode == "hybrid" and r.hits[0].locator == {"sheet": "BOQ", "row": 3}
    assert r.hits[0].found_by == ("meaning",)


def test_also_query_adds_a_words_list(boq):
    r = search(boq, "waterproofing", also=["عزل الرطوبة"])
    assert r.mode == "words"
    assert r.hits[0].locator == {"sheet": "BOQ", "row": 3} and r.hits[0].found_by == ("words",)


def test_words_and_meaning_together(boq):
    emb = ConceptEmbedder()
    index_vectors(boq, emb)
    r = search(boq, "waterproofing", also=["عزل الرطوبة"], embedder=emb)
    assert r.hits[0].locator == {"sheet": "BOQ", "row": 3}
    assert r.hits[0].found_by == ("words", "meaning")


def test_reranker_reorders_the_top(boq):
    assert search(boq, "خرسانة").hits[0].locator != {"sheet": "BOQ", "row": 2}
    r = search(boq, "خرسانة", reranker=PreferReranker("عادية"))
    assert r.hits[0].locator == {"sheet": "BOQ", "row": 2} and r.hits[0].score == 1.0


def test_k_limits_the_hits(boq):
    assert len(search(boq, "خرسانة", k=2).hits) == 2


def test_rrf_order_and_ties():
    assert rrf([[1, 2], [2, 3]]) == [(2, 1 / 62 + 1 / 61), (1, 1 / 61), (3, 1 / 62)]
    assert rrf([[5], [4]]) == [(4, 1 / 61), (5, 1 / 61)]  # a tie goes to the lower chunk id


def test_old_versions_hidden_by_default(rec):
    add_file(rec, "عينة.txt", "خرسانة قديمة".encode(), actor="engineer")
    add_file(rec, "عينة.txt", "حديد جديد".encode(), actor="engineer")
    assert search(rec, "قديمة").hits == []
    assert [h.text for h in search(rec, "قديمة", include_old=True).hits] == ["خرسانة قديمة"]
    assert search(rec, '"خرسانة قديمة"').hits == []
    assert search(rec, '"خرسانة قديمة"', include_old=True).hits


def test_old_versions_hidden_from_meaning_too(rec):
    emb = ConceptEmbedder()
    add_file(rec, "عينة.txt", "خرسانة قديمة".encode(), actor="engineer", embedder=emb)
    add_file(rec, "عينة.txt", "حديد جديد".encode(), actor="engineer", embedder=emb)
    assert [h.text for h in search(rec, "concrete", embedder=emb).hits] == ["حديد جديد"]
    found = search(rec, "concrete", embedder=emb, include_old=True).hits
    assert found[0].text == "خرسانة قديمة"


def test_index_rebuilt_when_normaliser_changes(boq):
    with boq.write("engineer") as c:
        c.execute("INSERT INTO chunks_fts(chunks_fts) VALUES ('delete-all')")
        boq.set_meta(c, "normaliser_version", "0")
    assert search(boq, "03/02").hits == []
    ensure_index(boq)
    assert boq.meta()["normaliser_version"] == "1"
    assert search(boq, "03/02").hits[0].locator == {"sheet": "BOQ", "row": 1}


def test_vectors_rebuilt_when_model_changes(boq):
    emb = ConceptEmbedder()
    assert index_vectors(boq, emb) == 5
    assert index_vectors(boq, emb) == 0  # resumable: only chunks without vectors
    assert index_vectors(boq, FlatEmbedder()) == 5
    meta = boq.meta()
    assert (meta["embed_model"], meta["embed_dims"]) == ("test-flat-1", "3")


def test_vectors_resume_after_a_failed_batch(boq):
    class Breaks(ConceptEmbedder):
        def embed_documents(self, texts):
            if self.calls == 1:
                raise RuntimeError("model stopped")
            return super().embed_documents(texts)

    with pytest.raises(RuntimeError):
        index_vectors(boq, Breaks(), batch=2)
    with boq.read() as c:
        assert c.execute("SELECT count(*) FROM chunk_vectors").fetchone()[0] == 2
    assert index_vectors(boq, ConceptEmbedder(), batch=2) == 3


def test_search_without_vectors_for_this_model_uses_words(boq):
    r = search(boq, "waterproofing", embedder=ConceptEmbedder())
    assert r.mode == "hybrid" and r.hits == []


def test_query_text_cannot_inject_fts_syntax(boq):
    for q in ['03" OR "05', "NEAR(خرسانة عزل)", "خرسانة*", '"', "AND OR NOT", "^03"]:
        search(boq, q)  # no FTS5 syntax error


def test_empty_query_gives_no_hits(boq):
    assert search(boq, "  ").hits == [] and search(boq, "؟!").hits == []


def test_looks_exact():
    assert looks_exact("03/02") and looks_exact("٥١٩٣ م.ط") and looks_exact('"خيش مقطرن"')
    assert looks_exact("«خيش مقطرن»")
    assert not looks_exact("bored piles 60 cm diameter with load tests")
    assert not looks_exact("خرسانة مسلحة")
