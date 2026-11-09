"""How a text is put into words: a file name in a sentence, filled blanks, counts, lists."""

import re
from dataclasses import dataclass

_EXTENSION = re.compile(r"(\.[A-Za-z0-9]{1,8})$")


_ARABIC_LETTERS = r"\u0600-\u06FF\u0750-\u077F\u0870-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF"
_ARABIC = re.compile(f"[{_ARABIC_LETTERS}]")
_STRONG = re.compile(f"[A-Za-z\u00c0-\u024f{_ARABIC_LETTERS}]")
_LATIN = re.compile(r"[A-Za-z]")


def file_name(name: str) -> str:
    """A file name for a sentence on screen, in Unicode isolates: the whole name first-strong
    (FSI … PDI), a lone extension in the name's direction (so its dot stays by an Arabic name, never
    «عينةxlsx.»). A name that starts in Arabic and ends in Latin words keeps those words with the
    extension as one left-to-right run (LRI … PDI), so
    «مواصفات (sample spec).docx» reads «مواصفات» then «(sample spec).docx» inside Arabic or
    English words, never «.docx(sample spec». Only for text shown to the engineer, never to a
    model. The UI's own file names do the same (ui/src/ui/FileName.tsx)."""
    found = _EXTENSION.search(name)
    whole = found is None or found.start() == 0
    stem, extension = (name, "") if whole else (name[: found.start()], found.group(1))
    first = _STRONG.search(stem)
    last = max((m.end() for m in _ARABIC.finditer(stem)), default=0)
    rest = stem[last:]
    if first and _ARABIC.match(first.group()) and last and _LATIN.search(rest):
        space = len(rest) - len(rest.lstrip())
        return f"\u2068{stem[: last + space]}\u2066{rest[space:]}{extension}\u2069\u2069"
    return f"\u2068{stem}{extension}\u2069"


_BLANK_THEN_STOP = re.compile(r"\{(\w+)\}\.")
_ISOLATES = "⁦⁧⁨⁩ "


def _one_stop(s: str, values: dict) -> str:
    """A value that ends a sentence itself («…شيت BOQ؟») takes the place of the full stop after
    its blank, never «؟.»."""

    def keep(m: re.Match) -> str:
        value = str(values.get(m[1], "")).rstrip(_ISOLATES)
        return m[0][:-1] if value[-1:] in (".", "?", "!", "؟", "…") else m[0]

    return _BLANK_THEN_STOP.sub(keep, s)


def fill(text: dict[str, str], /, **values) -> dict[str, str]:
    """Both languages of `text` with its {placeholders} filled from `values`.

    A value that is itself an {en, ar} pair gives each language its own words."""
    found = {}
    for lang, s in text.items():
        mine = {k: v[lang] if isinstance(v, dict) else v for k, v in values.items()}
        found[lang] = _one_stop(s, mine).format(**mine)
    return found


def _arabic_form(n: int) -> str:
    """Egyptian Arabic counting: بند واحد، بندين، 3 إلى 10 بنود، 11 فأكتر بند."""
    if n == 1:
        return "one"
    if n == 2:
        return "two"
    return "few" if 3 <= n % 100 <= 10 else "other"


@dataclass(frozen=True)
class Noun:
    """A counted noun's forms, each with {n}: English "one" and "other"; Arabic "one", "two",
    "few" (3 to 10) and "other"."""

    en: dict[str, str]
    ar: dict[str, str]


def counted(n: int, noun: Noun) -> dict[str, str]:
    """`n` with its noun in each language's own form. A value for `fill`."""
    return {
        "en": noun.en["one" if n == 1 else "other"].format(n=n),
        "ar": noun.ar[_arabic_form(n)].format(n=n),
    }


ITEMS = Noun(
    en={"one": "1 item", "other": "{n} items"},
    ar={"one": "بند واحد", "two": "بندين", "few": "{n} بنود", "other": "{n} بند"},
)
HEADINGS = Noun(
    en={"one": "1 heading", "other": "{n} headings"},
    ar={"one": "عنوان واحد", "two": "عنوانين", "few": "{n} عناوين", "other": "{n} عنوان"},
)
ROWS = Noun(
    en={"one": "1 row", "other": "{n} rows"},
    ar={"one": "صف واحد", "two": "صفين", "few": "{n} صفوف", "other": "{n} صف"},
)
CHANGES = Noun(
    en={"one": "1 change", "other": "{n} changes"},
    ar={"one": "تغيير واحد", "two": "تغييرين", "few": "{n} تغييرات", "other": "{n} تغيير"},
)
SECTIONS = Noun(
    en={"one": "1 section", "other": "{n} sections"},
    ar={"one": "قسم واحد", "two": "قسمين", "few": "{n} أقسام", "other": "{n} قسم"},
)
FILES = Noun(
    en={"one": "1 file", "other": "{n} files"},
    ar={"one": "ملف واحد", "two": "ملفين", "few": "{n} ملفات", "other": "{n} ملف"},
)


def listed(values: list[str]) -> dict[str, str]:
    """A short list of values in each language: «أ، ب» in Arabic, "a, b" in English."""
    return {"en": ", ".join(values), "ar": "، ".join(values)}
