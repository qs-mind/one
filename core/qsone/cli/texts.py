"""CLI-only copy. Core replies keep their own bilingual copy."""

TEXT = {
    "stop_timeout": {
        "en": "The owned core is still shutting down. Session retained; try stop again.",
        "ar": "ONE لسه بيقفل. بيانات الجلسة موجودة؛ جرّب stop تاني.",
    },
    "review_unresolved": {
        "en": (
            "A blocking comment needs an accepted linked fix "
            "and a current Code A or B check before closing."
        ),
        "ar": (
            "الملاحظة المانعة محتاجة تعديل مقبول مربوط بيها ومراجعة حالية كود A أو B قبل ما تتقفل."
        ),
    },
    "mode_not_defined": {
        "en": "This walk does not define steps for the session's mode.",
        "ar": "السيناريو ده مفيهوش خطوات لنوع الجلسة دي.",
    },
    "deliverable_missing": {
        "en": "No Deliverable matches this step. Inspect the preceding Brief and its errors.",
        "ar": "مفيش مُخرج مطابق للخطوة دي. راجع الطلب اللي قبلها وأخطاءه.",
    },
    "brief_failed": {
        "en": "The Brief failed without a recorded error. Inspect this session's core.log.",
        "ar": "الطلب فشل من غير رسالة خطأ مسجلة. راجع core.log بتاع الجلسة دي.",
    },
    "request_timeout": {
        "en": "The core request timed out. Inspect core.log before retrying the step.",
        "ar": "وقت طلب ONE خلص. راجع core.log قبل ما تعيد الخطوة.",
    },
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


LABELS.update(
    {
        "count": {"en": "Files attempted", "ar": "عدد الملفات"},
        "read": {"en": "Read", "ar": "اتقرا"},
        "partly_read": {"en": "Partly read", "ar": "اتقرا جزء منه"},
        "failed": {"en": "Failed", "ar": "فشل"},
        "reply": {"en": "Reply", "ar": "الرد"},
        "cards": {"en": "Cards", "ar": "الكروت"},
        "id": {"en": "ID", "ar": "المعرّف"},
        "options": {"en": "Options", "ar": "الاختيارات"},
        "state": {"en": "State", "ar": "الحالة"},
        "costs": {"en": "Cost", "ar": "التكلفة"},
        "status": {"en": "Status", "ar": "الحالة"},
        "groups": {"en": "Groups", "ar": "المجموعات"},
        "files": {"en": "Files", "ar": "الملفات"},
        "kind": {"en": "Kind", "ar": "النوع"},
        "read_how": {"en": "How read", "ar": "طريقة القراءة"},
        "key_pages": {"en": "Key pages", "ar": "الصفحات المهمة"},
        "sheets": {"en": "Sheets", "ar": "اللوحات"},
        "facts": {"en": "Tender summary", "ar": "ملخص المناقصة"},
        "links": {"en": "Links", "ar": "الروابط"},
        "folder": {"en": "Folder", "ar": "الفولدر"},
        "file_id": {"en": "File ID", "ar": "معرّف الملف"},
        "name": {"en": "Name", "ar": "الاسم"},
        "value": {"en": "Value", "ar": "القيمة"},
        "locator": {"en": "Source location", "ar": "مكان المصدر"},
        "verification": {"en": "Verification", "ar": "التأكيد"},
        "sheet": {"en": "Sheet", "ar": "اللوحة"},
        "number": {"en": "Number", "ar": "الرقم"},
        "local_state": {"en": "Local reading", "ar": "القراءة المحلية"},
        "ai_state": {"en": "AI mapping", "ar": "تصنيف ONE"},
        "line": {"en": "Progress", "ar": "التقدم"},
        "next_cursor": {"en": "Next cursor", "ar": "مؤشر الصفحة الجاية"},
    }
)

VALUES = {
    "found": {"en": "read by ONE, not checked", "ar": "قراه ONE، لسه متراجعش"},
    "confirmed": {"en": "Confirmed", "ar": "متأكد"},
    "blank": {"en": "Blank", "ar": "فاضي"},
    "conflict": {"en": "Conflict", "ar": "تعارض"},
    "text": {"en": "Text", "ar": "نص"},
    "ocr": {"en": "OCR", "ar": "قراءة ضوئية"},
    "mixed": {"en": "Text and OCR", "ar": "نص وقراءة ضوئية"},
    "stored": {"en": "Stored only", "ar": "محفوظ بس"},
    "waiting": {"en": "Waiting", "ar": "مستني"},
    "reading": {"en": "Reading", "ar": "بيقرا"},
    "done": {"en": "Done", "ar": "خلص"},
    "failed": {"en": "Failed", "ar": "فشل"},
    "no_ai": {"en": "No AI connected", "ar": "مفيش ذكاء اصطناعي متوصل"},
    "local": {"en": "Mapped locally", "ar": "متصنف محلي"},
    "declined": {"en": "Mapping declined", "ar": "التصنيف اترفض"},
    "timeout": {
        "en": "Wait timed out; mapping may continue",
        "ar": "وقت الانتظار خلص؛ التصنيف ممكن يكمل",
    },
    "waiting_engineer": {"en": "Waiting for your decision", "ar": "مستني قرارك"},
}
