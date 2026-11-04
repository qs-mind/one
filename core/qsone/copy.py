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

# The Lead QS model list and choice (GET /settings/models, PUT /settings/model).
MODELS_FAILED = {
    "en": "The models could not be loaded because of a problem with Claude. Try again.",
    "ar": "مقدرناش نجيب النماذج بسبب مشكلة في Claude. جرّب تاني.",
}

MODEL_NOT_SAVED = {
    "en": "The model choice was not saved on this computer. Try again.",
    "ar": "اختيار النموذج ماتحفظش على الجهاز ده. جرّب تاني.",
}
