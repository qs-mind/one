"""Settings in one home (qsone.settings_registry): each setting's title, help and choices, the
refusals of PATCH /settings/{key}, the Lead's `setting` card, and the AI links that are made by
pasting a key (qsone.ai_links)."""

# Each setting, in the registry's order. A title is short: it labels a control.
SET_AI_MODELS = {"en": "Models", "ar": "الموديلات"}
SET_AI_MODELS_HELP = {
    "en": (
        "ONE takes the strongest model for the Lead QS and the check, and the cheapest for "
        "quick questions."
    ),
    "ar": "ONE بياخد أقوى موديل للـ Lead QS والمراجعة، وأرخص موديل للأسئلة السريعة.",
}
SET_MODELS_RECOMMENDED = {"en": "The recommended choice", "ar": "الاختيار الموصى به"}
SET_MODELS_OWN = {"en": "I choose a model for each role myself", "ar": "أنا أختار موديل لكل دور"}

SET_ON_DEVICE = {"en": "On this computer only", "ar": "على الجهاز ده بس"}
SET_ON_DEVICE_HELP = {
    "en": (
        "Confidential Projects run on a model on this computer. Slower and weaker, but no text "
        "leaves it."
    ),
    "ar": "المشاريع السرية بتشتغل على موديل على الجهاز ده. أبطأ وأضعف، بس مفيش نص بيخرج منه.",
}

SET_CAP_BRIEF = {"en": "One piece of work", "ar": "الشغلانة الواحدة"}
SET_CAP_BRIEF_HELP = {
    "en": "The most one piece of work may spend.",
    "ar": "أقصى صرف للشغلانة الواحدة.",
}
SET_CAP_DAY = {"en": "One day", "ar": "اليوم الواحد"}
SET_CAP_DAY_HELP = {"en": "The most ONE may spend in a day.", "ar": "أقصى صرف لـ ONE في اليوم."}
SET_CAP_MONTH = {"en": "One month", "ar": "الشهر الواحد"}
SET_CAP_MONTH_HELP = {
    "en": "The most ONE may spend in a month.",
    "ar": "أقصى صرف لـ ONE في الشهر.",
}
SET_BUDGET_ABOVE = {"en": "Ask me first above", "ar": "اسألني الأول لو أكتر من"}
SET_BUDGET_ABOVE_HELP = {
    "en": "Work expected to cost more than this asks you before it starts.",
    "ar": "أي شغل متوقع يكلّف أكتر من كده بيسألك قبل ما يبدأ.",
}
SET_MAP_AUTO = {"en": "Reading a new drop", "ar": "قراية الملفات الجديدة"}
SET_MAP_AUTO_HELP = {
    "en": "What ONE may spend reading each new drop of files without asking you.",
    "ar": "اللي ONE يقدر يصرفه على قراية كل دفعة ملفات جديدة من غير ما يسألك.",
}
SET_SUBSCRIPTION = {"en": "Count my Claude subscription", "ar": "احسب اشتراك Claude بتاعي"}
SET_SUBSCRIPTION_HELP = {
    "en": (
        "The Claude subscription is not billed per use. On: its equivalent cost counts "
        "towards the caps too, and stops work at them."
    ),
    "ar": (
        "اشتراك Claude مش بيتحاسب على كل استخدام. لو شغّال: التكلفة المكافئة بتتحسب على السقوف "
        "كمان، وبتوقف الشغل عندها."
    ),
}

SET_USAGE_STATS = {"en": "Usage Stats", "ar": "إحصائيات الاستخدام"}
SET_USAGE_STATS_HELP = {
    "en": (
        "Send the QS Mind team which parts of ONE are used, never what you write or your files."
    ),
    "ar": "ابعت لفريق كيو إس مايند أنهي أجزاء من ONE بتتستخدم، من غير أي حاجة بتكتبها أو ملفاتك.",
}

SET_LANGUAGE = {"en": "Language", "ar": "اللغة"}
SET_LANGUAGE_HELP = {
    "en": "The language ONE speaks to you in.",
    "ar": "اللغة اللي ONE بيكلمك بيها.",
}
SET_LANGUAGE_AR = {"en": "Arabic", "ar": "العربي"}
SET_LANGUAGE_EN = {"en": "English", "ar": "الإنجليزي"}
SET_THEME = {"en": "Theme", "ar": "الشكل"}
SET_THEME_HELP = {
    "en": "Light or dark, or as this computer is set.",
    "ar": "فاتح أو غامق، أو زي ما الجهاز ده متظبط.",
}
SET_THEME_SYSTEM = {"en": "As this computer", "ar": "زي الجهاز"}
SET_THEME_LIGHT = {"en": "Light", "ar": "فاتح"}
SET_THEME_DARK = {"en": "Dark", "ar": "غامق"}
SET_ZOOM = {"en": "Zoom", "ar": "التكبير"}
SET_ZOOM_HELP = {"en": "The size of everything in the window.", "ar": "حجم كل حاجة في الشاشة."}

# A value as the card shows it. {usd} is exact decimal text.
SET_TOGGLE_ON = {"en": "on", "ar": "شغّال"}
SET_TOGGLE_OFF = {"en": "off", "ar": "مقفول"}
SET_USD = {"en": "{usd} USD", "ar": "{usd} دولار"}

# PATCH /settings/{key}. {setting} is a setting's title.
SETTING_NOT_FOUND = {
    "en": "ONE has no setting by this name.",
    "ar": "مفيش إعداد في ONE بالاسم ده.",
}
SETTING_BAD_VALUE = {
    "en": "«{setting}» cannot take this value.",
    "ar": "«{setting}» مايقبلش القيمة دي.",
}
SETTINGS_NOT_SAVED = {
    "en": "The setting was not saved on this computer. Try again.",
    "ar": "الإعداد ماتحفظش على الجهاز ده. جرّب تاني.",
}

# The `setting` card: the Lead asks before a change that spends more, sends more out or weakens a
# Confidential rule. {agent} is the Lead's name; {now} and {asked} are values as shown above.
SETTING_ASK = {
    "en": "{agent} asks to change «{setting}» from {now} to {asked}. Change it?",
    "ar": "{agent} عايز يغيّر «{setting}» من {now} لـ {asked}. نغيّره؟",
}

# POST /settings/ai/connect and DELETE /settings/ai/links/{link_id}.
KEY_NOT_RECOGNISED = {
    "en": (
        "ONE does not recognise this key, so it was sent to no one. Add the provider by its "
        "address instead."
    ),
    "ar": "ONE مش عارف المفتاح ده، فمابعتهوش لحد. ضيف المزوّد بعنوانه بدل كده.",
}
AI_LINK_NOT_FOUND = {
    "en": "This AI provider is not connected.",
    "ar": "المزوّد ده مش متوصّل.",
}
AI_LINK_IN_USE = {
    "en": "Work is using this AI provider right now. Wait for it to end, or stop it.",
    "ar": "في شغل بيستخدم المزوّد ده دلوقتي. استنى لما يخلص، أو وقّفه.",
}
