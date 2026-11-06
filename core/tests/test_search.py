"""Search: exact mode for codes and numbers, words for Arabic spellings, meaning through the
Embedder interface (test doubles only, no model), RRF fusion and dropping the vectors of an old
model."""

import pytest

from qsone.records.files import add_file
from qsone.records.project import Records
from qsone.records.search import (
    drop_stale_vectors,
    ensure_index,
    index_vectors,
    looks_exact,
    rrf,
    search,
    vector_counts,
)
from tests.doubles import ConceptEmbedder
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
    assert "meaning" in r.hits[0].found_by  # and words, through the QS terms (qs_terms)


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
    assert r.mode == "hybrid" and r.hits and all(h.found_by == ("words",) for h in r.hits)


def test_query_text_cannot_inject_fts_syntax(boq):
    for q in ['03" OR "05', "NEAR(خرسانة عزل)", "خرسانة*", '"', "AND OR NOT", "^03"]:
        search(boq, q)  # no FTS5 syntax error


def test_empty_query_gives_no_hits(boq):
    assert search(boq, "  ").hits == [] and search(boq, "؟!").hits == []


def test_looks_exact():
    assert looks_exact("03/02") and looks_exact("٥١٩٣ م.ط") and looks_exact('"خيش مقطرن"')
    assert looks_exact("«خيش مقطرن»")
    assert looks_exact("14.2") and looks_exact("12") and looks_exact('"1"')
    assert not looks_exact("bored piles 60 cm diameter with load tests")
    assert not looks_exact("خرسانة مسلحة")
    assert not looks_exact("1") and not looks_exact("١") and not looks_exact("خرسانة 1")


def test_a_lone_digit_finds_nothing(rec):
    # A page full of numbers is not an answer to "1": a lone digit is too common to search on.
    add_file(rec, "عينة.txt", "عدد 1 مفتاح 16 أمبير 1 أوتوماتيك".encode(), actor="engineer")
    assert search(rec, "1").hits == [] and search(rec, "١").hits == []
    assert search(rec, "1").mode == "words"
    assert search(rec, "مفتاح 1").hits  # the word still finds it
    assert search(rec, '"1"').mode == "exact" and search(rec, '"1"').hits  # quoted: asked for


def test_indexing_stops_between_batches_and_resumes(boq):
    emb = ConceptEmbedder()
    asked = []
    n = index_vectors(boq, emb, batch=2, should_stop=lambda: len(asked) > 0, progress=asked.append)
    assert n == 2 and asked == [2] and vector_counts(boq, emb) == (2, 5)
    assert index_vectors(boq, emb, batch=2) == 3 and vector_counts(boq, emb) == (5, 5)


def test_indexing_reports_the_running_count(boq):
    asked = []
    index_vectors(boq, ConceptEmbedder(), batch=2, progress=asked.append)
    assert asked == [2, 4, 5]


def test_counts_are_zero_for_another_model(boq):
    assert vector_counts(boq, ConceptEmbedder()) == (0, 5)  # no table yet
    index_vectors(boq, ConceptEmbedder())
    assert vector_counts(boq, FlatEmbedder()) == (0, 5)


def test_vectors_of_another_model_are_dropped_and_made_again(boq):
    old, new = FlatEmbedder(), ConceptEmbedder()
    assert drop_stale_vectors(boq, new) is False  # no table yet: nothing to drop
    index_vectors(boq, old)
    assert drop_stale_vectors(boq, old) is False  # its own vectors stay
    assert drop_stale_vectors(boq, new) is True
    assert not any(k.startswith("embed_") for k in boq.meta())
    with boq.read() as conn:
        assert (
            conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'chunk_vectors'").fetchone()
            is None
        )
    assert search(boq, "عزل", embedder=new).hits[0].locator == {"sheet": "BOQ", "row": 3}  # words
    assert vector_counts(boq, new) == (0, 5)
    assert index_vectors(boq, new) == 5 and vector_counts(boq, new) == (5, 5)
    assert boq.meta()["embed_dims"] == str(new.dims)


