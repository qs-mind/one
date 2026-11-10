"""Automatic setup: each part ONE fetches or checks by itself, what needs it, and why it stopped."""

# The parts, by their manifest id.
SETUP_SEARCH_MODEL = {"en": "Search model", "ar": "نموذج البحث"}
SETUP_SEARCH_MODEL_AFFECTS = {
    "en": "Search by meaning in the tender files",
    "ar": "البحث بالمعنى في ملفات العطاء",
}
SETUP_SANDBOX = {"en": "Sandbox", "ar": "الصندوق المعزول"}
SETUP_SANDBOX_AFFECTS = {
    "en": "Working on sheets with code in the Sandbox",
    "ar": "الشغل على الشيتات بالكود في الصندوق المعزول",
}
SETUP_SANDBOX_NOT_HERE = {
    "en": "The Sandbox cannot run on this computer. Everything else works as usual.",
    "ar": "الصندوق المعزول مش هينفع يشتغل على الجهاز ده. كل حاجة تانية شغالة عادي.",
}
SETUP_DWG = {"en": "DWG reader", "ar": "قارئ ملفات DWG"}
SETUP_DWG_AFFECTS = {"en": "Reading DWG drawings", "ar": "قراءة رسومات DWG"}
SETUP_DWG_MISSING = {
    "en": "The DWG reader is missing from this installation. Installing ONE again puts it back.",
    "ar": "قارئ ملفات DWG مش موجود في النسخة دي. لو نزّلت ONE تاني هيرجع.",
}
SETUP_OCR = {"en": "Text reader for pictures", "ar": "قارئ النص في الصور"}
SETUP_OCR_AFFECTS = {
    "en": (
        "Reading text in scanned pages and pictures on this computer; until then your AI reads them"
    ),
    "ar": (
        "قراية النص في الصفحات المتصورة والصور على الجهاز ده؛ لحد ما ينزل نموذجك هو اللي يقراها"
    ),
}
SETUP_OCR_NOT_HERE = {
    "en": (
        "Text in pictures cannot be read on this computer. "
        "Your AI reads scanned pages and pictures instead."
    ),
    "ar": (
        "قراية النص في الصور مش هينفع على الجهاز ده. نموذجك هو اللي هيقرا الصفحات المتصورة والصور."
    ),
}

# Why a part failed after three tries.
SETUP_FILE_DAMAGED = {
    "en": "The downloaded file was damaged three times in a row.",
    "ar": "الملف نزل بايظ 3 مرات ورا بعض.",
}
SETUP_REFUSED = {
    "en": (
        "It did not download three times in a row: the server refused it, or it could not be saved."
    ),
    "ar": "مانزلش 3 مرات ورا بعض: السيرفر رفضه، أو ماتحفظش على الجهاز.",
}
SETUP_NO_SPACE = {
    "en": (
        "There is not enough free space: it needs about {size} free. Free some space, then retry."
    ),
    "ar": "مفيش مساحة فاضية كفاية: محتاج حوالي {size} فاضيين. فضّي شوية مساحة وجرّب تاني.",
}
