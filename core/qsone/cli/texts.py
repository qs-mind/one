"""CLI-only copy. Core replies keep their own bilingual copy."""

TEXT = {
    "costs_unavailable": {
        "en": "Cost records could not be read. This step failed; no money cap was inferred.",
        "ar": "مقدرناش نقرا سجل التكلفة. الخطوة فشلت؛ ده مش معناه إن حد التكلفة اتوصل له.",
    },
    "stop_on_fail": {
        "en": "Not run: this walk requested stop_on_fail after a failed step.",
        "ar": "متنفّذش: السيناريو طلب التوقف بعد فشل خطوة باستخدام stop_on_fail.",
    },
    "previous_failed": {
        "en": "The preceding action failed; its result cannot satisfy this check.",
        "ar": "الخطوة اللي قبل دي فشلت؛ نتيجتها مينفعش تنجّح الاختبار ده.",
    },
    "not_checked": {
        "en": "No Checking QS result was recorded for the current version.",
        "ar": "مفيش نتيجة مراجعة مسجلة من مهندس المراجعة للنسخة الحالية.",
    },
    "scripted": {
        "en": "Scripted-only walks require a scripted CLI session. Start with --mode scripted.",
        "ar": "الخطوات التجريبية محتاجة جلسة تجريبية. ابدأ باستخدام --mode scripted.",
    },
    "check_request": {
        "en": (
            "Ask the Checking QS to check deliverable {deliverable} at its current saved version "
            "using submit_for_check. Report the recorded outcome."
        ),
        "ar": (
            "خلّي مهندس المراجعة يراجع المُخرج {deliverable} بنسخته المحفوظة الحالية "
            "باستخدام submit_for_check، وقول نتيجة المراجعة المسجلة."
        ),
    },
    "error": {"en": "ONE could not complete this command.", "ar": "ONE مقدرش يكمّل الأمر ده."},
    "unsafe": {
        "en": "This port or data folder is reserved for ONE.",
        "ar": "البورت أو مجلد البيانات ده محجوز لـ ONE.",
    },
    "session": {
        "en": "Use a private session folder; stop an existing session first.",
        "ar": "استخدم مجلد جلسة خاص؛ وقّف الجلسة الموجودة الأول.",
    },
    "missing": {
        "en": "No CLI session. Run start or attach first.",
        "ar": "مفيش جلسة للأوامر. شغّل start أو attach الأول.",
    },
    "identity": {
        "en": "Core process identity changed; no process was stopped.",
        "ar": "هوية عملية ONE اتغيّرت؛ موقّفناش أي عملية.",
    },
    "timeout": {
        "en": "Core did not become ready; inspect its core.log.",
        "ar": "ONE مجاهزش؛ راجع core.log بتاعه.",
    },
    "cap": {
        "en": "Not run: recorded money cap reached or a real-AI price is unknown.",
        "ar": "متنفّذش: حد التكلفة المسجلة اتوصل له، أو سعر الذكاء الاصطناعي الحقيقي مش معروف.",
    },
    "sample": {"en": "Sample data — scripted AI", "ar": "بيانات عينة — ذكاء اصطناعي تجريبي"},
    "source": {"en": "Source: ONE local core; observed", "ar": "المصدر: ONE المحلي؛ وقت القراءة"},
    "answer": {
        "en": "Supply an answer for every question with --answer ID=VALUE.",
        "ar": "اكتب إجابة لكل سؤال باستخدام --answer ID=VALUE.",
    },
    "walk": {
        "en": "Invalid walk or unsupported step/check.",
        "ar": "ملف الخطوات مش صحيح أو فيه خطوة أو اختبار مش مدعوم.",
    },
}


class CliError(Exception):
    def __init__(self, code="error", *, text=None, detail=None):
        self.text = text or TEXT[code]
        self.detail = detail
        super().__init__(self.text["en"])


LABELS = {
    "pages": {"en": "Pages", "ar": "الصفحات"},
    "page": {"en": "Page", "ar": "الصفحة"},
    "bookmarks": {"en": "Bookmarks", "ar": "علامات المستند"},
    "title": {"en": "Title", "ar": "العنوان"},
    "out": {"en": "Output file", "ar": "ملف الناتج"},
    "bytes": {"en": "Bytes", "ar": "الحجم بالبايت"},
    "checked": {"en": "Current version checked", "ar": "النسخة الحالية اتراجعت"},
    "closeout": {"en": "Review outcome", "ar": "نتيجة المراجعة"},
    "versions": {"en": "Versions", "ar": "النسخ"},
    "changes": {"en": "Suggested changes", "ar": "التعديلات المقترحة"},
    "before": {"en": "Before", "ar": "قبل التعديل"},
    "op": {"en": "Proposed operation", "ar": "التعديل المقترح"},
    "changed": {"en": "Changed pages", "ar": "الصفحات المتغيّرة"},
    "added": {"en": "Added words", "ar": "الكلمات المضافة"},
    "removed": {"en": "Removed words", "ar": "الكلمات المحذوفة"},
    "pairing_note": {"en": "Pairing reason", "ar": "سبب المطابقة"},
    "comments": {"en": "Comments", "ar": "التعليقات"},
    "body": {"en": "Comment", "ar": "التعليق"},
    "today": {"en": "Today", "ar": "النهارده"},
    "tokens": {"en": "Tokens", "ar": "وحدات النص"},
    "input": {"en": "Input", "ar": "المدخلات"},
    "output": {"en": "Output", "ar": "المخرجات"},
    "cached": {"en": "Cached", "ar": "المخزّن مؤقتًا"},
    "walks": {"en": "Walks", "ar": "السيناريوهات"},
    "steps": {"en": "Steps", "ar": "الخطوات"},
    "checks": {"en": "Checks", "ar": "الاختبارات"},
    "seconds": {"en": "Seconds", "ar": "الثواني"},
    "limitations": {"en": "Coverage limitations", "ar": "حدود التغطية"},
}