@pytest.fixture
def brissa(rec):
    """English conditions and an Arabic BOQ, shaped like the real ones (sample text)."""
    pages = [
        ["Percentage of Retention 14.3(iii) 10% of each payment - sample"],
        ["Delay damages for the Works 8.8 0.2% of the Contract Price per day - sample"],
        ["Section 09 Painting - sample", "Two coats of emulsion paint on plastered walls."],
        ["Bidder Technical Offer - sample", "The bidder shall submit his offer."],
    ]
    add_file(rec, "Conditions - sample.pdf", sample_pdf(pages), actor="engineer")
    rows = [["1", "غرامات التأخير ٠٫١٪ عن كل يوم - عينة"], ["2", "دهانات بلاستيك - عينة"]]
    add_file(rec, "شروط - عينة.xlsx", sample_xlsx({"شروط": rows}), actor="engineer")
    return rec


def test_an_arabic_question_finds_the_english_clause_by_its_qs_terms(brissa):
    """The real walk (6 Nov): «نسبة المحتجز من المستخلصات» never reached the retention table,
    «غرامة التأخير» found "Bidder Technical Offer" and "Painting". Words alone now find them."""
    hits = search(brissa, "نسبة المحتجز من المستخلصات").hits
    assert hits[0].locator == {"page": 1} and hits[0].file_name == "Conditions - sample.pdf"
    hits = search(brissa, "غرامة التأخير").hits
    assert {"page": 2} in [h.locator for h in hits[:2]]
    assert {"page": 4} not in [h.locator for h in hits] and {"page": 3} not in [
        h.locator for h in hits
    ]


def test_an_english_question_finds_the_arabic_row(brissa):
    hits = search(brissa, "delay damages").hits
    assert {"sheet": "شروط", "row": 1} in [h.locator for h in hits[:2]]


class Recording(ConceptEmbedder):
    def __init__(self):
        super().__init__()
        self.queries = []

    def embed_query(self, text):
        self.queries.append(text)
        return super().embed_query(text)


def test_meaning_also_embeds_the_terms_in_the_other_language(brissa):
    emb = Recording()
    index_vectors(brissa, emb)
    search(brissa, "نسبة المحتجز من المستخلصات", embedder=emb)
    assert emb.queries == ["نسبة المحتجز من المستخلصات", "retention, interim payment certificate"]
    emb.queries.clear()  # the agent wrote both languages: nothing more to translate
    search(brissa, "غرامة التأخير", also=["delay damages"], embedder=emb)
    assert emb.queries == ["غرامة التأخير", "delay damages"]


def test_queries_are_cleaned_as_passages_are(brissa):
    """Embedded queries get the same clean text as passages (the "query: " and "passage: "
    prefixes are the model's own, meaning/onnx.py)."""
    emb = Recording()
    index_vectors(brissa, emb)
    search(brissa, "غرامــة التأخير ١٤٫٣", embedder=emb)  # kashida, Arabic-Indic digits
    assert emb.queries[0] == "غرامة التأخير 14.3"


def test_weights_in_rrf():
    assert rrf([[1], [2]], weights=[1.0, 2.0]) == [(2, 2 / 61), (1, 1 / 61)]


@pytest.mark.parametrize(
    "mode, query, vectors",
    [
        ("exact", "retention", False),
        ("meaning", "retention", False),
        ("meaning", "unmatched", True),
        ("meaning", "retention", True),
    ],
)
@pytest.mark.parametrize("repeats", [60, 4100])
def test_repeated_pdf_pages_do_not_use_up_results(rec, mode, query, vectors, repeats):
    """Sample Brissa shape: p87 x60, p58 x2, p59 x2; fill the list with other pages."""
    import json

    from qsone.records.search import index_words

    f = add_file(rec, "Conditions sample.pdf", sample_pdf([["sample"]]), actor="engineer")
    with rec.write("engineer") as conn:
        conn.execute("DELETE FROM chunks_fts")
        conn.execute("DELETE FROM chunks")
        for seq, page in enumerate([87] * repeats + [58] * 2 + [59] * 2 + [60]):
            cur = conn.execute(
                "INSERT INTO chunks(file_id, seq, locator, text) VALUES (?, ?, ?, ?)",
                (f.id, seq, json.dumps({"page": page}), "retention sample"),
            )
            index_words(conn, [(cur.lastrowid, "retention sample")])
    # Same page number in another file must survive, as must separate spreadsheet rows.
    other = add_file(rec, "Other sample.pdf", sample_pdf([["retention sample"]]), actor="engineer")
    add_file(
        rec,
        "Rows sample.xlsx",
        sample_xlsx({"BOQ": [["retention sample"], ["retention sample"]]}),
        actor="engineer",
    )
    emb = FlatEmbedder() if vectors else None
    if emb:
        index_vectors(rec, emb)
    hits = search(rec, query, mode=mode, k=7, embedder=emb).hits
    assert len(hits) == 7
    pages = [(h.file_id, h.locator["page"]) for h in hits if "page" in h.locator]
    assert len(pages) == len(set(pages)) == 5
    assert (other.id, 1) in pages
    assert {(f.id, p) for p in (87, 58, 59, 60)} <= set(pages)
    assert len([h for h in hits if "row" in h.locator]) == 2
    with rec.read() as conn:
        best = conn.execute("SELECT min(id) FROM chunks WHERE file_id = ?", (f.id,)).fetchone()[0]
    assert next(h.chunk_id for h in hits if h.file_id == f.id and h.locator["page"] == 87) == best


