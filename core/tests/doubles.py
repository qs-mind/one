"""Test doubles for the search interfaces. Not product code: the real models come in Plan 2b."""

import math

# Concepts named in both languages, one axis each. A small constant axis keeps vectors non-zero.
CONCEPTS = [
    ("waterproofing", "عزل", "رطوب"),
    ("concrete", "خرسان"),
    ("steel", "حديد"),
    ("excavation", "حفر"),
]


class ConceptEmbedder:
    """Maps text to the concepts it names, so English finds Arabic and the reverse."""

    name = "test-concepts-1"
    dims = len(CONCEPTS) + 1

    def __init__(self) -> None:
        self.calls = 0

    def _embed(self, text: str) -> list[float]:
        text = text.lower()
        v = [1.0 if any(w in text for w in words) else 0.0 for words in CONCEPTS] + [0.1]
        size = math.sqrt(sum(x * x for x in v))
        return [x / size for x in v]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        return [self._embed(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)


class PreferReranker:
    """Scores 1.0 for texts that contain `word`, else 0.0."""

    name = "test-prefer-1"

    def __init__(self, word: str) -> None:
        self.word = word

    def rerank(self, query: str, texts: list[str]) -> list[float]:
        return [1.0 if self.word in t else 0.0 for t in texts]
