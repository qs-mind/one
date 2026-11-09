"""The words of a reply: the patterns the checks look for, its sentences, integers and script."""

import re

# The reply -----------------------------------------------------------------------------------

_SENTENCE = re.compile(r"[^.!?؟\n]+[.!?؟]?")
# Pricing done: «تم الانتهاء من تسعير», «سعّرت», «اتسعّرت», "priced all", "finished pricing".
PRICED = re.compile(r"تسعير|سع[ّ]?ر(?:ت|نا)\b|اتسع[ّ]?ر|مسع[ّ]?ر|\bpric(?:ed|ing)\b", re.IGNORECASE)
_DONE = re.compile(
    r"تم\s+(?:ال)?انتهاء|انتهي(?:ت|نا)|خل[ّ]?ص(?:ت|نا)|اكتمل|تم\s+تسعير|سع[ّ]?ر(?:ت|نا)\b"
    r"|اتسع[ّ]?ر|\b(?:completed?|finished|done|have priced|priced)\b",
    re.IGNORECASE,
)
# Every item of the BOQ, not a section's: «كافة بنود المقايسة», «كل البنود», "all the items".
_ALL = re.compile(
    r"(?:كل|كاف[ةه]|جميع)\s+(?:ال)?بنود(?:\s+(?:ال)?(?:مقايس[ةه]|جدول(?:\s+الكميات)?))?"
    r"(?=\s*(?:$|[(\[«.،,؛:!؟]|[0-9٠-٩]|و|بال|ب\s))"
    r"|(?:ال)?مقايس[ةه]\s+(?:كل[هة]ا|بالكامل|كامل[ةه])"
    r"|\b(?:all|every one of)\s+(?:the\s+)?(?:[0-9,]+\s+)?(?:boq\s+)?items\b"
    r"(?!\s+(?:in|of|under)\s+(?:section|division|the\s+\w+\s+works))"
    r"|\bthe\s+(?:whole|entire|full)\s+boq\b",
    re.IGNORECASE,
)
_INTEGER = re.compile(r"(?<![\d.,٫])[0-9٠-٩]{1,6}(?![\d.,٫])")
_DELIVERABLE_READY = re.compile(
    r"(?:خطاب(?: "
    r"العطاء)?|الخطاب|المخرج|المستند|مستند|مخرج|المقايس[ةه]\s+المسع[ّ]?ر[ةه]|deliverable)"
    r"[^.!?؟\n]{0,40}(?:جاهز|اتعمل|أنشأت|انشأت|عملت|خلص)"
    r"|(?:أنشأت|انشأت|قمت\s+بإنشاء|عملت|جهزت|جه[ّ]?زت)[^.!?؟\n]{0,30}(?:مستند|مخرج|deliverable)"
    r"|\b(?:deliverable|priced boq)\b[^.!?\n]{0,30}\b(?:is ready|ready|created|made)\b"
    r"|\b(?:created|made|prepared|wrote|written)\s+(?:the|a)\s+"
    r"(?:deliverable|priced boq|letter|document)\b"
    r"|\b(?:letter|document)\b[^.!?\n]{0,30}\b(?:ready|written|prepared)\b"
    r"|(?:تم\s+(?:تجهيز|كتابة|إعداد)|كتبت|جهزت)[^.!?؟\n]{0,30}(?:خطاب|مستند)",
    re.IGNORECASE,
)
# A change made: «تم تثبيت الأسعار», «عدّلت», «اتغيرت», "updated", "changed".
_CHANGED = re.compile(
    r"تم\s+(?:تثبيت|تعديل|تغيير|تحديث|استبدال|ضبط)|(?:عد[ّ]?لت|غي[ّ]?رت|ثب[ّ]?ت|حد[ّ]?ثت|ظبطت)\b"
    r"|\bات(?:عد[ّ]?ل|غي[ّ]?ر|ثب[ّ]?ت|حد[ّ]?ث)(?:ت)?\b"
    r"|\b(?:i(?:'ve| have)?\s+(?:updated|changed|set|fixed|replaced)|(?:has|have) been "
    r"(?:updated|changed|set|fixed|replaced))\b",
    re.IGNORECASE,
)
_CARD = re.compile(r"البطاق[ةه]|الكارت|بطاق[ةه]|كارت|\bcard\b", re.IGNORECASE)
# The end of a reply that says work goes on when nothing runs: «جاري التنفيذ…», «ثواني وهتكون».
_PROMISE = re.compile(
    r"\bجار[يٍ]?\s|\bه(?:ن)?(?:بدأ|كم[ّ]?ل|شتغل|بعت|رجع|ظبط|نض[ّ]?ف)\w*|\bسأ(?:قوم|بدأ|كمل|رسل|عمل)"
    r"|هخلص|هعرضهولك|سأقوم|\bi am going to\b|\bسوف\s|\bثواني\b|ثانية\s+واحدة"
    r"|\bلحظ(?:ة|ات)\b|دقايق\s+و|\bحال[اًا]+\s*$|بشتغل\s+على|\bبنشتغل"
    r"|\b(?:i will|i'll|we will|we'll|working on it|in progress|one moment|just a moment|"
    r"shortly|in a few (?:seconds|minutes)|let me now|starting now|will now)\b",
    re.IGNORECASE,
)
_OFFER = re.compile(
    r"لو\s+(?:عايز|عاوز|تحب|حابب|تحبي|حابة)|تحب\s+(?:إن|ان)|عايزني|\bif you (?:want|like|wish)|"
    r"\bshall i\b|\bdo you want\b|\bwould you like\b|[?؟]\s*$",
    re.IGNORECASE,
)
# Words for a specialist that ended up in the reply: «استمر يا بشمهندس، كمل تسعير… أنا متابع».
_ASK_ENGINEER = re.compile(
    r"(?:you may want to )?ask the engineer if they have received alternative offers", re.I
)
_TO_TEAM = re.compile(
    r"(?:^|[.!؟\n،,]\s*)(?:استمر|كم[ّ]?ل|ابدأ|خليك)\s+(?:يا|في|تسعير|الشغل|شغلك)"
    r"|أنا\s+متابع\s+معاك|انا\s+متابع\s+معاك|\b(?:keep going|carry on with|continue pricing|"
    r"i'?m following your work)\b",
    re.IGNORECASE,
)
_BRACKETED_ENGLISH = re.compile(r"[(（]\s*[A-Za-z][A-Za-z \-/]{1,40}\s*[)）]")
_TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$", re.M)
_ARABIC = re.compile(r"[؀-ۿ]")
_LATIN = re.compile(r"[A-Za-z]")
_LABOUR_CLAIM = re.compile(
    r"شامل(?:ة|اً|ا)?\s+(?:ال)?(?:مواد\s+و\s*ال)?(?:عمال[ةه]|مصنعي[ةه]|تركيب)"
    r"|\bincl(?:uding|\.)?\s+(?:materials and\s+)?(?:labou?r|installation)\b",
    re.IGNORECASE,
)


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE.findall(text or "") if s.strip()]


def _integers(sentence: str) -> list[int]:
    return [int(m.group().translate(_DIGITS)) for m in _INTEGER.finditer(sentence)]


_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


def arabic(text: str) -> bool:
    return len(_ARABIC.findall(text or "")) >= len(_LATIN.findall(text or ""))
