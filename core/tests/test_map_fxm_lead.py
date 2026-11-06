"""Synthetic regressions for tender facts in the first Lead request."""

import pytest

from qsone.engine import truth
from qsone.engine.map_digest import digest
from qsone.records import files, search
from qsone.records.mapping import store


def tender_fact(rec):
    f = files.add_file(
        rec,
        "sample-conditions.txt",
        "فتح العروض 16/04/1448".encode(),
        folder="01 المستلم",
        actor="t",
    )
    with rec.write("one") as c:
        store.write(
            c,
            rec,
            "map_facts",
            dict(
                id="sample-opening",
                file_id=f.id,
                name={"en": "Opening of offers", "ar": "فتح العروض"},
                value="16/04/1448",
                locator={"page": 7},
                state="found",
                evidence="فتح العروض 16/04/1448",
            ),
        )
    return f


def test_digest_keeps_tender_value_and_verification(rec):
    f = tender_fact(rec)
    text = digest(rec)
    assert "16/04/1448" in text and f.name in text
    assert "Opening of offers" in text and "فتح العروض" in text
    assert "unchecked" in text and "Received" in text


def test_map_grounded_fact_counts_as_read_only_at_its_source(rec):
    f = tender_fact(rec)
    assert not truth.unread_citations(f"Opening: 16/04/1448 ({f.name}, page 7).", [], rec=rec)
    assert truth.unread_citations(f"Opening: 17/04/1448 ({f.name}, page 7).", [], rec=rec)
    assert truth.unread_citations(f"Opening: 16/04/1448 ({f.name}, page 8).", [], rec=rec)
    assert truth.unread_citations("Opening: 16/04/1448 (other.txt, page 7).", [], rec=rec)


@pytest.mark.parametrize(
    ("query", "words"),
    [
        ("opening of offers", "فتح العروض"),
        ("award date", "الترسية"),
        ("works start", "بدء الأعمال"),
        ("project duration", "مدة المشروع"),
    ],
)
def test_english_tender_query_finds_arabic(rec, query, words):
    f = files.add_file(rec, "sample-arabic.txt", (words + " 16/04/1448").encode(), actor="t")
    result = search.search(rec, query)
    assert result.hits and result.hits[0].file_id == f.id
