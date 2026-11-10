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


# Visual order to logical order -----------------------------------------------------------------

_MIRROR = dict(zip("()[]{}<>«»", ")(][}{><»«", strict=True))


def _bidi(ch: str) -> str:
    kind = unicodedata.bidirectional(ch)
    if kind in ("R", "AL"):
        return "R"
    return kind if kind in ("L", "EN", "AN", "ES", "CS", "ET", "NSM") else "N"


def logical_order(items: list[tuple[str, object]]) -> list[tuple[str, object]]:
    """A printed line's characters as a recogniser reads them (left to right on the page), each
    with a payload, in the order they are read. ONE's own small subset of UAX#9, enough for one
    line (no python-bidi, which is LGPL): a line with no right-to-left letter stays as it is;
    left-to-right runs (Latin words, numbers with the separators the bidi rules join to them:
    `. , : /` between digits of one script, `+ -` between Western digits) keep their order and
    everything else is reversed around them; brackets in right-to-left text are mirrored back.
    So «٢-١-١٢» on the page is «١٢-١-٢» in the text, as ONE's PDF reader has it."""
    kinds = [_bidi(ch) for ch, _ in items]
    if "R" not in kinds:
        return list(items)
    n = len(items)
    ltr = [k in ("L", "EN", "AN") for k in kinds]

    def digit(i):
        return 0 <= i < n and kinds[i] in ("EN", "AN")

    for i, k in enumerate(kinds):  # W4/W5: separators and terminators that belong to a number
        if k == "CS" and digit(i - 1) and digit(i + 1) and kinds[i - 1] == kinds[i + 1]:
            ltr[i] = True
        elif k == "ES" and digit(i - 1) and digit(i + 1) and kinds[i - 1] == kinds[i + 1] == "EN":
            ltr[i] = True
        elif k == "ET" and ((i and kinds[i - 1] == "EN") or (i + 1 < n and kinds[i + 1] == "EN")):
            ltr[i] = True
    for i, k in enumerate(kinds):  # marks follow their base
        if k == "NSM" and i and ltr[i - 1]:
            ltr[i] = True
    i = 0
    while i < n:  # neutrals between two Latin runs stay inside the Latin text
        if ltr[i]:
            i += 1
            continue
        j = i
        while j < n and not ltr[j] and kinds[j] != "R":
            j += 1
        left = i - 1
        if j > i and left >= 0 and j < n and ltr[left] and ltr[j]:
            strong = next((kinds[p] for p in range(left, -1, -1) if kinds[p] in ("L", "R")), "R")
            if kinds[left] in ("L", "EN") and kinds[j] == "L" and strong == "L":
                for p in range(i, j):
                    ltr[p] = True
        i = max(j, i + 1)
    tokens, i = [], 0
    while i < n:
        if ltr[i]:
            j = i
            while j < n and ltr[j]:
                j += 1
            tokens.append(items[i:j])
            i = j
        else:
            ch, payload = items[i]
            tokens.append([(_MIRROR.get(ch, ch), payload)])
            i += 1
    out = [item for token in reversed(tokens) for item in token]
    fixed, k = [], 0
    while k < len(out):  # a combining mark read before its letter goes after it
        if (
            unicodedata.bidirectional(out[k][0]) == "NSM"
            and k + 1 < len(out)
            and _bidi(out[k + 1][0]) == "R"
            and (not fixed or _bidi(fixed[-1][0]) != "R")
        ):
            fixed += [out[k + 1], out[k]]
            k += 2
        else:
            fixed.append(out[k])
            k += 1
    return fixed
