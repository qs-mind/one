"""Keys and model errors: the Claude key, any AI Connector, the models, Claude Code, roles."""

NO_KEY = {
    "en": "There is no Claude key yet. Add your Claude key first.",
    "ar": "لسه مفيش مفتاح Claude. ضيف مفتاح Claude بتاعك الأول.",
}

KEY_STORE_DOWN = {
    "en": (
        "The system key store is not available, so the key was not saved. "
        "Unlock it or turn it on, then try again."
    ),
    "ar": "مخزن المفاتيح في الجهاز مش متاح، فالمفتاح ماتحفظش. افتحه أو شغّله وجرّب تاني.",
}

# Undo instead of "are you sure?" (qsone.undo): pressed after its window ended.
UNDO_GONE = {
    "en": "Too late to undo: it was removed for good. Add it again if you need it.",
    "ar": "وقت التراجع خلص: اتشال خلاص. ضيفه تاني لو محتاجه.",
}

# Model errors: the engineer sees one of these; the details go to core.log only.
# The Claude key's (the Native Link's): also what AI_KEY_REFUSED says for it.
KEY_REFUSED = {
    "en": (
        "Anthropic refused this Claude key. Check that you copied all of it, "
        "or make a new key at console.anthropic.com."
    ),
    "ar": (
        "Anthropic رفض مفتاح Claude ده. اتأكد إنك نسخته كله، "
        "أو اعمل مفتاح جديد من console.anthropic.com."
    ),
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


# ---------------------------------------------------------------------------------------------
# Agent engine (Plan 4). Keep these texts together, in this block.
# {placeholders} are filled by `fill` from real data; a value may itself be an {en, ar} pair.
# Money is shown in USD with 2 decimals and Western digits.
# ---------------------------------------------------------------------------------------------

# No AI is connected at all (the chat, a Brief started from a screen, the check).
NO_AI = {
    "en": (
        "No AI is connected yet. Connect a Claude key, another AI provider or your own "
        "Claude Code, then try again."
    ),
    "ar": (
        "لسه مفيش ذكاء اصطناعي متوصّل. وصّل مفتاح Claude، أو مزوّد تاني، أو Claude Code بتاعك، "
        "وبعدين جرّب تاني."
    ),
}

# A Confidential Project while "On this computer only" is on (`ai.confidential_on_device`), and
# no model on this computer is connected: its Lead does not start (contract `LeadBlock`).
CONFIDENTIAL_NO_LOCAL_AI = {
    "en": "This Confidential Project runs only on a model on this computer, and none is connected.",
    "ar": "المشروع السري ده بيشتغل بس على موديل على الجهاز ده، ومفيش موديل متوصل.",
}

# Model errors for any AI Connector; KEY_REFUSED and the others above stay for the Native Link,
# whose refused key is KEY_REFUSED here too (`key_refused`).
AI_KEY_REFUSED = {
    "en": (
        "{provider} refused the key. Check that you copied all of it, "
        "or make a new key at {provider}."
    ),
    "ar": "{provider} رفض المفتاح. اتأكد إنك نسخته كله، أو اعمل مفتاح جديد من عند {provider}.",
}

AI_NO_CONNECTION = {
    "en": "Could not reach {provider}. Check the internet connection, then try again.",
    "ar": "مقدرناش نوصل لـ {provider}. اتأكد إن النت شغال وجرّب تاني.",
}

AI_BUSY = {
    "en": "{provider} is busy right now. Try again in a minute.",
    "ar": "في ضغط على {provider} دلوقتي. جرّب تاني كمان دقيقة.",
}

AI_FAILED = {
    "en": "The work stopped because of a problem with {provider}. The work so far is saved.",
    "ar": "الشغل وقف بسبب مشكلة في {provider}. الشغل اللي اتعمل لحد دلوقتي محفوظ.",
}
# A bug inside ONE itself: never the provider's fault (tender day, 5 Nov 2026).
CORE_FAILED = {
    "en": "The work stopped because of a problem inside ONE, not with the AI. The work so far is "
    "saved. Send the same request again; if it stops again, tell the QS Mind team.",
    "ar": "الشغل وقف بسبب مشكلة جوّه ONE نفسه، مش في الذكاء الاصطناعي. الشغل اللي اتعمل لحد "
    "دلوقتي محفوظ. ابعت نفس الطلب تاني؛ ولو وقف تاني، بلّغ فريق كيو إس مايند.",
}
# The provider's own reason, in plain words (audit B7): a model it retired, and the one it names.
MODEL_GONE_TRY = {
    "en": "{provider} says {model} is no longer available; try {other}. Pick it in AI settings.",
    "ar": (
        "{provider} بيقول إن {model} مبقاش متاح؛ جرّب {other}. اختاره من إعدادات الذكاء الاصطناعي."
    ),
}
MODEL_GONE = {
    "en": "{provider} says {model} is not available. Pick another model in AI settings.",
    "ar": "{provider} بيقول إن {model} مش متاح. اختار نموذج تاني من إعدادات الذكاء الاصطناعي.",
}

# The one tiny check (first launch, AI settings): there is no work to save yet.
AI_CHECK_SLOW = {
    "en": "{provider} did not answer within 10 seconds. Check the address and the model's name, "
    "then try again.",
    "ar": "{provider} مارَدّش في 10 ثواني. راجع العنوان واسم النموذج، وجرّب تاني.",
}
AI_CHECK_FAILED = {
    "en": "{provider} did not answer the check. Try again in a few minutes.",
    "ar": "{provider} مارَدّش على الفحص. جرّب تاني كمان كام دقيقة.",
}

# When a model does not answer. {role} is a ROLE_* pair; prices are USD per million tokens.
FALLBACK_MOVED = {
    "en": "{old} is not answering, so the {role} moved to {new}, at the same price or cheaper.",
    "ar": "{old} مش بيرد، فـ{role} اتنقل على {new}، بنفس السعر أو أرخص.",
}

FALLBACK_COSTLIER = {
    "en": (
        "{old} is not answering, and no model of the same price or cheaper is set up. "
        "Use {new} at {price_in} USD in and {price_out} USD out per million tokens?"
    ),
    "ar": (
        "{old} مش بيرد، ومفيش نموذج بنفس السعر أو أرخص متظبط. "
        "نستخدم {new} بـ {price_in} دولار للداخل و{price_out} دولار للخارج لكل مليون توكن؟"
    ),
}

WAITING_INTERNET = {
    "en": "No internet. The work is saved, and it continues by itself when the connection is back.",
    "ar": "مفيش نت. الشغل محفوظ، وهيكمّل لوحده لما النت يرجع.",
}

MODEL_STOPPED = {
    "en": "ONE stopped using {model}: {provider} says it is no longer available.",
    "ar": "ONE بطل يستخدم {model}: {provider} بيقول إنه مبقاش متاح.",
}

# The Subscription Link: the engineer's own Claude Code.
CLAUDE_CODE_MISSING = {
    "en": (
        "Claude Code was not found on this computer. Install it from "
        "https://code.claude.com/docs/en/setup and sign in to it once in a terminal, "
        "then try again."
    ),
    "ar": (
        "Claude Code مش موجود على الجهاز ده. نزّله من https://code.claude.com/docs/en/setup "
        "وسجّل دخولك فيه مرة من الـ terminal، وبعدين جرّب تاني."
    ),
}

CLAUDE_CODE_TOO_OLD = {
    "en": (
        "Your Claude Code lacks options ONE needs. Update it to the newest version, then try again."
    ),
    "ar": "Claude Code اللي عندك ناقصه اختيارات ONE محتاجها. حدّثه لآخر نسخة، وبعدين جرّب تاني.",
}

CLAUDE_CODE_SHIM = {
    "en": (
        "This is the npm claude.cmd, which ONE cannot run safely. Install the native "
        "Claude Code from https://code.claude.com/docs/en/setup, then try again."
    ),
    "ar": (
        "ده claude.cmd بتاع npm، وONE مش هيقدر يشغّله بأمان. نزّل Claude Code الأصلي من "
        "https://code.claude.com/docs/en/setup، وبعدين جرّب تاني."
    ),
}

CLAUDE_CODE_SIGNED_OUT = {
    "en": "Claude Code is signed out. Sign in to it once in a terminal, then try again.",
    "ar": "Claude Code مش مسجّل دخول. سجّل دخولك فيه مرة من الـ terminal، وبعدين جرّب تاني.",
}

CLAUDE_CODE_LIMIT = {
    "en": (
        "Your Claude subscription's limit is reached for now. "
        "ONE waits, or moves the role to another model you have."
    ),
    "ar": "اشتراك Claude بتاعك وصل لحدّه دلوقتي. ONE هيستنى، أو هينقل الدور لنموذج تاني عندك.",
}

CLAUDE_CODE_COPY = {
    "en": (
        "Claude Code keeps its own copy of each conversation on this computer, "
        "outside ONE's encrypted files."
    ),
    "ar": "Claude Code بيحتفظ بنسخة خاصة بيه من كل محادثة على الجهاز ده، برّه ملفات ONE المتشفّرة.",
}

# The roles whose model the engineer picks (glossary names).
ROLE_LEAD = {"en": "Lead QS", "ar": "كبير مهندسي الكميات"}

ROLE_CHECKER = {"en": "Checking QS", "ar": "مهندس المراجعة"}

ROLE_SPECIALIST = {"en": "Specialists", "ar": "المهندسين المتخصصين"}

ROLE_QUICK = {"en": "Quick answers", "ar": "الإجابات السريعة"}
