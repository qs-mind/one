"""The truth checks: the facts beside a reply, and the line for each claim not in the records."""

# The truth checks (engine/truth.py): the facts the core puts beside a Brief's reply, from its own
# records, and the line for each claim the records do not show.
TRUTH_COVERAGE = {
    "en": "From ONE's records: {items} · {priced} priced by ONE · {made}",
    "ar": "من سجلات ONE: {items} · ONE سعّر {priced} · {made}",
}
TRUTH_CLIENT_RATES = {
    "en": "{items}, {n} with the client's rates",
    "ar": "{items}، فيهم {n} بسعر العميل",
}
TRUTH_NO_DELIVERABLE_YET = {"en": "no Deliverable yet", "ar": "مفيش مخرج لسه"}
TRUTH_DELIVERABLES = {"en": "{n} made", "ar": "فيه {n}"}
TRUTH_OVERCLAIM_PRICED = {
    "en": "The reply says {said} items are priced; the records show {priced} of {items}.",
    "ar": "الرد بيقول إن {said} بند اتسعّروا، والسجلات فيها {priced} بس من {items}.",
}
TRUTH_NO_DELIVERABLE = {
    "en": "The reply says a Deliverable is ready; there is none yet.",
    "ar": "الرد بيقول إن فيه مخرج جاهز، ومفيش مخرج لسه.",
}
TRUTH_NOTHING_CHANGED = {
    "en": "The reply says something changed; nothing was recorded or changed in this Brief.",
    "ar": "الرد بيقول إن حاجة اتغيرت، بس مفيش حاجة اتسجلت ولا اتغيرت في التكليف ده.",
}
TRUTH_SUPPLY_ONLY = {
    "en": "The reply says the rate includes labour; the quote it cites ({quote}) is supply only.",
    "ar": "الرد بيقول إن الفئة شاملة المصنعية، بس العرض اللي اتذكر ({quote}) توريد بس.",
}
TRUTH_PLACEHOLDER = {
    "en": "The reply left blanks for values: {blanks}. Those values are missing.",
    "ar": "الرد ساب فراغات مكان قيم: {blanks}. القيم دي ناقصة.",
}
TRUTH_PROMISE = {
    "en": "The reply says work is under way, but nothing is running now. Ask again to go on.",
    "ar": "الرد بيقول إن فيه شغل ماشي، بس مفيش حاجة شغالة دلوقتي. ابعت تاني عشان نكمّل.",
}
TRUTH_NO_CARD = {
    "en": "The «I understood this» card was not saved, so there is none to review yet.",
    "ar": "كارت «فهمت كده» ماتحفظش، فمفيش كارت تراجعه لسه.",
}
TRUTH_CARD_NOT_SAVED = {
    "en": "The «I understood this» card was not saved: {why}",
    "ar": "كارت «فهمت كده» ماتحفظش: {why}",
}
# A reply that says a step was done after ONE refused it (the real walk, 6 Nov 2026).
TRUTH_REFUSED = {
    "en": "The reply says this was done, but ONE refused it, so it was not done: {why}",
    "ar": "الرد بيقول إن ده اتعمل، بس ONE رفضه فماتعملش: {why}",
}
TRUTH_NOT_DONE = {
    "en": "The reply says {what} was done; ONE's records show it was not done in this Brief.",
    "ar": "الرد بيقول إن {what} اتعمل، وسجلات ONE بتقول إنه ماتعملش في التكليف ده.",
}
CLAIM_IMPORT = {"en": "the BOQ import", "ar": "استيراد المقايسة"}
CLAIM_ADD = {"en": "an addition to the records or a Deliverable", "ar": "الإضافة للسجلات أو للمخرج"}
CLAIM_PRICED = {"en": "the pricing", "ar": "التسعير"}
REFUSED_STEP = {
    "en": "the step «{step}» could not be done as it was sent.",
    "ar": "خطوة «{step}» ماكانش ينفع تتعمل بالشكل اللي اتبعتت بيه.",
}
# Real walk 2: plain truth checks and replacements in a final reply.
TRUTH_EMPTY_DOCUMENT = {
    "en": "The document is still empty. Its text has not been written yet.",
    "ar": "المستند لسه فاضي. نصه لسه ماتكتبش.",
}
TRUTH_CONTRACT_UNREAD = {
    "en": "These contract values have not been checked against the tender files in this request.",
    "ar": "قيم شروط العقد دي لسه ماتراجعتش على ملفات المناقصة في الطلب ده.",
}
TRUTH_LETTER_MONEY = {
    "en": (
        "The letter has values that are not verified against the project records. "
        "Do not use them yet."
    ),
    "ar": "الخطاب فيه قيم لسه ماتراجعتش على سجلات المشروع. ماتستخدمهاش لسه.",
}
REPLY_MISSING_VALUE = {"en": "not found", "ar": "مش موجود"}
REPLY_RECORDS = {"en": "project records", "ar": "سجلات المشروع"}
REPLY_TABLE = {"en": "table", "ar": "الجدول"}
REPLY_YOUR_QUOTES = {
    "en": "If you have alternative offers, add them for comparison",
    "ar": "لو عندك عروض بديلة، ضيفها عشان نقارنها",
}

