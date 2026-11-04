"""Texts the core returns to the engineer, always as {en, ar} pairs.

"Claude key" / «مفتاح Claude» is the button label on the screen (aiKey in ui/src/i18n.ts).
"""

NO_KEY = {
    "en": (
        "There is no Claude key yet. Press “Claude key” at the top, add your Claude key, "
        "then send your message again."
    ),
    "ar": "لسه مفيش مفتاح Claude. دوس على «مفتاح Claude» فوق وضيف مفتاحك، وبعدين ابعت رسالتك تاني.",
}

KEY_STORE_DOWN = {
    "en": (
        "The system key store is not available, so the key was not saved. "
        "Unlock it or turn it on, then try again."
    ),
    "ar": "مخزن المفاتيح في الجهاز مش متاح، فالمفتاح ماتحفظش. افتحه أو شغّله وجرّب تاني.",
}

# Model errors: the engineer sees one of these; the details go to core.log only.
KEY_REFUSED = {
    "en": "The Claude key was refused. Check it, or add a new one from “Claude key” at the top.",
    "ar": "مفتاح Claude اترفض. راجعه، أو ضيف مفتاح جديد من «مفتاح Claude» فوق.",
}

NO_CONNECTION = {
    "en": "Could not reach Claude. Check the internet connection, then try again.",
    "ar": "مقدرناش نوصل لـ Claude. اتأكد إن النت شغال وجرّب تاني.",
}

CLAUDE_BUSY = {
    "en": "Claude is busy right now. Try again in a minute.",
    "ar": "في ضغط على Claude دلوقتي. جرّب تاني كمان دقيقة.",
}

MODEL_FAILED = {
    "en": "The reply stopped because of a problem with Claude. Try again.",
    "ar": "الرد وقف بسبب مشكلة في Claude. جرّب تاني.",
}

# Project Records: projects.
PROJECT_NOT_FOUND = {
    "en": "This project is not on this computer.",
    "ar": "المشروع ده مش موجود على الجهاز ده.",
}

PROJECT_NOT_OPEN = {
    "en": "Open the project first.",
    "ar": "افتح المشروع الأول.",
}

PROJECT_KEY_MISSING = {
    "en": "The project's key is not in the system key store, so it cannot be opened.",
    "ar": "مفتاح المشروع مش موجود في مخزن المفاتيح في الجهاز، فمش هينفع يتفتح.",
}

PROJECT_DAMAGED = {
    "en": (
        "The project file cannot be read (it is damaged, or the key does not match). "
        "Nothing was changed."
    ),
    "ar": "ملف المشروع مش بيتقري (يا إما بايظ، يا إما المفتاح مش مطابق). ماتغيرش فيه حاجة.",
}

PROJECT_TOO_NEW = {
    "en": "A newer version of One saved this project. Update One, then open it.",
    "ar": "المشروع ده اتحفظ بنسخة أحدث من One. حدّث One وبعدين افتحه.",
}

# Project Records: files.
FILE_TOO_BIG = {
    "en": "The file is larger than 256 MB, so it was not added.",
    "ar": "الملف أكبر من 256 ميجا، فماتضافش.",
}

FILE_EMPTY = {
    "en": "The file is empty.",
    "ar": "الملف فاضي.",
}

FILE_NOT_READ_YET = {
    "en": "Kept in Project Records. One cannot read this kind of file yet.",
    "ar": "اتحفظ في سجلات المشروع. One لسه مش بيقرا النوع ده من الملفات.",
}

FILE_SCANNED_PAGES = {
    "en": "Some pages have no text layer (they are scanned), so they cannot be searched yet.",
    "ar": "في صفحات مفيهاش نص (متصورة سكانر)، فلسه مش هينفع ندوّر فيها.",
}

FILE_UNREADABLE = {
    "en": "Kept, but One could not read it (it is damaged, or locked with a password).",
    "ar": "اتحفظ، بس One مقدرش يقراه (يا إما بايظ، يا إما مقفول بباسورد).",
}

SEARCH_WORDS_ONLY = {
    "en": "Searching by words only for now. Search by meaning comes with the local model.",
    "ar": "البحث بالكلمات بس دلوقتي. البحث بالمعنى هييجي مع النموذج المحلي.",
}

# Project Records: the Source Ledger.
NUMBER_NOT_EXACT = {
    "en": (
        "Send the number as text: digits and one decimal point, no thousands separators, "
        "e.g. 39850.50."
    ),
    "ar": "ابعت الرقم كنص: أرقام وعلامة عشرية واحدة، من غير فواصل آلاف، زي 39850.50.",
}

NUMBER_NEEDS_UNIT = {
    "en": "This number needs a unit.",
    "ar": "الرقم ده محتاج وحدة.",
}

NUMBER_NEEDS_CURRENCY = {
    "en": "This number needs a currency: three letters, e.g. EGP, SAR, AED.",
    "ar": "الرقم ده محتاج عملة: تلات حروف، زي EGP أو SAR أو AED.",
}

NUMBER_NEEDS_SOURCE = {
    "en": "This number needs a source.",
    "ar": "الرقم ده محتاج مصدر.",
}

NUMBER_NEEDS_DATE = {
    "en": "This number needs the date it is true for, as YYYY-MM-DD.",
    "ar": "الرقم ده محتاج التاريخ اللي هو صحيح فيه، بالشكل YYYY-MM-DD.",
}

CORRECTION_NEEDS_REASON = {
    "en": "A correction needs a reason.",
    "ar": "التصحيح محتاج سبب.",
}

ALREADY_CORRECTED = {
    "en": "This number was already corrected. Correct the newest entry instead.",
    "ar": "الرقم ده اتصحح قبل كده. صحّح آخر قيمة بدل منه.",
}
