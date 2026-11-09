"""Spending Caps, a model with no known price, and the Brief Budget."""

# Spending Caps. {scope_name} is a SCOPE_* pair; {spent} and {cap} are USD amounts.
CAP_PAUSED = {
    "en": (
        "ONE paused at 80% of the Spending Cap for {scope_name}: {spent} of {cap} USD spent. "
        "Continue up to the cap, raise the cap, or stop with a report?"
    ),
    "ar": (
        "ONE وقّف عند 80% من سقف الصرف بتاع {scope_name}: اتصرف {spent} من {cap} دولار. "
        "نكمّل لحد السقف، ولا نرفع السقف، ولا نقف بتقرير؟"
    ),
}

CAP_STOPPED = {
    "en": (
        "The Spending Cap for {scope_name} is reached: {spent} of {cap} USD. "
        "Nothing more will be spent, and the work so far is saved."
    ),
    "ar": (
        "وصلنا لسقف الصرف بتاع {scope_name}: {spent} من {cap} دولار. "
        "مش هيتصرف حاجة تاني، والشغل اللي اتعمل لحد دلوقتي محفوظ."
    ),
}

CAP_TITLE = {"en": "Spending Cap", "ar": "سقف الصرف"}

CAPS_NOT_SAVED = {
    "en": "The Spending Caps were not saved on this computer. Try again.",
    "ar": "سقوف الصرف ماتحفظتش على الجهاز ده. جرّب تاني.",
}

# The Claude subscription is not billed per use: at 80% One only says so, unless the engineer
# turned on stopping it too.
CAP_EQUIVALENT = {
    "en": (
        "Equivalent cost on your Claude subscription has reached {spent} of the Spending Cap "
        "for {scope_name}, {cap} USD. It is not billed per use, so ONE carries on."
    ),
    "ar": (
        "التكلفة المكافئة على اشتراك Claude بتاعك وصلت {spent} من سقف الصرف بتاع {scope_name}، "
        "{cap} دولار. الاشتراك مش بيتحاسب على كل استخدام، فـONE هيكمّل."
    ),
}

SCOPE_BRIEF = {"en": "this Brief", "ar": "التكليف ده"}

SCOPE_DAY = {"en": "today", "ar": "النهارده"}

SCOPE_MONTH = {"en": "this month", "ar": "الشهر ده"}

EQUIVALENT_COST = {
    "en": "Equivalent cost on your Claude subscription (not billed per use).",
    "ar": "تكلفة مكافئة على اشتراك Claude بتاعك (مش بتتحاسب على كل استخدام).",
}

PRICE_UNKNOWN = {
    "en": (
        "ONE does not know the price of {model}. Enter its price per million tokens, and the "
        "Spending Caps count its cost. Or use it without a price: ONE then counts its tokens "
        "against the caps, a million tokens for each dollar of a cap. ONE asks once for this model."
    ),
    "ar": (
        "ONE مش عارف سعر {model}. اكتب سعره لكل مليون توكن، وسقوف الصرف هتحسب تكلفته. "
        "أو استخدمه من غير سعر: ONE ساعتها هيعدّ التوكنز بتاعته على السقوف، مليون توكن "
        "لكل دولار في السقف. ONE هيسألك مرة واحدة بس عن النموذج ده."
    ),
}
PRICE_TITLE = {"en": "A model with no known price", "ar": "نموذج سعره مش معروف"}
CAP_TOKENS_PAUSED = {
    "en": (
        "ONE paused at 80% of the Spending Cap for {scope_name}: {spent} of {cap} tokens of "
        "models with no known price. Continue up to the cap, raise the cap, or stop with a report?"
    ),
    "ar": (
        "ONE وقّف عند 80% من سقف الصرف بتاع {scope_name}: {spent} من {cap} توكن من نماذج "
        "سعرها مش معروف. تكمّل لحد السقف، ولا ترفع السقف، ولا توقف بتقرير؟"
    ),
}
CAP_TOKENS_STOPPED = {
    "en": (
        "The Spending Cap for {scope_name} is reached: {spent} of {cap} tokens of models with "
        "no known price. Nothing more will be spent, and the work so far is saved."
    ),
    "ar": (
        "وصلنا لسقف الصرف بتاع {scope_name}: {spent} من {cap} توكن من نماذج سعرها مش معروف. "
        "مش هيتصرف حاجة تاني، والشغل اللي اتعمل لحد دلوقتي محفوظ."
    ),
}

# The Brief Budget. {basis} is BASIS_MEASURED or BASIS_ASSUMED.
BUDGET_ASK = {
    "en": (
        "This Brief should cost about {usd} USD and take about {minutes} minutes ({basis}). Start?"
    ),
    "ar": "التكليف ده متوقع يكلّف حوالي {usd} دولار وياخد حوالي {minutes} دقيقة ({basis}). نبدأ؟",
}

BASIS_MEASURED = {
    "en": "measured from {n} past requests in this project",
    "ar": "محسوب من {n} طلب فات في المشروع ده",
}

BASIS_ASSUMED = {
    "en": "assumed until measured: 20,000 tokens in and 1,500 out per request",
    "ar": "تقدير لحد ما يتقاس: 20,000 توكن داخل و1,500 خارج لكل طلب",
}
