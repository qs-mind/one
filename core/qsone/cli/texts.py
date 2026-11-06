"""CLI-only copy. Core replies keep their own bilingual copy."""

TEXT = {
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
        "en": "Not run: money cap, unknown price, or unavailable costs.",
        "ar": "متنفّذش: حد التكلفة، سعر مش معروف، أو سجل التكلفة مش متاح.",
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
