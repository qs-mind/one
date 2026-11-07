"""Three forms of text. Display text is what the engineer reads, clean text goes to embeddings, and
normalised text goes into the word index and is used for queries (the spike's measured rules)."""

import math
import re
import unicodedata

# Bump when `normalise` changes: the word index of every project is then rebuilt.
NORMALISER_VERSION = 1

_PRESENTATION_FORMS = re.compile("[\ufb50-\ufdff\ufe70-\ufeff]+")
_KASHIDA = re.compile("[ \t]*\u0640+[ \t]*")  # with any spaces around it, as PDFs split it
_DOT_LEADER = re.compile(r"\.{4,}|\u2026{2,}")
_SPACES = re.compile(r"[^\S\n]+")
_LINE_END_SPACES = re.compile(r" ?\n ?")
_WORD = re.compile(r"\w+")
_ARABIC = re.compile("[\u0600-\u06ff]")

# Bidi marks and zero-width characters.
_INVISIBLE = "\u061c\u200b\u200c\u200d\u200e\u200f\u202a\u202b\u202c\u202d\u202e"
_INVISIBLE += "\u2060\u2066\u2067\u2068\u2069\ufeff"
_CLEAN = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹٫٬،", "01234567890123456789.,,", _INVISIBLE)

_HARAKAT = [*range(0x064B, 0x0660), 0x0670, *range(0x06D6, 0x06EE)]
_FOLD = str.maketrans("أإآٱىةؤئ", "اااايهوي", "".join(map(chr, _HARAKAT)))

_PREFIXES = ("وال", "بال", "كال", "فال", "لل", "ال", "و", "ب", "ل", "ف", "ك")
_SUFFIXES = ("ات", "ون", "ين", "ان", "يه", "ها", "ه", "ي")


def display_text(s: str, *, keep_blanks: bool = False) -> str:
    """Presentation forms joined, no kashida, tidy lines and spaces; digits as written."""
    s = _PRESENTATION_FORMS.sub(lambda m: unicodedata.normalize("NFKC", m[0]), s)
    s = _KASHIDA.sub("", s).replace("\r\n", "\n").replace("\r", "\n")
    s = _SPACES.sub(" ", s if keep_blanks else _DOT_LEADER.sub(" ", s))
    return _LINE_END_SPACES.sub("\n", s).strip()


def display_number(value: float | int) -> str:
    """A cell's number as Excel shows it in a General cell: at most 15 significant digits, so
    the noise of a stored double goes (4.7699999999999996 and 0.1 + 0.2 read 4.77 and 0.3).
    For text made from cells only: an import keeps the exact value (`boq.exact`)."""
    if isinstance(value, bool) or not isinstance(value, float) or not math.isfinite(value):
        return str(value)
    if value.is_integer() and abs(value) < 1e15:
        return str(int(value))
    text = format(value, ".15g")
    return text.rstrip("0").rstrip(".") if "." in text and "e" not in text else text


def clean(s: str) -> str:
    """For embeddings: NFKC, no invisible marks or kashida, Western digits, spaces collapsed."""
    s = _KASHIDA.sub("", unicodedata.normalize("NFKC", s).translate(_CLEAN))
    return _SPACES.sub(" ", s).strip()


def _stem(word: str) -> str:
    """Light stemming: one clitic prefix, then one common suffix, each leaving 3 letters or more."""
    for affix in _PREFIXES:
        if word.startswith(affix) and len(word) - len(affix) >= 3:
            word = word[len(affix) :]
            break
    for affix in _SUFFIXES:
        if word.endswith(affix) and len(word) - len(affix) >= 3:
            word = word[: -len(affix)]
            break
    return word


def normalise(s: str, *, stem: bool = True) -> str:
    """For the word index and for queries: folded letters, lower case, light-stemmed words."""
    words = _WORD.findall(clean(s).lower().translate(_FOLD))
    return " ".join(_stem(w) if stem and _ARABIC.search(w) else w for w in words)
