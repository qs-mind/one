"""Search: by words, and by meaning with the search model."""

SEARCH_WORDS_ONLY = {
    "en": "Searching by words only until search by meaning is ready.",
    "ar": "البحث بالكلمات بس لحد ما البحث بالمعنى يجهز.",
}

# Search by meaning: the search model ("Search model" / «نموذج البحث» in the glossary).
MEANING_DOWNLOAD_FAILED = {
    "en": (
        "The search model did not download (no internet, or the server did not answer). "
        "What came so far is kept; it goes on at the next start."
    ),
    "ar": (
        "نموذج البحث مانزلش (مفيش نت، أو السيرفر مارَدّش). "
        "اللي نزل لحد دلوقتي محفوظ، وهيكمّل أول ما تفتح البرنامج."
    ),
}

MEANING_FILE_DAMAGED = {
    "en": (
        "A downloaded file did not match its check, so it was deleted. "
        "It comes again at the next start."
    ),
    "ar": "ملف من اللي نزلوا ماطابقش الفحص بتاعه، فاتمسح. هينزل تاني أول ما تفتح البرنامج.",
}

MEANING_NO_SPACE = {
    "en": (
        "There is not enough free space: the search model needs about {size} free. "
        "Free some space; it tries again at the next start."
    ),
    "ar": (
        "مفيش مساحة فاضية كفاية: نموذج البحث محتاج حوالي {size} فاضيين. "
        "فضّي شوية مساحة، وهيحاول تاني أول ما تفتح البرنامج."
    ),
}

MEANING_NOT_ON_THIS_COMPUTER = {
    "en": "Search by meaning cannot run on this computer. Search by words works as usual.",
    "ar": "البحث بالمعنى مش هينفع يشتغل على الجهاز ده. البحث بالكلمات شغال عادي.",
}

MEANING_MODEL_FAILED = {
    "en": "The search model would not start, so it is checked and fetched again at the next start.",
    "ar": "نموذج البحث ماشتغلش، فهيتفحص ويتنزّل تاني أول ما تفتح البرنامج.",
}

MEANING_INDEX_FAILED = {
    "en": "Preparing search by meaning stopped on this project. It tries again at the next start.",
    "ar": "تجهيز البحث بالمعنى وقف في المشروع ده. هيحاول تاني أول ما تفتح البرنامج.",
}
