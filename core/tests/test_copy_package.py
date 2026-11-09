"""The texts package (`qsone.copy`): a text is added in its area module and nowhere else. Every
area's texts are on the package, no name means two things, every text has its English and its
Arabic, and `words_for` finds a text by one rule. Synthetic «عينة» data only."""

import ast
import importlib
import pkgutil
import shutil
import subprocess
import sys
from pathlib import Path

from qsone import copy

# Every module of the package holds one area's texts, but `lookup` (it holds `words_for`).
AREAS = [
    importlib.import_module(f"{copy.__name__}.{found.name}")
    for found in pkgutil.iter_modules(copy.__path__)
    if found.name != "lookup"
]


def _texts() -> list[tuple[str, dict]]:
    """Each {en, ar} text of each area module, by `area.NAME`."""
    return [
        (f"{area.__name__}.{name}", value)
        for area in AREAS
        for name, value in vars(area).items()
        if isinstance(value, dict) and ("en" in value or "ar" in value)
    ]


def _assigned(area) -> list[str]:
    """The names an area module's own top-level lines give a value (its imports aside)."""
    names = []
    for node in ast.parse(Path(area.__file__).read_text(encoding="utf-8")).body:
        if isinstance(node, ast.FunctionDef | ast.ClassDef):
            names.append(node.name)
        elif isinstance(node, ast.Assign | ast.AnnAssign):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names += [
                part.id
                for target in targets
                for part in ast.walk(target)
                if isinstance(part, ast.Name)
            ]
    return names


def test_every_text_of_every_area_is_on_the_package():
    texts = _texts()
    assert texts
    for where, text in texts:
        assert getattr(copy, where.rpartition(".")[2], None) is text, where


def test_no_name_is_given_a_value_in_two_areas():
    # the package takes each area whole (`import *`): of two values for one name, one would
    # win and nothing would say so
    home: dict[str, str] = {}
    for area in AREAS:
        for name in _assigned(area):
            if not name.startswith("_"):
                first = home.setdefault(name, area.__name__)
                assert first == area.__name__, f"{name} is in {first} and in {area.__name__}"
    assert home


def test_every_text_has_its_english_and_its_arabic():
    for where, text in _texts():
        for language in ("en", "ar"):
            said = text.get(language)
            assert isinstance(said, str) and said.strip(), f"{where} has no {language}"


def test_words_for_finds_each_text_by_its_english_inside_a_longer_message():
    findable = [
        (where, text) for where, text in _texts() if "{" not in text["en"] and len(text["en"]) >= 20
    ]
    assert findable
    for where, text in findable:
        # the text itself, so no two of them may share their English
        assert copy.words_for(f"The tool said: {text['en']} (sample)") is text, where


def test_words_for_takes_the_longer_of_two_nested_texts(monkeypatch):
    inner = {"en": "The sample file is locked.", "ar": "الملف العينة مقفول."}
    outer = {
        "en": "The sample file is locked. Close it and try again.",
        "ar": "الملف العينة مقفول. اقفله وجرب تاني.",
    }
    monkeypatch.setattr(copy, "SAMPLE_INNER", inner, raising=False)
    monkeypatch.setattr(copy, "SAMPLE_OUTER", outer, raising=False)
    assert copy.words_for(f"Refused: {outer['en']}") is outer
    assert copy.words_for(f"Refused: {inner['en']}") is inner
    # the longest wins wherever it starts
    assert copy.words_for(f"{inner['en']} Then: {outer['en']}") is outer


def test_of_two_texts_of_one_length_words_for_takes_the_one_that_starts_first(monkeypatch):
    one = {"en": "Sample refusal number one.", "ar": "رفض عينة رقم واحد."}
    two = {"en": "Sample refusal number two.", "ar": "رفض عينة رقم اتنين."}
    assert len(one["en"]) == len(two["en"])
    monkeypatch.setattr(copy, "SAMPLE_ONE", one, raising=False)
    monkeypatch.setattr(copy, "SAMPLE_TWO", two, raising=False)
    assert copy.words_for(f"{one['en']} {two['en']}") is one
    # the place in the message decides, not which text the package holds first
    assert copy.words_for(f"{two['en']} {one['en']}") is two


def test_words_for_gives_none_for_a_message_that_holds_no_text(monkeypatch):
    whole = {"en": "This sample refusal is whole.", "ar": "الرفض العينة ده كامل."}
    short = {"en": "Sample, too short.", "ar": "عينة قصيرة."}
    blank = {"en": "The sample file {name} is locked.", "ar": "الملف العينة {name} مقفول."}
    for name, text in (("SAMPLE_WHOLE", whole), ("SAMPLE_SHORT", short), ("SAMPLE_BLANK", blank)):
        monkeypatch.setattr(copy, name, text, raising=False)
    assert copy.words_for("Nothing in this sample message is a text of ONE.") is None
    assert copy.words_for("") is None
    assert copy.words_for(whole["en"]) is whole
    assert copy.words_for(whole["en"][:-1]) is None  # a text is found whole or not at all
    # under 20 characters, or with a blank to fill: never found
    assert copy.words_for(f"Refused: {short['en']}") is None
    assert copy.words_for(f"Refused: {blank['en']}") is None


def test_a_new_text_is_added_in_one_place(tmp_path):
    """A copy of the package with one text more in one area module and nothing else changed: the
    text is on the package, and `words_for` finds it."""
    package = tmp_path / "qsone" / "copy"
    shutil.copytree(
        Path(copy.__file__).parent, package, ignore=shutil.ignore_patterns("__pycache__")
    )
    (package.parent / "__init__.py").write_text("", encoding="utf-8")
    with (package / Path(AREAS[0].__file__).name).open("a", encoding="utf-8") as area:
        area.write(
            '\nSAMPLE_ADDED = {"en": "This sample text was added in one place.", '
            '"ar": "النص العينة ده اتضاف في مكان واحد."}\n'
        )
    check = (
        "import sys\n"
        "sys.path.insert(0, sys.argv[1])\n"
        "from qsone import copy\n"
        "assert copy.__file__.startswith(sys.argv[1]), copy.__file__\n"
        "assert copy.SAMPLE_ADDED['en'] == 'This sample text was added in one place.'\n"
        "said = 'Refused: This sample text was added in one place. (sample)'\n"
        "assert copy.words_for(said) is copy.SAMPLE_ADDED\n"
    )
    ran = subprocess.run(
        [sys.executable, "-c", check, str(tmp_path)],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    assert ran.returncode == 0, ran.stderr
