"""Arabic and English names of the same QS thing (qs_terms.json), so a query finds passages in
the other language too: «نسبة المحتجز من المستخلصات» is also searched as "retention" and
"interim payment certificate". The small search model crosses languages weakly by itself.

For search only: the names widen what a query looks for; they are never shown and never an
answer (no content pack). The data file is the one list; add a name there, not in code."""

import json
import re
from collections.abc import Sequence
from functools import cache
from importlib.resources import files

from qsone.records import arabic

_ARABIC = re.compile("[؀-ۿ]")
_LATIN = re.compile("[A-Za-z]")
LANGS = ("en", "ar")


def language(text: str) -> str:
    """ "ar" when the text has Arabic letters and no more Latin ones, "en" when it has more Latin
    ones, "" when it has neither (a row of numbers)."""
    ar, en = len(_ARABIC.findall(text)), len(_LATIN.findall(text))
    return "ar" if ar and ar >= en else "en" if en else ""


def _key(token: str) -> str | None:
    """A normalised word as names are matched: English plurals folded ("payments"), a lone
    letter dropped (the "s" of "contractor's"). Arabic words are already light-stemmed."""
    if _ARABIC.search(token):
        return token
    if len(token) == 1 and token.isalpha():
        return None
    plural = len(token) > 3 and token.endswith("s") and not token.endswith("ss")
    return token[:-1] if plural else token


def _keys(text: str) -> list[str]:
    return [k for k in map(_key, arabic.normalise(text).split()) if k]


@cache
def _terms() -> tuple[dict[str, tuple[str, ...]], ...]:
    data = json.loads((files("qsone.records") / "qs_terms.json").read_text("utf-8"))
    return tuple({lang: tuple(t[lang]) for lang in LANGS} for t in data["terms"])


@cache
def _index() -> dict[str, list[tuple[tuple[str, ...], int]]]:
    """First word -> (the name's words, its entry), longest names first."""
    index: dict[str, list[tuple[tuple[str, ...], int]]] = {}
    for n, term in enumerate(_terms()):
        for name in (name for lang in LANGS for name in term[lang]):
            keys = tuple(_keys(name))
            if keys and (keys, n) not in index.get(keys[0], []):
                index.setdefault(keys[0], []).append((keys, n))
    for names in index.values():
        names.sort(key=lambda kn: -len(kn[0]))
    return index


def named(text: str) -> list[int]:
    """The entries a text names, in order: the longest name wins where names overlap."""
    keys, found, i = _keys(text), [], 0
    index = _index()
    while i < len(keys):
        for name, n in index.get(keys[i], ()):
            if tuple(keys[i : i + len(name)]) == name:
                if n not in found:
                    found.append(n)
                i += len(name)
                break
        else:
            i += 1
    return found


def expand(texts: Sequence[str]) -> tuple[list[str], list[str]]:
    """(the named terms in each language none of `texts` is written in, for search by meaning;
    every name of them, normalised, for search by words)."""
    found = []
    for text in texts:
        found += [n for n in named(text) if n not in found]
    if not found:
        return [], []
    terms = _terms()
    written = {language(t) for t in texts if t.strip()}
    meaning = [", ".join(terms[n][lang][0] for n in found) for lang in LANGS if lang not in written]
    phrases = []
    for n in found:
        for name in (name for lang in LANGS for name in terms[n][lang]):
            norm = arabic.normalise(name)
            if norm and norm not in phrases:
                phrases.append(norm)
    return meaning, phrases