TRUTH_EMPTY_DELIVERABLE = {
    "en": "The reply speaks of priced items, but the Deliverable this Brief made has no items.",
    "ar": "الرد بيتكلم عن بنود متسعّرة، بس المخرج اللي اتعمل في التكليف ده مافيهوش أي بند.",
}
TRUTH_MISCITED = {
    "en": "The reply says {value} is at {place}; that place has {have}.",
    "ar": "الرد بيقول إن {value} موجود في {place}؛ والمكان ده فيه {have}.",
}
TRUTH_NO_PLACE = {
    "en": "The reply cites {place}, which no project file has.",
    "ar": "الرد بيستشهد بـ{place}، ومفيش ملف في المشروع فيه المكان ده.",
}
TRUTH_PER_DAY = {
    "en": "The reply gives {value} without its unit: {place} has it per day.",
    "ar": "الرد بيقول {value} من غير وحدته: {place} كاتبه عن كل يوم.",
}
TRUTH_OTHER_ROW = {
    "en": "The reply prices item {code} from {place}, which is another item's row.",
    "ar": "الرد بيسعّر البند {code} من {place}، والصف ده بتاع بند تاني.",
}
NO_NUMBERS = {"en": "no numbers", "ar": "مفيش أرقام"}

TRUTH_UNREAD_PLACE = {
    "en": "ONE has not read {place} in this Brief. Read the source before relying on this claim.",
    "ar": "ONE مقراش {place} في الطلب ده. اقرا المصدر قبل ما تعتمد على المعلومة دي.",
}
TRUTH_UNREAD_REPLY = {
    "en": (
        "ONE could not verify the cited source in this Brief. "
        "Read the source before relying on this answer."
    ),
    "ar": "ONE مقدرش يتحقق من المصدر المذكور في الطلب ده. اقرا المصدر قبل ما تعتمد على الإجابة دي.",
}

TENDER_SEARCH_NUDGE = {
    "en": (
        "Before saying a tender requirement was not found, use search_records "
        "received_only=true in the documents’ language with 2–3 short Arabic/English "
        "phrasings (فتح العروض, مدة "
        "التنفيذ, مدة المشروع, duration), then files_read the best hit's page. If still "
        "missing, name the searches tried. Retry silently."
    ),
    "ar": (
        "قبل ما تقول إن شرط مناقصة مش موجود، استخدم search_records مع received_only=true "
        "بلغة المستندات، بصيغتين أو تلاتة قصيرين بالعربي والإنجليزي (فتح العروض، مدة التنفيذ، مدة "
        "المشروع، duration)، واقرأ صفحة أحسن نتيجة بـ files_read. لو لسه مش موجود، اذكر "
        "كلمات البحث اللي جرّبتها. أعد المحاولة من غير ما تقول للمهندس."
    ),
}

TRUTH_READING_METHOD = {
    "en": "The claimed reading method or OCR confidence is not supported by the reading record.",
    "ar": "طريقة القراءة أو نسبة ثقة OCR المذكورة مش مثبتة في سجل القراءة.",
}