def test_fusion_keeps_one_page_when_words_and_meaning_prefer_different_chunks(rec, monkeypatch):
    from qsone.records import search as searches

    f = add_file(
        rec,
        "Conditions sample.pdf",
        sample_pdf([["retention sample"], ["retention other sample"]]),
        actor="engineer",
    )
    with rec.write("engineer") as conn:
        second = conn.execute(
            "INSERT INTO chunks(file_id, seq, locator, text) VALUES (?, 2, ?, ?)",
            (f.id, '{"page": 1}', "another passage sample"),
        ).lastrowid
        searches.index_words(conn, [(second, "another passage sample")])
    emb = FlatEmbedder()
    index_vectors(rec, emb)
    # A semantic match to a different passage on the same page must not duplicate that page
    # after fusion. The more highly ranked word match keeps its actual passage and locator.
    monkeypatch.setattr(searches, "_meaning", lambda *args: [second])
    hits = search(rec, "retention", mode="meaning", k=2, embedder=emb).hits
    assert [h.locator for h in hits] == [{"page": 1}, {"page": 2}]
    assert hits[0].text == "retention sample"


def test_repeated_lines_are_index_only_and_footer_chunks_are_absent(rec):
    import json

    from qsone.records.search import index_words

    f = add_file(
        rec,
        "Tender sample.pdf",
        sample_pdf([[f"sample page {i}"] for i in range(6)]),
        actor="engineer",
    )
    original = {}
    with rec.write("engineer") as c:
        c.execute("DELETE FROM chunks_fts")
        c.execute("DELETE FROM chunks")
        for page in range(1, 7):
            footer = f"https://tenders.example/Print?TenderId=123 {page}/6"
            body = (
                "فتح العروض 16/04/1448" if page == 4 else f"sample unique section {chr(64 + page)}"
            )
            for text in (f"كراسة الشروط 9/3/26 صفحة {page}\n{body}", footer):
                i = c.execute(
                    "INSERT INTO chunks(file_id,seq,locator,text) VALUES (?,?,?,?)",
                    (f.id, len(original), json.dumps({"page": page}), text),
                ).lastrowid
                original[i] = text
        index_words(c, original.items())

    class Capture(FlatEmbedder):
        def embed_documents(self, texts):
            assert all("https" not in text and "كراسة" not in text for text in texts)
            return super().embed_documents(texts)

    emb = Capture()
    assert index_vectors(rec, emb) == 6
    assert search(rec, "فتح العروض", embedder=emb).hits[0].locator == {"page": 4}
    assert not search(rec, "https", mode="exact").hits
    with rec.read() as c:
        assert dict(c.execute("SELECT id,text FROM chunks")) == original
        assert c.execute("SELECT count(*) FROM chunks_fts").fetchone()[0] == 6


def test_complete_query_bonus_beats_isolated_terms(rec):
    add_file(rec, "partial sample.txt", ("opening " * 20).encode(), actor="engineer")
    f = add_file(rec, "complete sample.txt", b"opening of offers sample", actor="engineer")
    assert search(rec, "opening offers").hits[0].file_id == f.id


def test_index_version_rebuild_is_once_and_never_changes_originals(boq):
    from qsone.records.search import INDEX_VERSION

    with boq.read() as c:
        original = c.execute("SELECT id,text FROM chunks").fetchall()
    index_vectors(boq, FlatEmbedder())
    with boq.write("one") as c:
        boq.set_meta(c, "search_index_version", "old")
    ensure_index(boq)
    assert boq.meta()["search_index_version"] == INDEX_VERSION
    assert index_vectors(boq, FlatEmbedder()) == len(original)
    ensure_index(boq)
    assert index_vectors(boq, FlatEmbedder()) == 0
    with boq.read() as c:
        assert c.execute("SELECT id,text FROM chunks").fetchall() == original
