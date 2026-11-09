"""The Project Map: reading the files, its facts and their checks, and the AI passes."""

MAP_PROGRESS = {
    "en": "Reading {done} of {total} files",
    "ar": "بنقرا {done} من {total} ملف",
}
MAP_FAILED = {
    "en": "ONE could not map this file locally. The original is kept.",
    "ar": "ONE مقدرش يقرا خريطة الملف ده محليًا. الأصل محفوظ.",
}
MAP_ARABIC_MISSING = {
    "en": "Arabic OCR data is missing. ONE kept reading the other files.",
    "ar": "بيانات قراية الصور بالعربي مش موجودة. ONE كمل قراية باقي الملفات.",
}
MAP_CURSOR_INVALID = {
    "en": "This map page cursor is invalid. Open the map again.",
    "ar": "مؤشر صفحة الخريطة مش صحيح. افتح الخريطة تاني.",
}

MAP_FACT_UNCHECKED = {"en": "Read by ONE, not checked", "ar": "ONE قراها، لسه ما اتراجعتش"}
MAP_FACT_CONFIRMED = {"en": "Confirmed", "ar": "اتراجعت"}
MAP_FACT_INVALID = {
    "en": "Choose a current fact and confirm it or enter a correction.",
    "ar": "اختار معلومة حالية وأكّدها أو اكتب التصحيح.",
}
MAP_FACT_GATE = {
    "en": "Confirm {fact} ({page}) before Sign-off or export.",
    "ar": "أكّد {fact} ({page}) قبل الاعتماد أو التصدير.",
}
MAP_REFERS_TO = {"en": "Refers to", "ar": "بيشير لـ"}

MAP_FACT_PAGE = {"en": "page {page}", "ar": "صفحة {page}"}
MAP_FACT_SHEET = {"en": "sheet {sheet}, row {row}", "ar": "شيت {sheet}، صف {row}"}
MAP_FACT_LINE = {"en": "line {line}", "ar": "سطر {line}"}
MAP_REVISION = {"en": "Drawing revisions", "ar": "إصدارات اللوحة"}
MAP_AI_LABEL = {"en": "Project Map", "ar": "خريطة المشروع"}
MAP_AI_COST = {
    "en": "Mapping {count} files costs about US${cost}.",
    "ar": "تخطيط {count} ملف هيتكلف حوالي {cost} دولار.",
}
MAP_AI_PRICE_UNKNOWN = {
    "en": "ONE has no price for {model} yet, so it cannot estimate this. Map them anyway?",
    "ar": "ONE لسه معندوش سعر لـ {model}، فمش هيقدر يقدّر التكلفة. نعمل الخريطة برضه؟",
}
MAP_AI_RUN = {"en": "Map them", "ar": "خطّطهم"}

MAP_AI_FAILED_REASON = {
    "en": "the AI request failed",
    "ar": "طلب الذكاء الاصطناعي فشل",
}
MAP_AI_FAILED = {
    "en": "ONE could not map {count} files with the AI: {reason}. Local reading is kept.",
    "ar": "ONE مقدرش يعمل خريطة {count} ملف بالذكاء الاصطناعي: {reason}. القراية المحلية محفوظة.",
}

MAP_AI_TIMEOUT = {"en": "the AI request timed out", "ar": "طلب الذكاء الاصطناعي خلّص وقته"}
MAP_AI_INVALID_OUTPUT = {
    "en": "the AI returned invalid output",
    "ar": "الذكاء الاصطناعي رجّع نتيجة مش صالحة",
}
MAP_AI_ERROR_TYPE = {
    "en": "the AI request failed ({kind})",
    "ar": "طلب الذكاء الاصطناعي فشل ({kind})",
}

MAP_AI_TOO_LARGE = {
    "en": "the AI request was too large for the provider",
    "ar": "طلب الذكاء الاصطناعي كان أكبر من الحد اللي المزوّد بيقبله",
}

MAP_FACTS_EMPTY = {
    "en": (
        "Tender facts pass returned no grounded facts. "
        "Check candidate pages and model output; remap to retry."
    ),
    "ar": (
        "استخراج بيانات المناقصة ما رجعش بيانات مرتبطة بمصدر. "
        "راجع الصفحات المرشحة ورد النموذج، وأعد الخريطة للمحاولة."
    ),
}

MAP_ROLE_RECEIVED = {"en": "Received tender document", "ar": "مستند مناقصة مستلم"}
MAP_ROLE_WORKING = {"en": "Our submission / working file", "ar": "ملف عرضنا أو شغلنا"}
MAP_ROLE_UNKNOWN = {"en": "Role unconfirmed", "ar": "دور الملف لسه مش مؤكد"}
MAP_LOCAL_KEY_PAGE = {"en": "Key source page", "ar": "صفحة بيانات مهمة"}
MAP_LOCAL_KEY_REASON = {
    "en": "Local terms, dates or contents",
    "ar": "مصطلحات أو تواريخ أو فهرس في الملف",
}

MAP_PASS_FACTS = {"en": "Tender facts", "ar": "بيانات المناقصة"}
MAP_PASS_LINKS = {"en": "Document links", "ar": "روابط المستندات"}
MAP_PASS_FAILED = {
    "en": "{stage} could not finish after one retry: {reason}",
    "ar": "{stage} ما خلصتش بعد إعادة المحاولة مرة: {reason}",
}

MAP_PICTURE_NUMBER = {
    "en": "The PDF's text says {text}; the page shows {picture} — check the page.",
    "ar": "نص الـPDF بيقول {text}؛ الصفحة بتعرض {picture} — راجع الصفحة.",
}


MAP_FACT_REJECTED = {
    "en": "Found but not verified",
    "ar": "اتلاقت، بس لسه مش متحقق منها",
}

MAP_LOCAL_RETRY = {
    "en": "Local reading paused after a temporary error; ONE will retry once.",
    "ar": "القراءة المحلية وقفت بسبب خطأ مؤقت؛ ONE هيحاول مرة كمان.",
}
