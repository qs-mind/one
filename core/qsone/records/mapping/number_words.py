"""Bounded source number-word recognition."""

import re
import unicodedata

from qsone.records import arabic


def vocabulary():
    words = {}
    english = (
        "zero one two three four five six seven eight nine ten eleven twelve "
        "thirteen fourteen fifteen sixteen seventeen eighteen nineteen"
    ).split()
    words.update({word: n for n, word in enumerate(english)})
    for n, word in enumerate("twenty thirty forty fifty sixty seventy eighty ninety".split(), 2):
        words[word] = n * 10
    groups = [
        "صفر",
        "واحد واحدة",
        "اثنان اثنين اثنتان اثنتين",
        "ثلاث ثلاثة",
        "اربع اربعة",
        "خمس خمسة",
        "ست ستة",
        "سبع سبعة",
        "ثمان ثمانية",
        "تسع تسعة",
        "عشر عشرة",
    ]
    for n, group in enumerate(groups):
        for word in group.split():
            words[word] = n
    for n, stem in enumerate(["ثلاث", "اربع", "خمس", "ست", "سبع", "ثمان", "تسع"], 3):
        for suffix in ("ون", "ين"):
            words[stem + suffix] = n * 10
        for suffix in ("مائة", "مئة"):
            words[stem + suffix] = n * 100
    words.update(
        {
            "عشرون": 20,
            "عشرين": 20,
            "مائة": 100,
            "مئة": 100,
            "مائتان": 200,
            "مائتين": 200,
            "مئتان": 200,
            "مئتين": 200,
            "الف": 1000,
            "hundred": 100,
            "thousand": 1000,
            "احد": 1,
            "احدى": 1,
            "اثنا": 2,
            "اثني": 2,
            "اثنتا": 2,
            "اثنتي": 2,
        }
    )
    return words


WORDS = vocabulary()


def values(text):
    text = arabic.clean(text).casefold().translate(str.maketrans("أإآ", "ااا"))
    text = "".join(c for c in text if not unicodedata.category(c).startswith("M"))
    tokens = re.findall(r"[^\W\d_]+|[\d.,/]+", text.replace("-", " "))
    result, total, active = set(), 0, False
    for token in tokens + ["."]:
        if token in ("and", "و") and active:
            continue
        token = token[1:] if token.startswith("و") and token[1:] in WORDS else token
        if token in ("hundred", "thousand") and active:
            total *= WORDS[token]
        elif token in WORDS:
            total += WORDS[token]
            active = True
        else:
            if active:
                result.add(total)
            total, active = 0, False
    return result
