"""Texts the core returns to the engineer, always as {en, ar} pairs.

A text says what happened and what to do, never where on the screen to go: the same text shows in
the chat, in AI settings and in the first launch. Where the engineer can act, the screen adds the
action for its place, from `fix_of` (an "Open AI settings" button in the chat; nothing more in AI
settings themselves).
"""

import re
from dataclasses import dataclass

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

# Project Records: projects.
PROJECT_NOT_FOUND = {
    "en": "This project is not on this computer.",
    "ar": "المشروع ده مش موجود على الجهاز ده.",
}

PROJECT_NAME_TAKEN = {
    "en": "A project with this name is already on this computer. Open it, or pick another name.",
    "ar": "فيه مشروع بالاسم ده على الجهاز. افتحه، أو اختار اسم تاني.",
}

PROJECT_NOT_OPEN = {
    "en": "Open the project first.",
    "ar": "افتح المشروع الأول.",
}

PROJECT_KEY_MISSING = {
    "en": "The project's key is not in the system key store, so it cannot be opened.",
    "ar": "مفتاح المشروع مش موجود في مخزن المفاتيح في الجهاز، فمش هينفع يتفتح.",
}

PROJECT_KEY_STORE_DOWN = {
    "en": (
        "The system key store is not available, so ONE cannot use the project's key. "
        "Unlock it or turn it on, then try again."
    ),
    "ar": (
        "مخزن المفاتيح في الجهاز مش متاح، فـ ONE مش قادر يوصل لمفتاح المشروع. "
        "افتحه أو شغّله وجرّب تاني."
    ),
}

PROJECT_DAMAGED = {
    "en": (
        "The project file cannot be read (it is damaged, or the key does not match). "
        "Nothing was changed."
    ),
    "ar": "ملف المشروع مش بيتقري (يا إما بايظ، يا إما المفتاح مش مطابق). ماتغيرش فيه حاجة.",
}

PROJECT_TOO_NEW = {
    "en": "A newer version of ONE saved this project. Update ONE, then open it.",
    "ar": "المشروع ده اتحفظ بنسخة أحدث من ONE. حدّث ONE وبعدين افتحه.",
}

# Project Records: files.
FILE_TOO_BIG = {
    "en": "The file is larger than 256 MB, so it was not added.",
    "ar": "الملف أكبر من 256 ميجا، فماتضافش.",
}

FILE_EMPTY = {
    "en": "The file is empty.",
    "ar": "الملف فاضي.",
}
# After the name dropped (ui: records/RecordsPanel.tsx): the same bytes are kept once.
FILE_SAME_AS = {
    "en": "is the same file as {old}; kept once.",
    "ar": "هو نفس {old}، اتحفظ مرة واحدة.",
}
FILE_SAME_AGAIN = {
    "en": "is already here; kept once.",
    "ar": "موجود بالفعل، اتحفظ مرة واحدة.",
}

FILE_NOT_READ_YET = {
    "en": "Kept in Project Records. ONE cannot read this kind of file yet.",
    "ar": "اتحفظ في سجلات المشروع. ONE لسه مش بيقرا النوع ده من الملفات.",
}

FILE_SCANNED_PAGES = {
    "en": "Some pages have no text layer (they are scanned), so they cannot be searched yet.",
    "ar": "في صفحات مفيهاش نص (متصورة سكانر)، فلسه مش هينفع ندوّر فيها.",
}

FILE_UNREADABLE = {
    "en": "Kept, but ONE could not read it (it is damaged, or locked with a password).",
    "ar": "اتحفظ، بس ONE مقدرش يقراه (يا إما بايظ، يا إما مقفول بباسورد).",
}

FILE_LOCKED = {
    "en": "Kept, but it is locked with a password, so ONE cannot read it. Save an open copy "
    "(without the password) and add that one.",
    "ar": "اتحفظ، بس مقفول بباسورد فـ ONE مش قادر يقراه. احفظ نسخة مفتوحة (من غير الباسورد) "
    "وضيفها.",
}

FILE_SHEETS_EMPTY = {
    "en": "Read: its sheets are empty, so there is nothing in it.",
    "ar": "اتقرا: الشيتات بتاعته فاضية، مفيهوش حاجة.",
}

FILE_NOT_FOUND = {
    "en": "This file is not in Project Records.",
    "ar": "الملف ده مش موجود في سجلات المشروع.",
}

# The workspace.
WORKSPACE_BAD = {
    "en": "The open document was not saved: ONE does not know its name.",
    "ar": "المستند المفتوح ما اتحفظش: ONE مش عارف اسمه.",
}
CLIENT_BOQ_NOT_FOUND = {
    "en": "No BOQ was imported from this file.",
    "ar": "مفيش مقايسة اتستوردت من الملف ده.",
}
# The Checking QS's comment on a Priced BOQ row whose item is not in the client's BOQ.
NOT_IN_CLIENT_BOQ = {
    "en": "Not in the client's BOQ: {code} {description}. Keep it or remove it?",
    "ar": "البند ده مش موجود في مقايسة العميل: {code} {description}. تسيبه ولا تشيله؟",
}

PAGE_NOT_FOUND = {
    "en": "The file has no page with this number.",
    "ar": "الملف مفيهوش صفحة بالرقم ده.",
}

FILE_HAS_NO_PAGES = {
    "en": "Only a PDF file shows its pages; this file shows its text.",
    "ar": "ملف الـ PDF بس هو اللي بيعرض صفحاته؛ الملف ده بيعرض النص بتاعه.",
}

PROJECT_IS_CONFIDENTIAL = {
    "en": "This is a Confidential Project, so the General chat cannot hand anything to it.",
    "ar": "ده مشروع سري، فالشات العام مايقدرش يحوّل له أي حاجة.",
}

CHAT_BAD_SELECTION = {
    "en": "What was selected in the open document could not be read, so the message was not sent.",
    "ar": "اللي اتحدد في المستند المفتوح ماتقراش، فالرسالة ماتبعتتش.",
}

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

# Project Records: the Source Ledger.
NUMBER_NOT_EXACT = {
    "en": (
        "Send the number as text: digits and one decimal point, no thousands separators, "
        "e.g. 39850.50."
    ),
    "ar": "ابعت الرقم كنص: أرقام وعلامة عشرية واحدة، من غير فواصل آلاف، زي 39850.50.",
}

NUMBER_NEEDS_UNIT = {
    "en": "This number needs a unit.",
    "ar": "الرقم ده محتاج وحدة.",
}

NUMBER_NEEDS_CURRENCY = {
    "en": "This number needs a currency: three letters, e.g. EGP, SAR, AED.",
    "ar": "الرقم ده محتاج عملة: تلات حروف، زي EGP أو SAR أو AED.",
}

NUMBER_NEEDS_SOURCE = {
    "en": "This number needs a source.",
    "ar": "الرقم ده محتاج مصدر.",
}

NUMBER_NEEDS_DATE = {
    "en": "This number needs the date it is true for, as YYYY-MM-DD.",
    "ar": "الرقم ده محتاج التاريخ اللي هو صحيح فيه، بالشكل YYYY-MM-DD.",
}

CORRECTION_NEEDS_REASON = {
    "en": "A correction needs a reason.",
    "ar": "التصحيح محتاج سبب.",
}

ALREADY_CORRECTED = {
    "en": "This number was already corrected. Correct the newest entry instead.",
    "ar": "الرقم ده اتصحح قبل كده. صحّح آخر قيمة بدل منه.",
}

# The reason stored when a newer number of the same name on an item takes the older one's place.
NUMBER_SUPERSEDED = {
    "en": "A newer number of the same name was recorded for this item.",
    "ar": "اتسجّل رقم أحدث بنفس الاسم للبند ده.",
}

# A tool refused an agent's call: the engineer sees why in the work log. {why}: the refusal's
# first sentence.
TOOL_REFUSED = {
    "en": "ONE refused this step: {why} The team is fixing it; if it keeps happening, tell the "
    "Lead QS what to do.",
    "ar": "ONE رفض الخطوة دي: {why} الفريق بيصلّحها؛ ولو اتكررت، قول لكبير مهندسي الكميات يعمل إيه.",
}

# A row whose item has two current numbers of one name (written before 5 Nov 2026).
# {name}: a BOQ_FIELDS label; {values}: the values, joined.
# The close card: a Deliverable that is not right, with the first row that says why.
CLOSE_ROW_PROBLEM = {"en": "Item {code}: {problem}", "ar": "البند {code}: {problem}"}

ROW_NUMBERS_CONFLICT = {
    "en": "This item has {n} different «{name}» values recorded: {values}. Type the right one in "
    "this row and ONE keeps that one only.",
    "ar": "البند ده متسجّل له {n} قيم مختلفة لـ«{name}»: {values}. اكتب القيمة الصح في الصف ده "
    "وONE هيحتفظ بيها لوحدها.",
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

# Approvals. {agent} is the agent's name; {action} its Progress Line words.
ASK_OUTSIDE = {
    "en": "{agent}: {action}. This leaves this computer. Allow it?",
    "ar": "{agent}: {action}. ده هيطلع برّه الجهاز ده. نسمح بيه؟",
}

ASK_ONLINE = {
    "en": (
        "{agent}: {action}. This goes online after reading project files, "
        "and text in files can hide instructions. Allow it?"
    ),
    "ar": (
        "{agent}: {action}. ده هيدخل على النت بعد ما قرا ملفات المشروع، "
        "والنص اللي في الملفات ممكن يكون مستخبي فيه أوامر. نسمح بيه؟"
    ),
}

# Progress Line words of the tools. {tool} is a tool's name; the other values come from its call.
# What a step is, for the Progress Line, when the tool has no words of its own for its arguments:
# never the tool's id. Every registered tool has its line here (tests/test_arabic.py checks it).
TOOL_STEP = {"en": "Working on a step", "ar": "بيشتغل على خطوة"}
TOOL_WORDS = {
    "add_item": {"en": "Adding an item to the Source Ledger", "ar": "بيضيف بند لسجل المصادر"},
    "add_source": {"en": "Adding a source to the Source Ledger", "ar": "بيضيف مصدر لسجل المصادر"},
    "ask_engineer": {"en": "Asking you a question", "ar": "بيسألك سؤال"},
    "boq_import": {"en": "Importing the BOQ", "ar": "بيستورد جدول الكميات"},
    "boq_price_from_sheet": {
        "en": "Pricing the BOQ from the build-up sheet",
        "ar": "بيسعّر المقايسة من شيت التسعير",
    },
    "boq_preview": {"en": "Looking at the BOQ's columns", "ar": "بيشوف أعمدة جدول الكميات"},
    "build_specialist": {"en": "Setting up a specialist", "ar": "بيجهّز متخصص"},
    "calculate": {"en": "Calculating a number", "ar": "بيحسب رقم"},
    "client_file_plan": {
        "en": "Planning how to fill the client's file",
        "ar": "بيخطط إزاي يملا ملف العميل",
    },
    "client_file_read": {"en": "Reading the client's file", "ar": "بيقرا ملف العميل"},
    "connector_call": {"en": "Using a connected app", "ar": "بيستخدم تطبيق متوصّل"},
    "connector_tools": {
        "en": "Looking at what the connected apps can do",
        "ar": "بيشوف التطبيقات المتوصّلة تقدر تعمل إيه",
    },
    "correct_number": {"en": "Correcting a number", "ar": "بيصحّح رقم"},
    "define_unit": {"en": "Defining a project unit", "ar": "بيعرّف وحدة للمشروع"},
    "delegate": {"en": "Handing work to the team", "ar": "بيسلّم شغل للفريق"},
    "deliverable_comment": {"en": "Commenting on a Deliverable", "ar": "بيعلّق على مُخرج"},
    "deliverable_create": {"en": "Making a Deliverable", "ar": "بيعمل مُخرج"},
    "deliverable_propose": {
        "en": "Suggesting changes to a Deliverable",
        "ar": "بيقترح تعديلات على مُخرج",
    },
    "deliverable_read": {"en": "Reading a Deliverable", "ar": "بيقرا مُخرج"},
    "explain_number": {"en": "Tracing where a number comes from", "ar": "بيتتبّع مصدر رقم"},
    "files_list": {"en": "Looking at the project files", "ar": "بيشوف ملفات المشروع"},
    "project_map": {"en": "Reading the project map", "ar": "بيقرا خريطة المشروع"},
    "files_read": {"en": "Reading a project file", "ar": "بيقرا ملف من ملفات المشروع"},
    "find_items": {"en": "Looking up items", "ar": "بيدوّر على بنود"},
    "hand_to_project": {"en": "Passing the work to a project", "ar": "بيحوّل الشغل لمشروع"},
    "ledger_numbers": {"en": "Reading the project's numbers", "ar": "بيقرا أرقام المشروع"},
    "rank_items": {"en": "Sorting the project's items", "ar": "بيرتّب بنود المشروع"},
    "make_deliverable": {"en": "Making a Deliverable", "ar": "بيعمل مُخرج"},
    "note_lesson": {"en": "Noting a lesson learned", "ar": "بيسجّل درس مستفاد"},
    "offer_new_project": {"en": "Suggesting a new project", "ar": "بيقترح مشروع جديد"},
    "plan_brief": {"en": "Planning the work", "ar": "بيخطط للشغل"},
    "prices_lookup": {"en": "Looking up market prices", "ar": "بيدوّر على أسعار السوق"},
    "prices_propose": {"en": "Proposing prices for you to keep", "ar": "بيقترح أسعار تحفظها"},
    "projects": {"en": "Looking at your projects", "ar": "بيشوف المشاريع"},
    "read_chunk": {
        "en": "Reading a passage of the project files",
        "ar": "بيقرا جزء من ملفات المشروع",
    },
    "recalculate": {"en": "Recalculating numbers", "ar": "بيعيد حساب الأرقام"},
    "record_number": {"en": "Recording a number", "ar": "بيسجّل رقم"},
    "sandbox_rerun": {"en": "Running a script again", "ar": "بيشغّل سكريبت تاني"},
    "sandbox_run": {"en": "Running a script", "ar": "بيشغّل سكريبت"},
    "save_desk": {"en": "Saving a Desk", "ar": "بيحفظ قسم"},
    "search_records": {"en": "Searching the project files", "ar": "بيدوّر في ملفات المشروع"},
    "send_message": {"en": "Sending a message to the team", "ar": "بيبعت رسالة للفريق"},
    "show": {"en": "Laying out a view for you", "ar": "بيجهّزلك عرض"},
    "submit_for_check": {
        "en": "Sending work to the Checking QS",
        "ar": "بيبعت الشغل لمهندس المراجعة",
    },
    "understood": {
        "en": "Filling in the “I understood this” card",
        "ar": "بيملا بطاقة «فهمت كده»",
    },
    "use_desk": {"en": "Calling on a Desk", "ar": "بيستعين بقسم"},
    "web_read": {"en": "Reading a web page", "ar": "بيقرا صفحة ويب"},
    "open_tools": {"en": "Getting tools ready", "ar": "بيجهّز أدواته"},
    "compare_files": {"en": "Comparing file revisions", "ar": "بيقارن نسخ الملفات"},
    "pack_propose": {"en": "Arranging the tender pack", "ar": "بيرتّب ملف المناقصة"},
    "web_search": {"en": "Searching the web", "ar": "بيدوّر على الويب"},
}


def tool_step(name: str) -> dict[str, str]:
    """The Progress Line's words for a step of tool `name`: its own line, or a plain one."""
    return TOOL_WORDS.get(name, TOOL_STEP)


TOOL_SEARCH_RECORDS = {
    "en": "Searching the project files for «{query}»",
    "ar": "بيدوّر في ملفات المشروع على «{query}»",
}

TOOL_READ_CHUNK = {
    "en": "Reading a passage of the project files",
    "ar": "بيقرا جزء من ملفات المشروع",
}

TOOL_FIND_ITEMS = {
    "en": "Looking up items in the Source Ledger",
    "ar": "بيدوّر على بنود في سجل المصادر",
}

TOOL_RANK_ITEMS = {
    "en": "Finding the top {top} items by {name}",
    "ar": "بيطلّع أعلى {top} بنود في {name}",
}
TOOL_LEDGER_NUMBERS = {
    "en": "Reading the numbers of item {item}",
    "ar": "بيقرا أرقام البند {item}",
}

TOOL_ADD_SOURCE = {
    "en": "Adding the source «{title}» to the Source Ledger",
    "ar": "بيضيف المصدر «{title}» لسجل المصادر",
}

TOOL_ADD_ITEM = {
    "en": "Adding an item to the Source Ledger",
    "ar": "بيضيف بند لسجل المصادر",
}

TOOL_RECORD_NUMBER = {
    "en": "Recording the {name} of item {item}, with its source",
    "ar": "بيسجّل {name} للبند {item} بمصدره",
}

TOOL_CORRECT_NUMBER = {
    "en": "Correcting a number, keeping the old one",
    "ar": "بيصحّح رقم، والرقم القديم محفوظ",
}

CONTINUE_BRIEF = {
    "en": "This Brief stopped at: {step}. Continue it?",
    "ar": "التكليف ده وقف عند: {step}. نكمّله؟",
}

STOPPED = {
    "en": "Stopped. The work so far is saved.",
    "ar": "وقفنا. الشغل اللي اتعمل لحد دلوقتي محفوظ.",
}
# The engineer pressed Stop: what the Brief's records show it changed before it stopped.
STOPPED_NOTHING = {"en": "Stopped. Nothing was changed.", "ar": "وقفت. ماتغيرش حاجة."}
STOPPED_CHANGED = {
    "en": "Stopped. What changed before the stop is kept: {changes}.",
    "ar": "وقفت. اللي اتغيّر قبل ما أقف محفوظ: {changes}.",
}  # {changes}: counted(n, CHANGES)

DESK_SAVE = {
    "en": "Keep “{desk}” as a Draft Desk for next time?",
    "ar": "نحتفظ بـ«{desk}» كقسم مسودة للمرة الجاية؟",
}

DISAGREEMENT = {
    "en": (
        "After two rounds, the Checking QS and {agent} still disagree. "
        "Both views and their evidence are below; you decide."
    ),
    "ar": "بعد جولتين، مهندس المراجعة و{agent} لسه مختلفين. الرأيين ودليل كل واحد تحت؛ القرار ليك.",
}

SAME_PROVIDER = {
    "en": (
        "Same-provider check: the Checking QS also runs on {provider}. "
        "Add a second AI provider for a stronger check."
    ),
    "ar": (
        "مراجعة من نفس الشركة: مهندس المراجعة شغال برضه على {provider}. "
        "ضيف مزوّد ذكاء اصطناعي تاني عشان المراجعة تبقى أقوى."
    ),
}

NO_SOURCE = {
    "en": "Some numbers have no source yet; they are marked.",
    "ar": "في أرقام لسه ملهاش مصدر؛ متعلّم عليها.",
}

# The team (Plan 4, Task 7). {name} and {desk} are {en, ar} pairs; {title} is a Deliverable's.
BUDGET_TITLE = {"en": "Brief Budget", "ar": "ميزانية التكليف"}
BUDGET_SPENT = {
    "en": "This Brief has spent {spent} USD so far and is about to pass {line} USD. Go on?",
    "ar": "التكليف ده صرف لحد دلوقتي {spent} دولار، وقرّب يعدّي {line} دولار. نكمّل؟",
}

BUDGET_UNKNOWN = {
    "en": (
        "ONE cannot tell what this Brief will cost: a model in its plan has no known price. "
        "It should take about {minutes} minutes. Start?"
    ),
    "ar": (
        "ONE مش عارف التكليف ده هيكلّف كام: في نموذج في الخطة سعره مش معروف. "
        "متوقع ياخد حوالي {minutes} دقيقة. نبدأ؟"
    ),
}

DESK_TITLE = {"en": "Draft Desk", "ar": "قسم مسودة"}

DISAGREEMENT_TITLE = {"en": "The Checking QS disagrees", "ar": "مهندس المراجعة مش موافق"}

DISAGREEMENT_CHECKER = {
    "en": "Checking QS, round {round}, Code {code}:",
    "ar": "مهندس المراجعة، الجولة {round}، كود {code}:",
}

DISAGREEMENT_MAKER = {
    "en": "{agent}'s Deliverable, as it stands:",
    "ar": "المُخرَج بتاع {agent} زي ما هو:",
}

DISAGREEMENT_ASK = {
    "en": "Keep the Deliverable as it is? “No” sends it back to be fixed as the Checking QS says.",
    "ar": "نسيب المُخرَج زي ما هو؟ «لأ» يرجّعه يتصلّح زي ما مهندس المراجعة قال.",
}

TOOL_PLAN_BRIEF = {"en": "Planning the Brief", "ar": "بيخطّط للتكليف"}

TOOL_BUILD_SPECIALIST = {
    "en": "Building a specialist: {name}",
    "ar": "بيجهّز مهندس متخصص: {name}",
}

TOOL_DELEGATE = {"en": "Handing work to a specialist", "ar": "بيسلّم شغل لمهندس متخصص"}

TOOL_SEND_MESSAGE = {"en": "Sending a message to the team", "ar": "بيبعت رسالة للفريق"}

TOOL_MAKE_DELIVERABLE = {
    "en": "Making the Deliverable «{title}»",
    "ar": "بيعمل المُخرَج «{title}»",
}

TOOL_SUBMIT_FOR_CHECK = {
    "en": "Sending a Deliverable to the Checking QS",
    "ar": "بيبعت مُخرَج لمهندس المراجعة",
}

TOOL_SAVE_DESK = {
    "en": "Offering to keep the Desk «{desk}»",
    "ar": "بيعرض نحتفظ بالقسم «{desk}»",
}

TOOL_USE_DESK = {"en": "Opening a saved Desk", "ar": "بيفتح قسم محفوظ"}

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

# The Brief Runner (Plan 4, Task 8): the step a Brief is at, shown in "Continue Brief?".
STEP_QUEUED = {
    "en": "waiting for another Brief to finish",
    "ar": "مستني تكليف تاني يخلص",
}

STEP_STARTED = {"en": "the Lead QS started", "ar": "كبير مهندسي الكميات بدأ"}

STEP_WAITING = {"en": "waiting for your answer: {title}", "ar": "مستني ردّك: {title}"}

STEP_CHECKING = {
    "en": "the Checking QS is checking the work",
    "ar": "مهندس المراجعة بيراجع الشغل",
}

STEP_DONE = {"en": "done", "ar": "خلص"}

DESK_TEMPORARY = {"en": "Temporary Desk", "ar": "قسم مؤقت"}

CONTINUE_AFTER_RESTART = "ONE restarted. Continue from your last step."  # the model reads it

STEP_LIMIT_NOW = (  # the model reads it: the last request after ONE's step limit
    "ONE's step limit for one request is reached, so the work stops now. Without calling any "
    "tool, reply with what you found so far, with its sources, and what is left."
)
STEP_LIMIT_REACHED = {
    "en": "ONE stopped this request at its limit of {n} steps, with what the Lead QS found so "
    "far. Ask for less at a time (one section, or the top items) to go on.",
    "ar": "ONE وقّف الطلب ده عند حدّه: {n} خطوة، ومعاه اللي كبير مهندسي الكميات لقاه لحد "
    "دلوقتي. اطلب حاجة أصغر في المرة (قسم واحد، أو أعلى البنود) عشان نكمّل.",
}
# ONE's own refusals, repeated until the model gave up: never the provider's fault (6 Nov 2026).
TOOL_GAVE_UP = {
    "en": "The work stopped: ONE refused the same step {n} times, so it was not done. Why: {why} "
    "The work so far is saved; tell the Lead QS how to go on.",
    "ar": "الشغل وقف: ONE رفض نفس الخطوة {n} مرات، فماتعملتش. السبب: {why} الشغل اللي اتعمل "
    "لحد دلوقتي محفوظ؛ قول لكبير مهندسي الكميات يكمّل إزاي.",
}
REPLY_GAVE_UP = {
    "en": "The work stopped: ONE sent the Lead QS's answer back to be fixed several times, and it "
    "could not fix it. The work so far is saved; ask again in fewer words.",
    "ar": "الشغل وقف: ONE رجّع رد كبير مهندسي الكميات يتصلّح كذا مرة، وماعرفش يصلّحه. الشغل "
    "اللي اتعمل لحد دلوقتي محفوظ؛ اطلب تاني بكلام أقل.",
}
REPORT_NOW = (  # the model reads it: the last request after the engineer chose "stop with a report"
    "The Spending Cap stops the work now. Without calling any tool, reply with a short report: "
    "what is done, with its sources, and what is left."
)

BRIEF_BUSY = {
    "en": "This chat already has a Brief running. Your message steers it.",
    "ar": "في تكليف شغال في الشات ده. رسالتك هتوجّهه.",
}

BRIEF_NOT_RUNNING = {
    "en": "This Brief is not running now.",
    "ar": "التكليف ده مش شغال دلوقتي.",
}

BRIEF_NOT_FOUND = {
    "en": "This Brief is not on this computer, or it is already finished.",
    "ar": "التكليف ده مش على الجهاز ده، أو خلص خلاص.",
}

CHAT_MODEL_GONE = {
    "en": "The model picked in the message box is no longer there. Pick another and send again.",
    "ar": "الموديل اللي اخترته في مربع الرسالة مابقاش متاح. اختار غيره وابعت تاني.",
}

CHAT_EMPTY = {
    "en": "The message is empty. Write what you need, then send it.",
    "ar": "الرسالة فاضية. اكتب اللي محتاجه وابعتها.",
}

CARD_GONE = {
    "en": "This question was already answered or withdrawn.",
    "ar": "السؤال ده اتجاوب عليه أو اتسحب.",
}

CARD_CHOICE = {
    "en": "That is not one of this card's choices.",
    "ar": "ده مش من اختيارات الكارت ده.",
}


# ---------------------------------------------------------------------------------------------
# QS Calc Engine (Plan 3). Keep these texts together, in this block.
# Texts with values use {name} placeholders filled by `fill`; literal braces are doubled.
# ---------------------------------------------------------------------------------------------


_EXTENSION = re.compile(r"(\.[A-Za-z0-9]{1,8})$")


_ARABIC_LETTERS = r"\u0600-\u06FF\u0750-\u077F\u0870-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF"
_ARABIC = re.compile(f"[{_ARABIC_LETTERS}]")
_STRONG = re.compile(f"[A-Za-z\u00c0-\u024f{_ARABIC_LETTERS}]")
_LATIN = re.compile(r"[A-Za-z]")


def file_name(name: str) -> str:
    """A file name for a sentence on screen, in Unicode isolates: the whole name first-strong
    (FSI … PDI), a lone extension in the name's direction (so its dot stays by an Arabic name, never
    «عينةxlsx.»). A name that starts in Arabic and ends in Latin words keeps those words with the
    extension as one left-to-right run (LRI … PDI), so
    «مواصفات (sample spec).docx» reads «مواصفات» then «(sample spec).docx» inside Arabic or
    English words, never «.docx(sample spec». Only for text shown to the engineer, never to a
    model. The UI's own file names do the same (ui/src/ui/FileName.tsx)."""
    found = _EXTENSION.search(name)
    whole = found is None or found.start() == 0
    stem, extension = (name, "") if whole else (name[: found.start()], found.group(1))
    first = _STRONG.search(stem)
    last = max((m.end() for m in _ARABIC.finditer(stem)), default=0)
    rest = stem[last:]
    if first and _ARABIC.match(first.group()) and last and _LATIN.search(rest):
        space = len(rest) - len(rest.lstrip())
        return f"\u2068{stem[: last + space]}\u2066{rest[space:]}{extension}\u2069\u2069"
    return f"\u2068{stem}{extension}\u2069"


_BLANK_THEN_STOP = re.compile(r"\{(\w+)\}\.")
_ISOLATES = "⁦⁧⁨⁩ "


def _one_stop(s: str, values: dict) -> str:
    """A value that ends a sentence itself («…شيت BOQ؟») takes the place of the full stop after
    its blank, never «؟.»."""

    def keep(m: re.Match) -> str:
        value = str(values.get(m[1], "")).rstrip(_ISOLATES)
        return m[0][:-1] if value[-1:] in (".", "?", "!", "؟", "…") else m[0]

    return _BLANK_THEN_STOP.sub(keep, s)


def fill(text: dict[str, str], /, **values) -> dict[str, str]:
    """Both languages of `text` with its {placeholders} filled from `values`.

    A value that is itself an {en, ar} pair gives each language its own words."""
    found = {}
    for lang, s in text.items():
        mine = {k: v[lang] if isinstance(v, dict) else v for k, v in values.items()}
        found[lang] = _one_stop(s, mine).format(**mine)
    return found


def words_for(said: str) -> dict[str, str] | None:
    """The {en, ar} text whose English words `said` holds (a refusal the model was given in
    English), the longest that fits; None when no text of this module, without blanks, is in it."""
    found = None
    for value in globals().values():
        if (
            isinstance(value, dict)
            and isinstance(value.get("en"), str)
            and isinstance(value.get("ar"), str)
            and "{" not in value["en"]
            and len(value["en"]) >= 20
            and value["en"] in said
            and (found is None or len(value["en"]) > len(found["en"]))
        ):
            found = value
    return found


def _arabic_form(n: int) -> str:
    """Egyptian Arabic counting: بند واحد، بندين، 3 إلى 10 بنود، 11 فأكتر بند."""
    if n == 1:
        return "one"
    if n == 2:
        return "two"
    return "few" if 3 <= n % 100 <= 10 else "other"


@dataclass(frozen=True)
class Noun:
    """A counted noun's forms, each with {n}: English "one" and "other"; Arabic "one", "two",
    "few" (3 to 10) and "other"."""

    en: dict[str, str]
    ar: dict[str, str]


def counted(n: int, noun: Noun) -> dict[str, str]:
    """`n` with its noun in each language's own form. A value for `fill`."""
    return {
        "en": noun.en["one" if n == 1 else "other"].format(n=n),
        "ar": noun.ar[_arabic_form(n)].format(n=n),
    }


ITEMS = Noun(
    en={"one": "1 item", "other": "{n} items"},
    ar={"one": "بند واحد", "two": "بندين", "few": "{n} بنود", "other": "{n} بند"},
)
HEADINGS = Noun(
    en={"one": "1 heading", "other": "{n} headings"},
    ar={"one": "عنوان واحد", "two": "عنوانين", "few": "{n} عناوين", "other": "{n} عنوان"},
)
ROWS = Noun(
    en={"one": "1 row", "other": "{n} rows"},
    ar={"one": "صف واحد", "two": "صفين", "few": "{n} صفوف", "other": "{n} صف"},
)
CHANGES = Noun(
    en={"one": "1 change", "other": "{n} changes"},
    ar={"one": "تغيير واحد", "two": "تغييرين", "few": "{n} تغييرات", "other": "{n} تغيير"},
)
SECTIONS = Noun(
    en={"one": "1 section", "other": "{n} sections"},
    ar={"one": "قسم واحد", "two": "قسمين", "few": "{n} أقسام", "other": "{n} قسم"},
)
FILES = Noun(
    en={"one": "1 file", "other": "{n} files"},
    ar={"one": "ملف واحد", "two": "ملفين", "few": "{n} ملفات", "other": "{n} ملف"},
)

# What ONE found in a drop of files, in the project chat (records/report.py). Every number in it
# is read by the core, with the sheet, rows and cell it comes from.
REPORT_HEAD = {"en": "ONE read {files}:", "ar": "ONE قرا {files}:"}
REPORT_FILE = {"en": "{name}: {label}.", "ar": "{name}: {label}."}
REPORT_NOT_READ = {"en": "{name}: {note}", "ar": "{name}: {note}"}
REPORT_TABLES_NOT_READ = {
    "en": "ONE could not read the tables in this file; no BOQ row count is available yet.",
    "ar": "ONE ماقدرش يقرا الجداول في الملف ده؛ عدد بنود المقايسة لسه مش معروف.",
}
REPORT_PDF_PAGES = {"en": "PDF: {pages} pages.", "ar": "ملف PDF: {pages} صفحة."}
REPORT_PDF_UNREAD = {
    "en": "No text on pages: {pages}. These pages still need reading from their images.",
    "ar": "الصفحات دي مفيهاش نص: {pages}. لسه محتاجة تتقري من صورها.",
}
REPORT_PDF_BOQ = {
    "en": "The PDF tables show {rows} BOQ rows; these have not been imported by this report.",
    "ar": "جداول الـ PDF فيها {rows} بند مقايسة؛ التقرير ده ما استوردش البنود.",
}

REPORT_BOQ_SHEET = {
    "en": "Sheet «{sheet}»: {items} in {sections} (rows {first}–{last}).",
    "ar": "شيت «{sheet}»: {items} في {sections} (الصفوف {first}–{last}).",
}
REPORT_TOTAL = {
    "en": "Its own total: {total} (row {row}, column {column}).",
    "ar": "إجماليه في الملف: {total} (صف {row}، عمود {column}).",
}
REPORT_NO_TOTAL = {"en": "No total row in it.", "ar": "مفيش فيه صف إجمالي."}
REPORT_MISSING = {
    "en": "Not among the project's files yet: {missing}.",
    "ar": "لسه مش موجود في ملفات المشروع: {missing}.",
}
REPORT_LABELS = {
    "boq": {"en": "BOQ", "ar": "مقايسة"},
    "specs": {"en": "Specifications", "ar": "مواصفات"},
    "conditions": {"en": "Conditions of contract", "ar": "شروط التعاقد"},
    "quote": {"en": "Quotation", "ar": "عرض سعر"},
    "drawings": {"en": "Drawings", "ar": "رسومات"},
    "price_list": {"en": "Price list", "ar": "قائمة أسعار"},
    "sheet": {"en": "Spreadsheet, not a BOQ", "ar": "شيت إكسل، مش مقايسة"},
    "image": {"en": "Image", "ar": "صورة"},
    "document": {"en": "Document; ONE could not tell its kind", "ar": "مستند؛ ONE مقدرش يعرف نوعه"},
}


def listed(values: list[str]) -> dict[str, str]:
    """A short list of values in each language: «أ، ب» in Arabic, "a, b" in English."""
    return {"en": ", ".join(values), "ar": "، ".join(values)}


# The formula.
CALC_UNEXPECTED = {
    "en": (
        "At character {at}, «{found}» was not expected; ONE expected {expected}. "
        "Numbers have no thousands separators."
    ),
    "ar": (
        "عند الحرف {at}، «{found}» مش مكانه هنا؛ ONE كان مستني {expected}. "
        "الأرقام من غير فواصل آلاف."
    ),
}

CALC_TOO_LONG = {
    "en": "The formula is longer than 4,000 characters. Split it into steps saved one by one.",
    "ar": "المعادلة أطول من 4000 حرف. قسّمها لخطوات تتحفظ واحدة واحدة.",
}

CALC_TOO_DEEP = {
    "en": "The formula nests more than 50 brackets or calls deep.",
    "ar": "المعادلة فيها أقواس أو دوال جوه بعض أكتر من 50 مستوى.",
}

CALC_UNKNOWN_NAME = {
    "en": (
        "«{name}» is not an input. Inputs: {names}. Add it to `inputs`, "
        'e.g. `"{name}": {{"item": "03/02", "name": "rate"}}`.'
    ),
    "ar": (
        "«{name}» مش من المدخلات. المدخلات: {names}. ضيفه في `inputs`، "
        'زي `"{name}": {{"item": "03/02", "name": "rate"}}`.'
    ),
}

CALC_UNKNOWN_FUNCTION = {
    "en": (
        "«{name}» is not a function. "
        "Functions: sum, count, avg, min, max, round, abs, sqrt, to, if."
    ),
    "ar": "«{name}» مش دالة. الدوال: sum، count، avg، min، max، round، abs، sqrt، to، if.",
}

CALC_USAGE = {
    "en": "Use {fn} like this: {usage}.",
    "ar": "استخدم {fn} كده: {usage}.",
}

CALC_LIST_HERE = {
    "en": "«{name}» is a list; use it inside sum, count, avg, min or max.",
    "ar": "«{name}» قايمة؛ استخدمها جوه sum أو count أو avg أو min أو max.",
}

CALC_POWER = {
    "en": "A power must be a whole number from -12 to 12, e.g. `side^2`.",
    "ar": "الأس لازم يكون رقم صحيح من -12 لـ 12، زي `side^2`.",
}

CALC_SQRT = {
    "en": "sqrt needs a value of zero or more whose unit powers are even, e.g. `sqrt(a^2 + b^2)`.",
    "ar": "sqrt محتاجة قيمة صفر أو أكتر، وأسس وحدتها زوجية، زي `sqrt(a^2 + b^2)`.",
}

CALC_DIVIDE_BY_ZERO = {
    "en": "«{text}» divides by zero.",
    "ar": "«{text}» فيها قسمة على صفر.",
}

CALC_TOO_BIG = {
    "en": "A value in «{text}» is too large to compute exactly.",
    "ar": "في قيمة في «{text}» أكبر من إنها تتحسب بالظبط.",
}

# Units and currencies.
CALC_UNITS_DIFFER = {
    "en": (
        "«{left}» and «{right}» cannot be added, compared or converted: their units do not match."
    ),
    "ar": "«{left}» و«{right}» مينفعش يتجمعوا أو يتقارنوا أو يتحوّلوا لبعض: وحداتهم مش متطابقة.",
}

CALC_CURRENCIES_DIFFER = {
    "en": (
        "{left} and {right} are different currencies. Multiply by an exchange rate from the "
        "Source Ledger, a number with unit {left}/{right}."
    ),
    "ar": (
        "{left} و{right} عملتين مختلفتين. اضرب في سعر صرف من سجل المصادر، رقم وحدته {left}/{right}."
    ),
}

CALC_RESULT_UNIT = {
    "en": "The formula gives {got}, not {want}. Check the formula or `result.unit`.",
    "ar": "المعادلة بتطلّع {got} مش {want}. راجع المعادلة أو `result.unit`.",
}

CALC_UNIT_UNREADABLE = {
    "en": "The unit «{unit}» cannot be read. Write it like m3, kg/m3, EGP/m3 or m3/day.",
    "ar": "الوحدة «{unit}» مش مفهومة. اكتبها زي m3 أو kg/m3 أو EGP/m3 أو m3/day.",
}

CALC_UNIT_BUILT_IN = {
    "en": "«{symbol}» is a built-in unit; it cannot be defined again.",
    "ar": "«{symbol}» وحدة أساسية في ONE؛ مينفعش تتعرّف تاني.",
}

CALC_UNIT_CURRENCY = {
    "en": (
        "A unit cannot hold a currency. "
        "An exchange rate is a Source Ledger number with a unit like EGP/USD."
    ),
    "ar": "الوحدة مينفعش يبقى فيها عملة. سعر الصرف رقم في سجل المصادر بوحدة زي EGP/USD.",
}

CALC_UNIT_LOOP = {
    "en": "«{symbol}» would be defined through itself.",
    "ar": "«{symbol}» كده هتتعرّف بنفسها.",
}

CALC_UNIT_FACTOR = {
    "en": 'A unit must equal more than zero of another unit, e.g. `"equals": "50 kg"`.',
    "ar": 'الوحدة لازم تساوي أكتر من صفر من وحدة تانية، زي `"equals": "50 kg"`.',
}

CALC_UNIT_CASE = {
    "en": (
        "«{symbol}» is already defined as «{existing}»: units that differ only in upper and "
        "lower case are one unit. Send «{existing}» with a `reason` to correct it."
    ),
    "ar": (
        "«{symbol}» متعرّفة قبل كده باسم «{existing}»: الوحدات اللي فرقها في الحروف الكبيرة "
        "والصغيرة بس وحدة واحدة. ابعت «{existing}» مع `reason` عشان تصححها."
    ),
}

# Inputs.
CALC_CONSTANT_UNIT = {
    "en": (
        "A constant is a plain number or %. "
        "A number with a unit or a currency goes in the Source Ledger with its source and date."
    ),
    "ar": (
        "الثابت رقم مجرد أو نسبة %. الرقم اللي ليه وحدة أو عملة مكانه سجل المصادر، بمصدره وتاريخه."
    ),
}

CALC_ITEM_NOT_FOUND = {
    "en": "No item has the id or code «{ref}».",
    "ar": "مفيش بند الـ id أو الكود بتاعه «{ref}».",
}

CALC_ITEM_AMBIGUOUS = {
    "en": "«{ref}» matches {n} items: {choices}. Send the item id.",
    "ar": "«{ref}» بيطابق {n} بنود: {choices}. ابعت الـ id بتاع البند.",
}

CALC_NUMBER_NOT_FOUND = {
    "en": "No number has the id «{ref}».",
    "ar": "مفيش رقم الـ id بتاعه «{ref}».",
}

CALC_NUMBER_OLD = {
    "en": "Number «{ref}» was corrected; the current entry is «{now}».",
    "ar": "الرقم «{ref}» اتصحح؛ القيمة الحالية هي «{now}».",
}

CALC_NUMBER_MISSING = {
    "en": "Item {item} has no current «{name}».",
    "ar": "البند {item} مفيهوش «{name}» حالي.",
}

CALC_NUMBER_AMBIGUOUS = {
    "en": (
        "Item {item} has {n} current «{name}» numbers: {choices}. "
        'Send `{{"number": "<id>"}}` for the one to use.'
    ),
    "ar": (
        "البند {item} فيه {n} أرقام حالية باسم «{name}»: {choices}. "
        'ابعت `{{"number": "<id>"}}` للرقم اللي هتستخدمه.'
    ),
}

CALC_NO_MATCH = {
    "en": "No item matches {selector}.",
    "ar": "مفيش بند بيطابق {selector}.",
}

CALC_MISSING_IN_ITEMS = {
    "en": '{n} items have no «{name}»: {codes}. Add it first, or send `"skip_missing": true`.',
    "ar": '{n} بنود مفيهاش «{name}»: {codes}. ضيفه الأول، أو ابعت `"skip_missing": true`.',
}

# Saving.
CALC_NEEDS_LEDGER_INPUT = {
    "en": "A saved result needs at least one number from the Source Ledger.",
    "ar": "النتيجة اللي هتتحفظ محتاجة رقم واحد على الأقل من سجل المصادر.",
}

CALC_SAVE_NEEDS_REASON = {
    "en": (
        "Item {item} already has «{name}» = {value} {unit} (from {source}). "
        "Send `save.reason` to correct it."
    ),
    "ar": (
        "البند {item} فيه «{name}» = {value} {unit} بالفعل (من {source}). "
        "ابعت `save.reason` عشان تصححه."
    ),
}

CALC_SAVE_RATE = {
    "en": "A rate is a currency per unit, e.g. EGP/m3; this result is {unit}.",
    "ar": "الفئة عملة لكل وحدة، زي EGP/m3؛ النتيجة دي {unit}.",
}

CALC_SAVE_AMOUNT = {
    "en": "An amount is one currency, e.g. EGP; this result is {unit}.",
    "ar": "المبلغ عملة واحدة، زي EGP؛ النتيجة دي {unit}.",
}

CALC_SAVE_QUANTITY = {
    "en": "A quantity has no currency; this result is {unit}.",
    "ar": "الكمية مفيهاش عملة؛ النتيجة دي {unit}.",
}

CALC_SAVE_OWN_INPUT = {
    "en": "The result cannot correct one of its own inputs («{name}»).",
    "ar": "النتيجة مينفعش تصحح مدخل من مدخلاتها («{name}»).",
}

CALC_REQUEST_SHAPE = {
    "en": "The request is not complete at «{field}». Send it like this: {example}.",
    "ar": "الطلب ناقص عند «{field}». ابعته كده: {example}.",
}

# The tools for agents: what each one does, in the engineer's words.
CALC_TOOL_CALCULATE = {
    "en": "Calculates a number exactly and saves it with its formula and sources.",
    "ar": "بيحسب الرقم بالظبط ويحفظه بمعادلته ومصادره.",
}

CALC_TOOL_DEFINE_UNIT = {
    "en": "Defines a project unit, like a bag of 50 kg, with its source.",
    "ar": "بيعرّف وحدة للمشروع، زي شيكارة 50 كجم، بمصدرها.",
}

CALC_TOOL_EXPLAIN = {
    "en": "Shows where a number comes from: its formula, inputs, sources and dates.",
    "ar": "بيوضّح الرقم جاي منين: معادلته ومدخلاته ومصادره وتواريخها.",
}

CALC_TOOL_RECALCULATE = {
    "en": "Lists the numbers out of date after a correction, and recalculates them in order.",
    "ar": "بيعرض الأرقام اللي محتاجة إعادة حساب بعد تصحيح، ويحسبها تاني بالترتيب.",
}

# Notes: facts about a result, not refusals.
CALC_NOTE_INEXACT = {
    "en": "The result is not exact before rounding: a division or conversion does not end.",
    "ar": "النتيجة مش مظبوطة قبل التقريب: في قسمة أو تحويل مش بيخلص.",
}

CALC_NOTE_OWN_UNIT = {
    "en": "«{unit}» is not defined, so it is a unit of its own that converts to nothing.",
    "ar": "«{unit}» مش متعرّفة، فهي وحدة لوحدها ومش بتتحوّل لأي وحدة تانية.",
}

CALC_NOTE_SKIPPED = {
    "en": "{n} items were skipped for a missing «{name}»: {codes}.",
    "ar": "اتسابت {n} بنود عشان مفيهاش «{name}»: {codes}.",
}

# Recalculation reasons. The English text is stored in the ledger; the trace keeps the cause.
CALC_RECALCULATED = {
    "en": "Recalculated: «{name}» was corrected ({reason}).",
    "ar": "اتحسب تاني: «{name}» اتصحح ({reason}).",
}

CALC_RECALC_MEMBERS = {
    "en": "Recalculated: the matching items changed.",
    "ar": "اتحسب تاني: البنود المطابقة اتغيرت.",
}


# ---------------------------------------------------------------------------------------------
# Deliverables and review (Plan 6). Keep these texts together, in this block.
# Texts with values use {name} placeholders filled by `fill`.
# ---------------------------------------------------------------------------------------------

# The Deliverable and its Template Data Sheet.
DELIVERABLE_NOT_FOUND = {
    "en": "This Deliverable is not in the project. Open the Project Index to find it.",
    "ar": "المُخرَج ده مش موجود في المشروع. افتح فهرس المشروع ودوّر عليه.",
}

DELIVERABLE_CALC_REASON = {
    "en": "calculated in «{title}»",
    "ar": "اتحسب في «{title}»",
}

RECORDS_MOVED = {
    "en": "Update from Project Records",
    "ar": "تحديث من سجلات المشروع",
}

TEMPLATE_UNKNOWN = {
    "en": "There is no such template. A Deliverable is a Sheet or a Document.",
    "ar": "مفيش قالب بالاسم ده. المُخرَج يا إما جدول (Sheet) يا إما مستند (Document).",
}

COLUMN_NOT_ALLOWED = {
    "en": (
        "This column is not allowed. A column is text (code, field:<key>, number:<name>.unit), "
        "number (number:<name>) or calc (a formula of this row's numbers)."
    ),
    "ar": (
        "العمود ده مش مسموح. العمود يا إما text (code أو field:<key> أو number:<name>.unit)، "
        "يا إما number (number:<name>)، يا إما calc (معادلة من أرقام نفس الصف)."
    ),
}

NODE_NOT_ALLOWED = {
    "en": (
        "This part of the document is not allowed. Use p, h1-h3, ul, ol, li, table, tr, td or "
        "blockquote, with num and cell for numbers, and bold or italic."
    ),
    "ar": (
        "الجزء ده من المستند مش مسموح. استخدم p أو h1-h3 أو ul أو ol أو li أو table أو tr أو td "
        "أو blockquote، ومعاهم num وcell للأرقام، وbold أو italic."
    ),
}

# Operations.
OP_UNKNOWN = {
    "en": (
        "This operation is not known. A Sheet takes set_number, set_field, add_item_row, "
        "add_section, set_section_title, remove_row, move_row and set_columns; a Document takes "
        "set_block, insert_block, remove_block and move_block."
    ),
    "ar": (
        "العملية دي مش معروفة. الجدول بياخد set_number وset_field وadd_item_row وadd_section "
        "وset_section_title وremove_row وmove_row وset_columns؛ والمستند بياخد set_block "
        "وinsert_block وremove_block وmove_block."
    ),
}

OP_NOT_IN_TEMPLATE = {
    "en": "This Deliverable's template does not allow this operation.",
    "ar": "قالب المُخرَج ده مش بيسمح بالعملية دي.",
}

OP_NUMBER_NEEDS_NAME = {
    "en": 'A number needs its name, the column it goes in: "name": "rate" or "quantity".',
    "ar": 'الرقم محتاج اسمه، يعني العمود اللي هيتحط فيه: "name": "rate" أو "quantity".',
}

ROW_NOT_FOUND = {
    "en": "This row is not in the Deliverable, or it was removed. Read the Deliverable again.",
    "ar": "الصف ده مش موجود في المُخرَج، أو اتشال. اقرا المُخرَج تاني.",
}

NUMBER_WAS_CALCULATED = {
    "en": "This rate came from «{formula}»; typing it replaces the calculation.",
    "ar": "الفئة دي جاية من «{formula}»؛ لو كتبتها بإيدك هتحل محل الحساب.",
}

AMOUNT_IS_COMPUTED = {
    "en": (
        "Amounts are computed by the QS Calc Engine from quantity × rate; "
        "change the quantity or the rate."
    ),
    "ar": "الإجمالي بيحسبه محرك الحسابات من الكمية × الفئة؛ غيّر الكمية أو الفئة.",
}

# Suggested changes.
UNDO_ACCEPT_REASON = {
    "en": "Undo of an accepted change in «{title}»",
    "ar": "تراجع عن تعديل اتقبل في «{title}»",
}

UNDO_TOO_LATE = {
    "en": "Too late to undo: this Deliverable changed since. Its Saved versions show what moved.",
    "ar": "مينفعش تتراجع: المُخرَج ده اتغيّر من ساعتها. النسخ المحفوظة بتوضّح إيه اللي اتغيّر.",
}

UNDO_RECORDS = {
    "en": (
        "An Update from Project Records cannot be undone here: correct the number in "
        "Project Records."
    ),
    "ar": "تحديث من سجلات المشروع مايتلغيش من هنا: صحّح الرقم في سجلات المشروع.",
}

CHANGE_STALE = {
    "en": "This cell changed after the change was suggested. Ask ONE again, or edit it yourself.",
    "ar": "الخلية دي اتغيرت بعد ما التعديل اتقترح. اطلب من ONE تاني، أو عدّلها بنفسك.",
}

CHANGE_NOT_PENDING = {
    "en": "This change was already accepted or rejected.",
    "ar": "التعديل ده اتقبل أو اترفض قبل كده.",
}

# Comments.
COMMENT_NOT_FOUND = {
    "en": "This comment is not in the Deliverable.",
    "ar": "الملاحظة دي مش موجودة في المُخرَج.",
}

COMMENT_NEEDS_TEXT = {
    "en": "Write the comment first.",
    "ar": "اكتب الملاحظة الأول.",
}

ANCHOR_NOT_FOUND = {
    "en": "The place this comment points to is not in the Deliverable. Pick a cell or text.",
    "ar": "المكان اللي الملاحظة بتشاور عليه مش موجود في المُخرَج. اختار خلية أو نص.",
}

COMMENT_KIND_NOT_ALLOWED = {
    "en": (
        "ONE's team writes notes, with no code. Review comments come from you or the "
        "Checking QS, with Code B or C."
    ),
    "ar": (
        "فريق ONE بيكتب ملاحظات بس، من غير كود. ملاحظات المراجعة بتيجي منك أو من مهندس "
        "المراجعة، بكود B أو C."
    ),
}

# "Fix it": the message the screen sends to the Lead QS for one Review comment.
FIX_REQUEST = {
    "en": (
        "Fix Review comment {comment} on «{title}» (Deliverable {deliverable}, {at}), "
        "at {place}: «{body}». Propose the fix with deliverable_propose and comment_id {comment}."
    ),
    "ar": (
        "صلّح ملاحظة المراجعة {comment} في «{title}» (المُخرَج {deliverable}، {at})، "
        "عند {place}: «{body}». اقترح التصليح بـ deliverable_propose ومعاه comment_id {comment}."
    ),
}

FIX_AT_REVISION = {"en": "Rev {no}, version {n}", "ar": "Rev {no}، النسخة {n}"}

FIX_AT_VERSION = {"en": "version {n}", "ar": "النسخة {n}"}

FIX_PLACE_CELL = {
    "en": "item «{row}», column «{column}» (row {id})",
    "ar": "البند «{row}»، عمود «{column}» (الصف {id})",
}

FIX_PLACE_RANGE = {
    "en": "from item «{start}» to item «{end}», columns «{first}» to «{last}» (rows {ids})",
    "ar": "من البند «{start}» للبند «{end}»، الأعمدة من «{first}» لـ «{last}» (الصفوف {ids})",
}

FIX_PLACE_ROW = {
    "en": "«{row}» (row {id})",
    "ar": "«{row}» (الصف {id})",
}

FIX_PLACE_TEXT = {
    "en": "the words «{quote}» (block {id})",
    "ar": "الكلام «{quote}» (الفقرة {id})",
}

FIX_PLACE_DELIVERABLE = {
    "en": "the whole Deliverable",
    "ar": "المُخرَج كله",
}

# Close-out and Sign-off.
SIGNOFF_PENDING_CHANGES = {
    "en": "Accept or reject every Suggested change first.",
    "ar": "اقبل أو ارفض كل التعديلات المقترحة الأول.",
}

SIGNOFF_OPEN_CODE_C = {
    "en": "A Code C comment is still open. Fix it and close it first.",
    "ar": "في ملاحظة كود C لسه مفتوحة. صلّحها واقفلها الأول.",
}

SIGNOFF_NEEDS_CHECK = {
    "en": "The Checking QS has not checked this version yet. Ask for a check first.",
    "ar": "مهندس المراجعة لسه ماراجعش النسخة دي. اطلب مراجعة الأول.",
}

SIGNOFF_CODE_C = {
    "en": "The Checking QS gave this version Code C: revise and resubmit.",
    "ar": "مهندس المراجعة إدّى النسخة دي كود C: يتعدّل ويتقدّم تاني.",
}

ALREADY_SIGNED_OFF = {
    "en": "This version is already signed off.",
    "ar": "النسخة دي اتعتمدت قبل كده.",
}

# Exports.
EXPORT_DRAFT_MARK = {
    "en": "Draft — not signed off",
    "ar": "مسودة — غير معتمد",
}

SAMPLE_DATA = {
    "en": "Sample data",
    "ar": "بيانات تجريبية",
}

SOURCES_SHEET = {
    "en": "Sources",
    "ar": "المصادر",
}

ENTERED_BY_ENGINEER = {
    "en": "Entered by the engineer",
    "ar": "أدخله المهندس",
}

MANUAL_EDIT_REASON = {
    "en": "Edited by hand in «{title}»",
    "ar": "تعديل يدوي في «{title}»",
}

EXPORT_FORMAT_NOT_ALLOWED = {
    "en": "A Sheet exports to Excel or PDF, a Document to Word or PDF.",
    "ar": "الجدول بيتصدّر Excel أو PDF، والمستند Word أو PDF.",
}

# The exports' own labels (Excel, Word, PDF), formal like the documents they sit in, each an
# {en, ar} pair; qsone.export.say fills them in the Deliverable's language.
EXPORT_LABELS = {
    "total": {"en": "Grand total", "ar": "الإجمالي العام"},
    "sources": {"en": "Sources", "ar": "المصادر"},
    "deliverable": {"en": "Deliverable", "ar": "مُخرَج"},
    "draft": {"en": "Draft", "ar": "مسودة"},
    "rev": {"en": "Rev {n}", "ar": "إصدار {n}"},
    "page_of": {"en": "Page {x} of {y}", "ar": "صفحة {x} من {y}"},
    "needs_signoff": {
        "en": "This Deliverable is exported only after Sign-off. Sign it off first.",
        "ar": "المُخرَج ده بيتصدّر بعد الاعتماد بس. اعتمده الأول.",
    },
    # The sources list: one line per number shown.
    "src_where": {"en": "Item", "ar": "البند"},
    "src_column": {"en": "Column", "ar": "العمود"},
    "src_value": {"en": "Value", "ar": "القيمة"},
    "src_unit": {"en": "Unit or currency", "ar": "الوحدة أو العملة"},
    "src_title": {"en": "Source", "ar": "المصدر"},
    "src_file": {"en": "File", "ar": "الملف"},
    "src_place": {"en": "Place", "ar": "الموضع"},
    "src_link": {"en": "Link", "ar": "الرابط"},
    "src_dated": {"en": "Dated", "ar": "التاريخ"},
    "src_kind": {"en": "Kind", "ar": "النوع"},
    "page": {"en": "page", "ar": "صفحة"},
    "sheet": {"en": "sheet", "ar": "ورقة"},
    "row": {"en": "row", "ar": "صف"},
    "cell": {"en": "cell", "ar": "خلية"},
    "column": {"en": "column", "ar": "عمود"},
    "line": {"en": "line", "ar": "سطر"},
    "layer": {"en": "layer", "ar": "طبقة"},
    # A calculation's formula in words: «الكمية × الفئة», «مجموع الإجمالي».
    "fn_sum": {"en": "Sum of", "ar": "مجموع"},
    "fn_count": {"en": "Count of", "ar": "عدد"},
    "fn_avg": {"en": "Average of", "ar": "متوسط"},
    "fn_min": {"en": "Least of", "ar": "أقل"},
    "fn_max": {"en": "Greatest of", "ar": "أكبر"},
    # A file source's kind as the sources list names it; any other kind reads "Document".
    "kind_boq": {"en": "BOQ", "ar": "مقايسة"},
    "kind_quote": {"en": "Quotation", "ar": "عرض سعر"},
    "kind_specification": {"en": "Specification", "ar": "مواصفات"},
    "kind_contract": {"en": "Contract", "ar": "عقد"},
    "kind_drawing": {"en": "Drawing", "ar": "رسومات"},
    "kind_web": {"en": "Web page", "ar": "صفحة ويب"},
    "kind_prices": {"en": "QS Mind market prices", "ar": "أسعار السوق من كيو إس مايند"},
    "kind_connector": {"en": "Connector", "ar": "موصّل"},
    "kind_chat": {"en": "The chat", "ar": "الشات"},
    "kind_document": {"en": "Document", "ar": "مستند"},
    # The PDF's header block.
    "head_project": {"en": "Project", "ar": "المشروع"},
    "head_client": {"en": "Client", "ar": "العميل"},
    "head_submission": {"en": "Submission", "ar": "ميعاد التقديم"},
    "head_date": {"en": "Date", "ar": "التاريخ"},
    "prepared": {"en": "Prepared with ONE", "ar": "تم الإعداد باستخدام ONE"},
    "calc_engine": {"en": "QS Calc Engine", "ar": "محرك الحسابات"},
    "engineer": {"en": "The engineer", "ar": "المهندس"},
    # The Review report.
    "report": {"en": "Review report", "ar": "تقرير المراجعة"},
    "issued": {"en": "Issued {at} by {by}", "ar": "صدر {at} بواسطة {by}"},
    "signed_by": {"en": "Signed off {at} by {by}", "ar": "اعتمده {by} في {at}"},
    "checks": {"en": "Checks", "ar": "المراجعات"},
    "code": {"en": "Code {code}", "ar": "كود {code}"},
    "version": {"en": "Version {n}", "ar": "نسخة {n}"},
    "checker": {"en": "Checker", "ar": "المراجع"},
    "same_provider": {"en": "Same-provider check", "ar": "مراجعة من نفس الشركة"},
    "other_provider": {"en": "Another provider", "ar": "شركة أخرى"},
    "changes": {
        "en": "Changes: {accepted} accepted, {rejected} rejected",
        "ar": "التعديلات: {accepted} مقبول، {rejected} مرفوض",
    },
    "comments": {"en": "Comments", "ar": "الملاحظات"},
    "note": {"en": "ONE's note", "ar": "ملاحظة ONE"},
    "review": {"en": "Review comment", "ar": "ملاحظة مراجعة"},
    "open": {"en": "Open", "ar": "مفتوحة"},
    "closed": {"en": "Closed", "ar": "مقفولة"},
    "none": {"en": "None", "ar": "مفيش"},
}

# The client's own file.
FILL_XLS_NOT_SUPPORTED = {
    "en": "Open the file in Excel, save it as .xlsx, then drop it again.",
    "ar": "افتح الملف في Excel واحفظه بصيغة .xlsx، وبعدين ارميه تاني.",
}

FILL_NEEDS_SIGNOFF = {
    "en": "The client's file is filled only from a signed-off Revision. Sign off first.",
    "ar": "ملف العميل بيتملي من إصدار معتمد بس. اعتمد الأول.",
}

FILL_SHEET_NOT_FOUND = {
    "en": "The client's file has no sheet named «{sheet}».",
    "ar": "ملف العميل مفيهوش ورقة اسمها «{sheet}».",
}

FILL_ROW_MISSING = {
    "en": "Row {row} is not in the client's sheet, so nothing was written. Check the Fill Plan.",
    "ar": "الصف {row} مش موجود في ورقة العميل، فمكتبناش حاجة. راجع خطة التعبئة.",
}

FILL_ROW_TWICE = {
    "en": "Row {row} appears twice in the Fill Plan.",
    "ar": "الصف {row} متكرر مرتين في خطة التعبئة.",
}

FILL_CODE_MISMATCH = {
    "en": "Row {row}: the client's code is «{theirs}», our item is «{ours}».",
    "ar": "الصف {row}: كود العميل «{theirs}»، والبند عندنا «{ours}».",
}

FILL_FORMULA_SKIPPED = {
    "en": "{cell} holds the client's formula, so it was left as it is.",
    "ar": "{cell} فيها معادلة العميل، فسيبناها زي ما هي.",
}

FILL_COLUMN_LETTER = {
    "en": "A column of the client's sheet is a letter from A to XFD, as Excel shows it.",
    "ar": "عمود ورقة العميل حرف من A لحد XFD، زي ما Excel بيعرضه.",
}

FILL_PLAN_NOT_FOUND = {
    "en": "This Fill Plan is not in the project. Ask ONE to map the client's file again.",
    "ar": "خطة التعبئة دي مش موجودة في المشروع. اطلب من ONE يربط ملف العميل تاني.",
}

# Accepting while Project Records moved.
UPDATE_FIRST = {
    "en": (
        "First review «Update from Project Records»: "
        "the Project Records changed since this version."
    ),
    "ar": "راجع «تحديث من سجلات المشروع» الأول: سجلات المشروع اتغيرت من ساعة الإصدار ده.",
}

# Tools (Plan 5). Activity words: the Progress Line and the online and outside cards show them,
# so they hold the exact thing that would leave One.
DOING_WEB_SEARCH = {"en": "Search the web for: {query}", "ar": "يدوّر في الويب على: {query}"}
DOING_WEB_READ = {"en": "Open the web page: {url}", "ar": "يفتح صفحة الويب: {url}"}
DOING_FILES_READ = {"en": "Read {name}, pages {pages}", "ar": "يقرا {name}، صفحات {pages}"}
DOING_FILES_READ_PAGE = {"en": "Read {name}, page {page}", "ar": "يقرا {name}، صفحة {page}"}
DOING_FILES_READ_ROWS = {
    "en": "Read {name}, sheet {sheet}, rows {rows}",
    "ar": "يقرا {name}، شيت {sheet}، الصفوف {rows}",
}
DOING_FILE_READ = {"en": "Read {name}", "ar": "يقرا {name}"}  # a file with no pages
DOING_BOQ_IMPORT = {
    "en": "Import the BOQ from {name}, sheet {sheet}",
    "ar": "يستورد المقايسة من {name}، شيت {sheet}",
}
DOING_PRICES = {"en": "Look up the price of: {item}", "ar": "يدوّر على سعر: {item}"}
DOING_SANDBOX = {
    "en": "Run a script in the Sandbox on {count} files",
    "ar": "يشغّل سكريبت في الصندوق المعزول على {count} ملف",
}
DOING_CONNECTOR = {
    "en": "Use {connector}: {tool} with {args}",
    "ar": "يستخدم {connector}: {tool} بـ {args}",
}
DOING_ASK = {"en": "Waiting for your answer", "ar": "مستني ردك"}

# ask_engineer's card. {agent} is the agent's name; the questions are the agent's own words.
QUESTION_OWN_REQUEST = {
    "en": "That is the engineer's own question. Answer it from the files you read "
    "(drawing reads start with sheets and block counts; project_map modes sheets/counts); "
    "if truly absent, say what you searched.",
    "ar": "ده نفس سؤال المهندس. جاوب عليه من الملفات اللي قريتها "
    "(قراءة الرسومات بتبدأ باللوحات وأعداد البلوكات؛ وأوضاع project_map هي sheets/counts)؛ "
    "ولو المعلومة مش موجودة فعلاً، قول دورت على إيه.",
}
QUESTION_TITLE = {"en": "{agent} asks", "ar": "{agent} بيسأل"}
QUESTION_DETAIL = {
    "en": "Answer every question, then press Send. Your answers are kept as the source of "
    "any number they give.",
    "ar": "جاوب على كل سؤال، وبعدين دوس إرسال. ردودك بتتحفظ كمصدر لأي رقم فيها.",
}

ON_DEVICE_NO_ONLINE = {
    "en": (
        "This is an On-device Project: nothing leaves this computer, so ONE cannot do this here."
    ),
    "ar": "ده مشروع على الجهاز: مفيش حاجة بتخرج من الجهاز، فـ ONE مش هيقدر يعمل ده هنا.",
}

# The web.
WEB_OFFLINE = {
    "en": (
        "No internet connection, so ONE could not reach the web. "
        "It will try again when the connection is back."
    ),
    "ar": "مفيش نت، فـ ONE مقدرش يوصل للويب. هيحاول تاني لما النت يرجع.",
}
WEB_NO_SEARCH = {
    "en": (
        "No web search is set up. Add a search key, connect an AI that can search "
        "(Claude), or subscribe to QS Mind."
    ),
    "ar": (
        "مفيش بحث على الويب متظبط. ضيف مفتاح بحث، أو وصّل ذكاء اصطناعي بيعرف يدوّر "
        "(Claude)، أو اشترك في QS Mind."
    ),
}
WEB_SEARCH_KEY_REFUSED = {
    "en": "The search key was refused. Check that you copied all of it, or add a new one.",
    "ar": "مفتاح البحث اترفض. اتأكد إنك نسخته كله، أو ضيف مفتاح جديد.",
}
WEB_SEARCH_LIMIT = {
    "en": ("This month's search allowance is used up. Add your own search key to continue."),
    "ar": "رصيد البحث للشهر ده خلص. ضيف مفتاح بحث بتاعك عشان تكمّل.",
}
WEB_SEARCH_BUSY = {
    "en": "The search service is busy. Try again in a minute.",
    "ar": "خدمة البحث عليها ضغط. جرّب تاني كمان دقيقة.",
}
WEB_BAD_URL = {
    "en": "Send a full web address that starts with https:// or http://.",
    "ar": "ابعت عنوان ويب كامل بيبدأ بـ https:// أو http://.",
}
WEB_PRIVATE_ADDRESS = {
    "en": "This address points inside this computer or its local network, so ONE will not open it.",
    "ar": "العنوان ده بيشاور على حاجة جوه الجهاز أو الشبكة المحلية، فـ ONE مش هيفتحه.",
}
WEB_PAGE_REFUSED = {
    "en": "The site refused the page, or it does not exist.",
    "ar": "الموقع رفض الصفحة، أو هي مش موجودة.",
}
WEB_SITE_DOWN = {
    "en": "The site did not answer in time. Try again later.",
    "ar": "الموقع مارَدّش في الوقت. جرّب تاني بعدين.",
}
WEB_TOO_BIG = {
    "en": "The page is larger than 10 MB, so ONE did not read it.",
    "ar": "الصفحة أكبر من 10 ميجا، فـ ONE ماقراهاش.",
}
WEB_KIND_NOT_READ = {
    "en": "ONE cannot read this kind of web file yet.",
    "ar": "ONE لسه مش بيقرا النوع ده من ملفات الويب.",
}
WEB_ROBOTS = {
    "en": "The site asks programs not to read this page, so ONE did not.",
    "ar": "الموقع طالب من البرامج ماتقراش الصفحة دي، فـ ONE ماقراهاش.",
}
WEB_QUERY_NAMES_PROJECT = {
    "en": "Search in general words, without the project's or the client's name.",
    "ar": "دوّر بكلام عام، من غير اسم المشروع أو اسم العميل.",
}
WEB_QUERY_PERSONAL = {
    "en": "Search without anyone's phone numbers, emails or ID numbers.",
    "ar": "دوّر من غير أرقام تليفونات أو إيميلات أو أرقام بطاقات لحد.",
}
WEB_NO_DATE = {
    "en": "The page shows no date; the date it was read is given instead.",
    "ar": "الصفحة مفيهاش تاريخ؛ مكتوب بدله تاريخ قرايتها.",
}

# Files.
FILE_NOT_IN_PROJECT = {
    "en": "There is no file with this id here. files_list shows the files.",
    "ar": "مفيش ملف بالرقم ده هنا. files_list بيعرض الملفات.",
}
FILE_PAGES_OUT_OF_RANGE = {
    "en": "Those pages are not in the file. It has {pages}.",
    "ar": "الصفحات دي مش في الملف. الملف فيه {pages}.",
}
FILE_LIBREOFFICE_MISSING = {
    "en": "Kept. LibreOffice opens this file, but is not installed. Download it from "
    "https://www.libreoffice.org/download/download-libreoffice/.",
    "ar": "اتحفظ. LibreOffice بيفتح الملف ده، بس مش متثبت. نزّله من "
    "https://www.libreoffice.org/download/download-libreoffice/.",
}
FILE_OFFICE_CONVERSION_FAILED = {
    "en": "Kept. LibreOffice could not convert this file or took too long. "
    "Open it in LibreOffice and export a PDF or XLSX copy, then drop that copy.",
    "ar": "اتحفظ. LibreOffice مقدرش يحوّل الملف ده أو أخد وقت طويل. "
    "افتحه في LibreOffice وصدّر نسخة PDF أو XLSX، وبعدين ارمي النسخة دي.",
}
FILE_OLD_WORD = {
    "en": (
        "Kept. ONE reads Word files saved as .docx: open this one in Word, save it as .docx, "
        "then drop it again."
    ),
    "ar": (
        "اتحفظ. ONE بيقرا ملفات Word المحفوظة .docx: افتح الملف ده في Word واحفظه .docx "
        "وبعدين ارميه تاني."
    ),
}
FILE_DWG_NOT_YET = {
    "en": "This drawing was kept before ONE’s drawing reader was available.",
    "ar": "الرسم ده اتحفظ قبل ما قارئ الرسومات بتاع ONE يبقى متاح.",
}
FILE_IMAGE_STORED = {
    "en": "Kept. ONE reads the image when it is asked to.",
    "ar": "اتحفظت. ONE هيقرا الصورة لما يتطلب منه.",
}
FILE_HIDDEN_TEXT = {
    "en": (
        "This file has hidden text (white, tiny or invisible) or lines that look like orders to "
        "an AI. ONE treats them as data only and shows them to you and the Checking QS."
    ),
    "ar": (
        "الملف ده فيه نص مخفي (أبيض أو صغير جداً أو مش ظاهر) أو سطور شكلها أوامر لذكاء اصطناعي. "
        "ONE بيتعامل معاها كبيانات بس وبيوريها ليك ولمهندس المراجعة."
    ),
}

# Scanned pages: local OCR first, then the engineer's AI.
OCR_TESSERACT_MISSING = {
    "en": (
        "Tesseract is not installed. Get it at "
        "https://tesseract-ocr.github.io/tessdoc/Installation.html. "
        "ONE can still use your AI reader."
    ),
    "ar": (
        "Tesseract مش متثبت. نزّله من "
        "https://tesseract-ocr.github.io/tessdoc/Installation.html. "
        "ONE لسه يقدر يقرا عن طريق نموذجك."
    ),
}
OCR_TESSERACT_FAILED = {
    "en": (
        "The local OCR reader or its language data could not be used. ONE can still use your "
        "AI reader."
    ),
    "ar": "القراية المحلية أو بيانات لغاتها مش متاحة. ONE لسه يقدر يقرا عن طريق نموذجك.",
}
OCR_LOW_CONFIDENCE = {
    "en": (
        "Low-confidence OCR: the Lead QS must check this page against its image "
        "before using its numbers."
    ),
    "ar": (
        "الثقة في قراية الصفحة قليلة: كبير مهندسي الكميات لازم يراجعها على الصورة "
        "قبل استخدام أرقامها."
    ),
}

OCR_NEEDS_MODEL = {
    "en": (
        "Reading scanned pages needs an AI model that can read images. Connect one, then ask again."
    ),
    "ar": "قراية الصفحات المتصورة محتاجة نموذج ذكاء اصطناعي بيقرا الصور. وصّل واحد واطلب تاني.",
}
OCR_FAILED = {
    "en": "The page image could not be read. Try again, or use another model.",
    "ar": "صورة الصفحة مااتقرتش. جرّب تاني، أو استخدم نموذج تاني.",
}
OCR_ASK = {
    "en": "Read {pages} scanned pages with {model}? About {cost}.",
    "ar": "أقرا {pages} صفحة متصورة بـ {model}؟ تقريباً {cost}.",
}
OCR_ASK_UNKNOWN = {
    "en": (
        "Read {pages} scanned pages with {model}? ONE cannot tell the cost: it has no known price."
    ),
    "ar": "أقرا {pages} صفحة متصورة بـ {model}؟ ONE مش عارف التكلفة: النموذج ملوش سعر معروف.",
}
OCR_COST = {"en": "{usd} USD", "ar": "{usd} دولار"}
OCR_COST_EQUIVALENT = {
    "en": "{usd} USD of equivalent cost on your Claude subscription",
    "ar": "{usd} دولار تكلفة مكافئة على اشتراك Claude بتاعك",
}
OCR_IMAGE_KIND = {
    "en": "ONE reads PNG and JPEG images. Save this image as PNG or JPEG, then drop it again.",
    "ar": "ONE بيقرا صور PNG و JPEG. احفظ الصورة دي PNG أو JPEG وارميها تاني.",
}
A_FILE = {"en": "a file", "ar": "ملف"}  # DOING_FILES_READ's {name} before the file is known

# BOQ import.
BOQ_NO_SHEET = {
    "en": "This file has no sheet by that name. The sheets are: {sheets}.",
    "ar": "الملف ده مفيهوش شيت بالاسم ده. الشيتات: {sheets}.",
}
BOQ_BAD_COLUMNS = {
    "en": 'Map at least the description, unit and quantity columns, by letter (e.g. "C").',
    "ar": 'حدّد على الأقل أعمدة الوصف والوحدة والكمية، بالحرف (زي "C").',
}
BOQ_ROW_SKIPPED = {
    "en": "Row {row} was not imported: {why}",
    "ar": "الصف {row} مااتستوردش: {why}",
}
# Task 9: the import's own words. Why a row was left out ({field} is a BOQ_FIELDS pair).
BOQ_WHY_TEXT = {
    "en": "the {field} in column {column} is text, not a number",
    "ar": "{field} في العمود {column} نص، مش رقم",
}
BOQ_WHY_NUMBER_FORMAT = {
    "en": (
        "the {field} in column {column} has an ambiguous decimal/thousands separator; "
        "the file does not establish one convention"
    ),
    "ar": (
        "الفاصل في {field} بالعمود {column} مش واضح: عشري ولا آلاف، وباقي الملف مش موضّح طريقة واحدة"
    ),
}
BOQ_WHY_DECIMALS = {
    "en": "the {field} in column {column} has more than 6 decimals; check the cell in Excel",
    "ar": "{field} في العمود {column} فيه أكتر من 6 أرقام عشرية؛ راجع الخانة في Excel",
}
BOQ_WHY_NO_UNIT = {"en": "a quantity with no unit", "ar": "كمية من غير وحدة"}
BOQ_WHY_NO_DESCRIPTION = {"en": "numbers with no description", "ar": "أرقام من غير وصف"}
BOQ_QUANTITY_FALLBACK = {
    "en": "Quantity taken from column {column} for rows {rows}.",
    "ar": "الكمية اتاخدت من العمود {column} للصفوف {rows}.",
}
BOQ_QUANTITY_MISSING = {
    "en": (
        "No quantity in the file for rows {rows} "
        "(the mapped and quantity-heading columns are empty)."
    ),
    "ar": "مفيش كمية في الملف للصفوف {rows} (العمود المختار وأعمدة الكمية فاضيين).",
}
BOQ_PRICE_ITEM_REQUIRED = {
    "en": (
        "The engineer did not name item {item} or request pricing. "
        "Name the intended BOQ item, request pricing, "
        "or keep a standalone price."
    ),
    "ar": (
        "المهندس محددش البند {item} ولا طلب تسعير. "
        "حدّد بند المقايسة المقصود، أو اطلب تسعير، "
        "أو سجّل السعر لوحده."
    ),
}

BOQ_WHY_TOTAL = {"en": "a total row", "ar": "صف إجمالي"}
BOQ_WHY_NUMBER_ONLY = {
    "en": "a rate or amount with no quantity and no unit",
    "ar": "فئة أو إجمالي من غير كمية ولا وحدة",
}
BOQ_WHY_HIDDEN = {"en": "the row is hidden in Excel", "ar": "الصف مخفي في Excel"}
BOQ_WHY_HEADER = {"en": "the column headings again", "ar": "عناوين الأعمدة تاني"}
BOQ_FIELDS = {
    "code": {"en": "Item no.", "ar": "رقم البند"},
    "description": {"en": "Description", "ar": "الوصف"},
    "description_2": {"en": "Description, other language", "ar": "الوصف باللغة التانية"},
    "unit": {"en": "Unit", "ar": "الوحدة"},
    "quantity": {"en": "Quantity", "ar": "الكمية"},
    "rate": {"en": "Rate", "ar": "الفئة"},
    "amount": {"en": "Amount", "ar": "الإجمالي"},
}
BOQ_NOT_USED = {"en": "Not used", "ar": "مش مستخدم"}
BOQ_FILE = {"en": "the BOQ file", "ar": "ملف المقايسة"}
DOING_BOQ_PREVIEW = {
    "en": "Look at the BOQ columns in {name}",
    "ar": "يبص على أعمدة المقايسة في {name}",
}
BOQ_NOT_EXCEL = {
    "en": "This file is not an Excel workbook or PDF BOQ; files_read reads it.",
    "ar": "الملف ده مش ملف Excel أو مقايسة PDF؛ files_read بيقراه.",
}
BOQ_PDF_NO_TABLES = {
    "en": "No tables were found in this PDF; files_read reads its text.",
    "ar": "مالقيناش جداول في ملف PDF ده؛ files_read بيقرا النص اللي فيه.",
}
BOQ_NO_ROWS = {
    "en": "No BOQ rows were found below the header row with these columns. Check the header row "
    "and the columns with boq_preview.",
    "ar": "مالقيناش صفوف مقايسة تحت صف العناوين بالأعمدة دي. راجع صف العناوين والأعمدة بـ "
    "boq_preview.",
}
BOQ_ASK_CURRENCY = {
    "en": "The BOQ's rates and amounts don't say their currency. Which currency are they in?",
    "ar": "الفئات والإجماليات في المقايسة مش مكتوب عملتها. هي بأنهي عملة؟",
}
BOQ_NEEDS_CURRENCY = {
    "en": "Rates and amounts need their currency: three letters, e.g. EGP, SAR, AED.",
    "ar": "الفئات والإجماليات محتاجة عملتها: تلات حروف، زي EGP أو SAR أو AED.",
}
# The card that shows the column mapping before anything is written.
BOQ_CONFIRM_TITLE = {
    "en": "Import the BOQ from {name}, sheet {sheet}?",
    "ar": "أستورد المقايسة من {name}، شيت {sheet}؟",
}
# {items}, {headings} and {count}: counted phrases (counted: ITEMS, HEADINGS, ROWS)
BOQ_CONFIRM_DETAIL = {
    "en": "Rows {first} to {last}: {items} and {headings}.",
    "ar": "الصفوف من {first} لـ {last}: {items} و{headings}.",
}
BOQ_CONFIRM_SKIPPED = {"en": "Left out: {count}.", "ar": "واتساب {count}."}
BOQ_CONFIRM_TICK = {
    "en": "Check what each column holds and change any that is wrong. A column set to «Not used» "
    "is left out.",
    "ar": "راجع كل عمود فيه إيه، وغيّر اللي غلط. العمود اللي «مش مستخدم» مش هيتستورد.",
}
BOQ_CONFIRM_HIDDEN = {
    "en": "Hidden in Excel and left out: {count}.",
    "ar": "مخفي في Excel ومتساب: {count}.",
}
BOQ_CONFIRM_HIDDEN_IN = {
    "en": "Hidden in Excel and included: {count}.",
    "ar": "مخفي في Excel وداخل في الاستيراد: {count}.",
}
BOQ_CONFIRM_FLAGGED = {
    "en": "With hidden text (white, tiny or invisible) or what looks like orders to an AI: "
    "{count}. Imported as data only.",
    "ar": "فيه نص مخفي (أبيض أو صغير جداً أو مش ظاهر) أو كلام شكله أوامر لذكاء اصطناعي: "
    "{count}. بيتستورد كبيانات بس.",
}
BOQ_CARD_COLUMNS = {
    "meaning": {"en": "What it holds", "ar": "فيه إيه"},
    "column": {"en": "Column", "ar": "العمود"},
    "header": {"en": "Its heading in the file", "ar": "عنوانه في الملف"},
    "example": {"en": "First values", "ar": "أول القيم"},
}
BOQ_NOT_CONFIRMED = {
    "en": "The engineer did not confirm the columns, so nothing was imported.",
    "ar": "المهندس ماأكدش الأعمدة، فمااتستوردش حاجة.",
}
BOQ_REQUIRED_UNTICKED = {
    "en": "The engineer did not set the {fields} column, so nothing was imported.",
    "ar": "المهندس ماحددش عمود {fields}، فمااتستوردش حاجة.",
}
BOQ_MEANING_TWICE = {
    "en": "The engineer set {fields} on more than one column, so nothing was imported.",
    "ar": "المهندس حدد {fields} لأكتر من عمود، فمااتستوردش حاجة.",
}

# Evidence for numbers.
SOURCE_NOT_EVIDENCE = {
    "en": (
        "A source must point to real evidence: a file and its page or row, a web page ONE read, "
        "a QS Mind price, or the engineer's answer."
    ),
    "ar": (
        "المصدر لازم يشاور على دليل حقيقي: ملف وصفحته أو صفه، أو صفحة ويب ONE قراها، "
        "أو سعر من QS Mind، أو رد المهندس."
    ),
}
CLIENT_ITEMS_IMPORTED = {
    "en": "The client's BOQ items come only from the engineer's import or an accepted change. "
    "Record a breakdown's parts as resource items, and a condition or a contract's data as its "
    "own kind; a new row in a Deliverable is proposed there as a change.",
    "ar": "بنود مقايسة العميل بتيجي من استيراد المهندس أو تعديل اتقبل بس. سجّل مكونات التحليل "
    "كموارد، والشروط وبيانات العقد كنوع لوحدها؛ والصف الجديد في مستند بيتقترح هناك كتعديل.",
}
NUMBER_NEEDS_CALC = {
    "en": (
        "A computed number comes only from the QS Calc Engine. "
        "Send the formula there; it records the result with its sources."
    ),
    "ar": "الرقم المحسوب بييجي من محرك الحسابات بس. ابعت المعادلة هناك؛ هو بيسجل النتيجة بمصادرها.",
}

# What to keep.
KEEP_ASK = {"en": "Keep {kind} in your records?", "ar": "أحفظ {kind} في سجلاتك؟"}
KEEP_NEVER = {
    "en": "Not kept: you chose never to keep {kind}.",
    "ar": "ماتحفظش: إنت اخترت ماتتحفظش {kind} أبداً.",
}
KEEP_ENGINEER_ASK = {
    "en": "Keep this for all your projects?",
    "ar": "أحفظ ده لكل مشاريعك؟",
}
KEEP_KINDS = {
    "phone": {"en": "phone numbers", "ar": "أرقام التليفون"},
    "email": {"en": "email addresses", "ar": "الإيميلات"},
    "person_name": {"en": "people's names", "ar": "أسامي الأشخاص"},
    "address": {"en": "addresses", "ar": "العناوين"},
    "national_id": {"en": "ID numbers", "ar": "أرقام البطاقات"},
    "whatsapp": {"en": "WhatsApp numbers", "ar": "أرقام الواتساب"},
}
# Task 7: the what-to-keep question's options and words, and the Engineer Records card.
KEEP_OPTION_KEEP = {"en": "Keep", "ar": "احفظ"}
KEEP_OPTION_NEVER = {"en": "Never keep", "ar": "ماتحفظش أبداً"}
KEEP_DETAIL = {
    "en": "{agent} is writing {kind} into your records. ONE asks once and remembers your answer "
    "for every project.",
    "ar": "{agent} بيكتب {kind} في سجلاتك. ONE بيسأل مرة واحدة وبيفتكر ردك لكل المشاريع.",
}
KEEP_ENGINEER_DETAIL = {
    "en": "{agent}: {action}. It goes into your Engineer Records, which every project can use. "
    "ONE asks once in this Brief.",
    "ar": "{agent}: {action}. ده هيتحفظ في سجلات المهندس، واللي كل مشاريعك تقدر تستخدمها. "
    "ONE بيسأل مرة واحدة في الطلب ده.",
}
ENGINEER_RECORDS_CLOSED = {
    "en": "Engineer Records is not open, so ONE cannot use it now.",
    "ar": "سجلات المهندس مش مفتوحة، فـ ONE مش هيقدر يستخدمها دلوقتي.",
}
# How a source got its date, when the evidence shows none of its own.
DATED_RECEIVED = {"en": "date received", "ar": "تاريخ الاستلام"}
DATED_READ = {"en": "date read", "ar": "تاريخ القراية"}
TOOL_NOTE_LESSON = {"en": "Noting a lesson learned", "ar": "بيسجّل درس مستفاد"}

# Prices.
PRICES_ASK = {
    "en": "Keep these prices? Tick the rows to keep.",
    "ar": "أحفظ الأسعار دي؟ علّم على الصفوف اللي تتحفظ.",
}
PRICES_NOT_SUBSCRIBED = {
    "en": (
        "QS Mind Prices come with a QS Mind subscription. "
        "Showing your own prices and this project's."
    ),
    "ar": "أسعار QS Mind بتيجي مع اشتراك QS Mind. بنعرض أسعارك وأسعار المشروع ده.",
}
PRICES_OFFLINE = {
    "en": "No internet: showing the QS Mind prices saved on {date}.",
    "ar": "مفيش نت: بنعرض أسعار QS Mind المحفوظة يوم {date}.",
}
PRICES_DOWN = {
    "en": "QS Mind Prices did not answer. Showing the prices saved on {date}.",
    "ar": "أسعار QS Mind مارَدّتش. بنعرض الأسعار المحفوظة يوم {date}.",
}
PRICES_NONE_FOUND = {
    "en": "No price was found for this item. Try other words, or search the market.",
    "ar": "مالقيناش سعر للبند ده. جرّب كلام تاني، أو دوّر في السوق.",
}
PRICES_COUNTRY = {
    "en": "Prices cover Egypt, Saudi Arabia and the UAE: send EG, SA or AE.",
    "ar": "الأسعار لمصر والسعودية والإمارات: ابعت EG أو SA أو AE.",
}
PRICES_ON_DEVICE = {
    "en": "This is an On-device Project, so ONE did not fetch QS Mind Prices: showing the "
    "prices saved on {date}.",
    "ar": "ده مشروع على الجهاز، فـ ONE ماجابش أسعار QS Mind: بنعرض الأسعار المحفوظة يوم {date}.",
}
PRICES_NONE_SAVED = {
    "en": "No QS Mind prices are saved on this computer yet, and ONE could not get them now. "
    "Showing your own prices and this project's.",
    "ar": "مفيش أسعار QS Mind محفوظة على الجهاز لسه، و ONE مقدرش يجيبها دلوقتي. "
    "بنعرض أسعارك وأسعار المشروع ده.",
}
PRICES_FOR_ALL = {
    "en": "{agent} proposes these prices. The ticked ones go into your Engineer Records, "
    "for every project, with this card as their source.",
    "ar": "{agent} بيقترح الأسعار دي. اللي تعلّم عليها هتتحفظ في سجلات المهندس، لكل مشاريعك، "
    "والبطاقة دي مصدرها.",
}
PRICES_FOR_PROJECT = {
    "en": "{agent} proposes these prices. The ticked ones are kept in this project, each with "
    "its source.",
    "ar": "{agent} بيقترح الأسعار دي. اللي تعلّم عليها هتتحفظ في المشروع ده، كل واحد بمصدره.",
}
PRICES_COLUMNS = {
    "description": {"en": "Item", "ar": "البند"},
    "unit": {"en": "Unit", "ar": "الوحدة"},
    "rate": {"en": "Rate", "ar": "السعر"},
    "currency": {"en": "Currency", "ar": "العملة"},
    "vat": {"en": "VAT", "ar": "الضريبة"},
    "dated": {"en": "Date", "ar": "التاريخ"},
    "supplier": {"en": "Supplier", "ar": "المورّد"},
}
# A price's VAT basis, as QS Mind Prices states it.
PRICES_VAT = {
    "incl": {"en": "VAT included", "ar": "شامل الضريبة"},
    "excl": {"en": "VAT not included", "ar": "من غير الضريبة"},
    "na": {"en": "No VAT", "ar": "مفيش ضريبة"},
    "unknown": {"en": "VAT not stated", "ar": "الضريبة مش مذكورة"},
}
TOOL_PRICES_PROPOSE = {
    "en": "Proposing prices for you to keep",
    "ar": "بيقترح أسعار عشان تحفظها",
}

# The Sandbox.
SANDBOX_NOT_READY = {
    "en": (
        "The Sandbox's Python is missing or damaged, so no code ran. "
        "ONE downloads it again (about 16 MB) the next time a script runs."
    ),
    "ar": (
        "بايثون الصندوق المعزول ناقص أو بايظ، فمفيش كود اشتغل. "
        "ONE هينزّله تاني (حوالي 16 ميجا) أول ما سكريبت يشتغل."
    ),
}
SANDBOX_DOWNLOAD_FAILED = {
    "en": (
        "The Sandbox's Python did not download (no internet, or the server did not answer). "
        "What came so far is kept. Try again."
    ),
    "ar": (
        "بايثون الصندوق المعزول مانزلش (مفيش نت، أو السيرفر مارَدّش). "
        "اللي نزل لحد دلوقتي محفوظ. جرّب تاني."
    ),
}
SANDBOX_NO_SPACE = {
    "en": (
        "There is not enough free space: the Sandbox's Python needs about 300 MB while it "
        "downloads. Free some space, then try again."
    ),
    "ar": (
        "مفيش مساحة فاضية كفاية: بايثون الصندوق المعزول محتاج حوالي 300 ميجا وهو بينزل. "
        "فضّي شوية مساحة وجرّب تاني."
    ),
}
SANDBOX_SCRIPT_TOO_BIG = {
    "en": (
        "The script is larger than 200 KB. "
        "Send a shorter one that reads its data from the input files."
    ),
    "ar": "السكريبت أكبر من 200 كيلو. ابعت واحد أقصر بيقرا بياناته من ملفات الإدخال.",
}
SANDBOX_RUN_UNKNOWN = {
    "en": "There is no Sandbox run with this id here. A sandbox_run result gives its run id.",
    "ar": "مفيش تشغيلة في الصندوق المعزول بالرقم ده هنا. نتيجة sandbox_run فيها رقم التشغيلة.",
}
SANDBOX_SYNTAX = {
    "en": "The script has a mistake on line {line}: {message}",
    "ar": "في غلطة في السكريبت في سطر {line}: {message}",
}
SANDBOX_MODULE = {
    "en": (
        "The Sandbox has Python's own modules plus openpyxl and xlrd only. "
        "Rewrite the script without {module}."
    ),
    "ar": (
        "الصندوق المعزول فيه موديولات بايثون الأساسية ومعاها openpyxl و xlrd بس. "
        "اكتب السكريبت من غير {module}."
    ),
}
SANDBOX_TIMEOUT = {
    "en": "The script ran longer than {seconds} seconds and was stopped.",
    "ar": "السكريبت اشتغل أكتر من {seconds} ثانية فاتوقف.",
}
SANDBOX_MEMORY = {
    "en": "The script used more than 512 MB of memory and was stopped.",
    "ar": "السكريبت استهلك أكتر من 512 ميجا من الذاكرة فاتوقف.",
}
SANDBOX_TOO_MUCH = {
    "en": "The script's files are larger than 64 MB in all.",
    "ar": "ملفات السكريبت أكبر من 64 ميجا في المجموع.",
}
SANDBOX_FAILED = {
    "en": "The script stopped with an error; its last lines are below.",
    "ar": "السكريبت وقف بغلطة؛ آخر سطوره تحت.",
}

# Connectors.
CONNECTOR_ASK_ADD = {
    "en": "Add the {connector} Connector? It can:",
    "ar": "أضيف موصّل {connector}؟ يقدر:",
}
CONNECTOR_NOT_FOUND = {
    "en": "There is no Connector with this name. connector_tools lists them.",
    "ar": "مفيش موصّل بالاسم ده. connector_tools بيعرضهم.",
}
CONNECTOR_OFF = {"en": "This Connector is switched off.", "ar": "الموصّل ده مقفول."}
CONNECTOR_DOWN = {
    "en": "The Connector did not start or did not answer. Check it, then try again.",
    "ar": "الموصّل ماشتغلش أو مارَدّش. راجعه وجرّب تاني.",
}
CONNECTOR_TOOL_UNKNOWN = {
    "en": "This Connector has no tool by that name; connector_tools lists them.",
    "ar": "الموصّل ده مفيهوش أداة بالاسم ده؛ connector_tools بيعرضهم.",
}
CONNECTOR_RUNS = {
    "en": "It runs on this computer: {command}",
    "ar": "بيشتغل على الجهاز ده: {command}",
}
CONNECTOR_REACHES = {
    "en": "It reaches a server over the internet: {url}",
    "ar": "بيوصل لسيرفر على النت: {url}",
}
CONNECTOR_NAME_TAKEN = {
    "en": "A Connector with this name is already added. Choose another name.",
    "ar": "في موصّل بالاسم ده متضاف قبل كده. اختار اسم تاني.",
}
CONNECTOR_BAD = {
    "en": "Give the Connector a name of 2 to 40 small letters, digits or dashes, and either "
    "the command that runs it or its https:// address.",
    "ar": "سمّي الموصّل باسم من 2 لـ 40 حرف إنجليزي صغير أو رقم أو شرطة، واكتب يا الأمر اللي "
    "بيشغّله يا عنوانه اللي بيبدأ بـ https://.",
}
CONNECTOR_CARD_GONE = {
    "en": "This Connector card is no longer waiting. Add the Connector again.",
    "ar": "كارت الموصّل ده مبقاش مستني. ضيف الموصّل تاني.",
}

CARD_BAD_ANSWER = {
    "en": "Answer every question: choose an option or write a reply.",
    "ar": "جاوب على كل الأسئلة: اختار اختيار أو اكتب رد.",
}

# Plan 8: journey and release. "Connect AI" / «وصّل الذكاء الاصطناعي» is the first-launch step
# (connectAi in ui/src/i18n.ts). Proposed terms: Backup key / مفتاح النسخة الاحتياطية, Recovery
# code / كود الاسترجاع, Archived project / مشروع مؤرشف.
PROJECT_ARCHIVED = {
    "en": "This project is archived, so it is read-only. Unarchive it to change it.",
    "ar": "المشروع ده مؤرشف، فهو للقراءة بس. لغي الأرشفة عشان تعدّل فيه.",
}
ARCHIVE_BACKUP_FAILED = {
    "en": "The project is archived, but its final backup was not made. Back it up now.",
    "ar": "المشروع اتأرشف، بس آخر نسخة احتياطية ليه ماتعملتش. اعمله نسخة احتياطية دلوقتي.",
}
AI_CONSENT_NEEDED = {
    "en": "Before ONE uses AI, say yes to the note on where your text goes.",
    "ar": "قبل ما ONE يستخدم الذكاء الاصطناعي، وافق على الملاحظة اللي بتوضح نصك بيروح فين.",
}
CLAUDE_CODE_NOT_FOUND = {
    "en": (
        "Claude Code was not found on this computer. Install it, sign in to it once in a "
        "terminal, then try again."
    ),
    "ar": (
        "مالقيناش Claude Code على الجهاز ده. نزّله، وسجّل دخولك فيه مرة من الـ terminal، "
        "وبعدين جرّب تاني."
    ),
}

# The QS Mind account.
ACCOUNT_OFFLINE = {
    "en": "Could not reach the QS Mind account. Check the internet connection, then try again.",
    "ar": "مقدرناش نوصل لحساب QS Mind. اتأكد إن النت شغال وجرّب تاني.",
}
ACCOUNT_REFUSED = {
    "en": "The QS Mind account did not accept this sign-in. Sign in again.",
    "ar": "حساب QS Mind ماقبلش الدخول ده. سجّل دخولك تاني.",
}
ACCOUNT_DENIED = {
    "en": "Sign-in was cancelled in the browser. Sign in again when you are ready.",
    "ar": "الدخول اتلغى من المتصفح. سجّل دخولك تاني لما تكون جاهز.",
}
ACCOUNT_EXPIRED = {
    "en": "The sign-in ran out of time. Sign in again.",
    "ar": "وقت الدخول خلص. سجّل دخولك تاني.",
}
ACCOUNT_KEY_STORE_DOWN = {
    "en": (
        "The system key store is not available, so ONE cannot keep you signed in. "
        "Unlock it or turn it on, then sign in again."
    ),
    "ar": (
        "مخزن المفاتيح في الجهاز مش متاح، فـ ONE مش هيقدر يفضّل دخولك متسجّل. "
        "افتحه أو شغّله وسجّل دخولك تاني."
    ),
}
ACCOUNT_UNAVAILABLE = {  # a build without One's client id at the account (O1)
    "en": "Signing in to the QS Mind account is not ready in this version of ONE yet.",
    "ar": "تسجيل الدخول لحساب QS Mind لسه مش جاهز في النسخة دي من ONE.",
}
ACCOUNT_SIGNED_IN = {  # the loopback page in the browser, after the sign-in
    "en": "Signed in. Go back to ONE.",
    "ar": "دخولك اتسجّل. ارجع لـ ONE.",
}

# Backups, the Backup key and recovery codes.
BACKUP_FOLDER_UNREACHABLE = {
    "en": (
        "The backup folder cannot be reached. The last good backup is from {date}. "
        "Connect its drive, or pick another folder."
    ),
    "ar": (
        "مقدرناش نوصل لفولدر النسخة الاحتياطية. آخر نسخة سليمة بتاريخ {date}. "
        "وصّل الهارد بتاعه، أو اختار فولدر تاني."
    ),
}
BACKUP_FOLDER_NOT_WRITABLE = {
    "en": "ONE cannot save files in this folder. Pick an existing folder you can write in.",
    "ar": "ONE مش قادر يحفظ ملفات في الفولدر ده. اختار فولدر موجود تقدر تكتب فيه.",
}
BACKUP_KEY_WRONG = {
    "en": "This backup was made with another Backup key, so this key cannot open it.",
    "ar": "النسخة دي اتعملت بمفتاح نسخة احتياطية تاني، فالمفتاح ده مش هيفتحها.",
}
BACKUP_NEEDS_SIGN_IN = {
    "en": (
        "To open this backup, sign in to the QS Mind account that keeps its Backup key, "
        "or type its recovery code."
    ),
    "ar": (
        "عشان تفتح النسخة دي، سجّل دخولك بحساب QS Mind اللي فيه مفتاح النسخة الاحتياطية، "
        "أو اكتب كود الاسترجاع بتاعها."
    ),
}
BACKUP_NEEDS_CODE = {
    "en": "Type the recovery code for this backup to open it.",
    "ar": "اكتب كود الاسترجاع بتاع النسخة دي عشان تفتحها.",
}
RECOVERY_CODE_WRONG = {
    "en": (
        "This recovery code does not open this backup. Check each group of five, then try again."
    ),
    "ar": "كود الاسترجاع ده مش بيفتح النسخة دي. راجع كل مجموعة من الخمسة وجرّب تاني.",
}
RECOVERY_LAST_GROUP_WRONG = {
    "en": "That is not the code's last group. Look at the code you saved and type its last five.",
    "ar": "دي مش آخر مجموعة في الكود. بص على الكود اللي حفظته واكتب آخر خمسة فيه.",
}
PROJECT_KEY_RESTORED = {
    "en": (
        "The project's key was missing from the system key store, so ONE put it back from "
        "the project's own key file."
    ),
    "ar": (
        "مفتاح المشروع ماكانش في مخزن المفاتيح في الجهاز، فـ ONE رجّعه من ملف المفتاح "
        "بتاع المشروع نفسه."
    ),
}

# Tender folder import and the "I understood this" card. FACT_* and COUNT_* go back to the Lead
# QS from the card's check, so they say exactly what to send.
ZIP_TOO_BIG = {
    "en": (
        "This zip holds more than 2 GB once opened, so ONE kept it as a file and did not "
        "open it. Unzip it and add the folder instead."
    ),
    "ar": (
        "الملف المضغوط ده بعد ما يتفك أكبر من 2 جيجا، فـ ONE حفظه زي ما هو ومافتحهوش. "
        "فكّه وضيف الفولدر بداله."
    ),
}
ZIP_UNSAFE = {
    "en": (
        "This zip looks unsafe to open (too many files, or packed far too tightly), so ONE "
        "kept it as a file and did not open it."
    ),
    "ar": (
        "الملف المضغوط ده شكله مش أمان يتفتح (ملفات كتير قوي، أو مضغوط بزيادة)، فـ ONE "
        "حفظه زي ما هو ومافتحهوش."
    ),
}
FACT_NEEDS_SOURCE = {
    "en": (
        "{fact} has no source. Send the file_id of the file it comes from and a locator, "
        'such as {{"page": 3}} or {{"sheet": "BOQ", "row": 12}}.'
    ),
    "ar": (
        "{fact} مالوش مصدر. ابعت الـ file_id بتاع الملف اللي جاي منه ومكانه فيه، "
        'زي {{"page": 3}} أو {{"sheet": "BOQ", "row": 12}}.'
    ),
}
FACT_FILE_UNKNOWN = {
    "en": "There is no current file with file_id {file_id}. Use an id that files_list gives.",
    "ar": "مفيش ملف حالي الـ file_id بتاعه {file_id}. استخدم id من اللي files_list بيديه.",
}
FACT_LOCATOR_UNKNOWN = {
    "en": (
        "The locator for {fact} names no page or row of file {file_id}. Read the file with "
        "files_read, then send a page, or a sheet and row, that it has."
    ),
    "ar": (
        "مكان {fact} مش بيشاور على صفحة أو صف موجود في الملف {file_id}. اقرا الملف بـ "
        "files_read، وبعدين ابعت صفحة، أو شيت وصف، موجودين فيه."
    ),
}
FACT_DATE_BAD = {
    "en": "{fact} must be a real date written as YYYY-MM-DD, such as 2026-12-01.",
    "ar": "{fact} لازم يكون تاريخ حقيقي مكتوب YYYY-MM-DD، زي 2026-12-01.",
}
COUNT_NEEDS_TRACE = {
    "en": (
        "items_count must come from code, never be typed: import the BOQ with boq_import and "
        "send its import_id as the trace_id (or the id of a calculation that counts them)."
    ),
    "ar": (
        "items_count لازم ييجي من الكود، ومايتكتبش باليد: استورد جدول الكميات بـ boq_import "
        "وابعت الـ import_id بتاعه كـ trace_id (أو id حساب بيعدّهم)."
    ),
}
FACT_SUBMISSION_DATE = {"en": "The submission date", "ar": "ميعاد التقديم"}
UNDERSTAND_BRIEF = {
    "en": "Read the tender folder I just added and fill in the “I understood this” card.",
    "ar": "اقرا فولدر المناقصة اللي لسه ضايفه واملا بطاقة «فهمت كده».",
}
LESSONS_BRIEF = {
    "en": "Before I close this project, propose the lessons learned from how we worked on it.",
    "ar": "قبل ما أقفل المشروع ده، اقترح الدروس المستفادة من طريقة شغلنا فيه.",
}
LESSON_STAYS_CONFIDENTIAL = {
    "en": "This is a Confidential Project, so its lessons stay in it.",
    "ar": "ده مشروع سري، فدروسه بتفضل جوّاه.",
}
LESSON_NOT_FOUND = {
    "en": "This lesson is not in the project.",
    "ar": "الدرس ده مش موجود في المشروع.",
}
ARCHIVE_WAITS_FOR_BRIEF = {
    "en": "A Brief is still running in this project. Let it finish or stop it, then archive.",
    "ar": "فيه تكليف لسه شغال في المشروع ده. استنى لما يخلص أو وقّفه، وبعدين أرشف.",
}

# The updater.
UPDATE_FAILED = {
    "en": (
        "The update did not install, so ONE is still on this version and your projects are "
        "as they were. Try again later."
    ),
    "ar": "التحديث ماتسطبش، فـ ONE لسه على النسخة دي ومشاريعك زي ما هي. جرّب تاني بعدين.",
}
UPDATE_OFFLINE = {
    "en": "Could not check for updates. Check the internet connection, then try again.",
    "ar": "مقدرناش ندوّر على تحديثات. اتأكد إن النت شغال وجرّب تاني.",
}


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

# ---------------------------------------------------------------------------------------------
# What the screen can add to a text: the action that fixes it, for the place it shows in.
# "ai": AI settings ("Open AI settings" in the chat; nothing more in AI settings or the first
# launch's Connect AI, where the fix is already in place). "consent": the first launch's Connect
# AI step. "retry": the same check once more ("Try again"). "backup": the Backup panel.
# ---------------------------------------------------------------------------------------------
FIXES = {
    "ai": (
        NO_KEY,
        KEY_REFUSED,
        NO_AI,
        AI_KEY_REFUSED,
        PRICE_UNKNOWN,
        MODEL_GONE_TRY,
        MODEL_GONE,
    ),
    # the web search setting, in AI settings (audit B8)
    "search": (WEB_NO_SEARCH, WEB_SEARCH_KEY_REFUSED, WEB_SEARCH_LIMIT),
    "consent": (AI_CONSENT_NEEDED,),
    "retry": (
        KEY_STORE_DOWN,
        NO_CONNECTION,
        CLAUDE_BUSY,
        MODELS_FAILED,
        AI_NO_CONNECTION,
        AI_BUSY,
        AI_CHECK_FAILED,
        CLAUDE_CODE_MISSING,
        CLAUDE_CODE_TOO_OLD,
        CLAUDE_CODE_SHIM,
        CLAUDE_CODE_SIGNED_OUT,
        CLAUDE_CODE_NOT_FOUND,
    ),
    "backup": (ARCHIVE_BACKUP_FAILED,),
}


def _shape(text: dict[str, str]) -> re.Pattern:
    """The English words of `text`, with any value in each {placeholder}."""
    pieces = re.split(r"\{[a-z_]+\}", text["en"])
    return re.compile(".+?".join(re.escape(piece) for piece in pieces), re.S)


_FIX_SHAPES = [(fix, _shape(text)) for fix, found in FIXES.items() for text in found]


def fix_of(text: object) -> str | None:
    """The action that fixes `text` (one of FIXES, filled or not), or None."""
    if not isinstance(text, dict) or not isinstance(text.get("en"), str):
        return None
    return next((fix for fix, shape in _FIX_SHAPES if shape.fullmatch(text["en"])), None)


def error(text: dict[str, str]) -> dict:
    """A JSON error body: `{"error": text}`, and its `fix` when the screen can add one."""
    fix = fix_of(text)
    return {"error": text} if fix is None else {"error": text, "fix": fix}


# PDF page-region comments (Wave 1 E).
FILE_REGION_PLACE = {
    "en": "file {file}, page {page}, box {box}",
    "ar": "الملف {file}، صفحة {page}، المنطقة {box}",
}
FILE_REGION_FIX = {
    "en": "Review the comment on file {file}, page {page}, box {box}: {body}",
    "ar": "راجع التعليق على الملف {file}، صفحة {page}، المنطقة {box}: {body}",
}

# Tender packs (wave 1 A).
PACK_INVALID = {
    "en": "This pack step is invalid. Choose pages that exist and paired text.",
    "ar": "الخطوة دي مش صالحة. اختار صفحات موجودة ونص بالعربي والإنجليزي.",
}
PACK_PAGE = {"en": "Page {n} of {total}", "ar": "صفحة {n} من {total}"}
PACK_SEAL = {
    "en": (
        "The free seal proves the file was not changed after sealing. "
        "It is not a licensed e-signature."
    ),
    "ar": "الختم المجاني بيثبت إن الملف ماتغيرش بعد الختم. ده مش توقيع إلكتروني معتمد.",
}
PACK_KEY_UNAVAILABLE = {
    "en": "ONE could not access the key store to seal this pack.",
    "ar": "ONE مش قادر يوصل لمخزن المفاتيح عشان يختم الحزمة.",
}
PACK_LABELS = {
    "file": {"en": "File pages", "ar": "صفحات الملف"},
    "cover": {"en": "Cover", "ar": "الغلاف"},
    "divider": {"en": "Divider", "ar": "فاصل"},
    "stamp": {"en": "Stamp", "ar": "ختم نصّي"},
    "page_numbers": {"en": "Page numbers", "ar": "ترقيم الصفحات"},
    "seal": {"en": "Free integrity seal", "ar": "ختم سلامة مجاني"},
    "top": {"en": "Top", "ar": "فوق"},
    "center": {"en": "Center", "ar": "في النص"},
    "bottom": {"en": "Bottom", "ar": "تحت"},
}
PACK_LOCKED = {
    "en": "This PDF needs a password. Add an unlocked copy to the project to include its pages.",
    "ar": "الـ PDF ده محتاج كلمة سر. ضيف نسخة مفتوحة للمشروع عشان تستخدم صفحاته.",
}

# Revision comparison: observed words/pixels only, never inferred engineering changes.
COMPARE_PAIRING_REVIEW = {
    "en": "This sheet pairing needs a look: more than one sheet number was found on a page.",
    "ar": "ربط اللوحتين محتاج نظرة: لقينا أكتر من رقم لوحة في صفحة.",
}
COMPARE_TEXT = {"en": "Page words changed.", "ar": "كلمات الصفحة اتغيّرت."}
COMPARE_PIXELS = {"en": "Page image changed.", "ar": "صورة الصفحة اتغيّرت."}
COMPARE_TEXT_PIXELS = {"en": "Page words and image changed.", "ar": "كلمات وصورة الصفحة اتغيّروا."}
COMPARE_WIDTH = {
    "en": "Choose a supported page image size.",
    "ar": "اختار مقاس مدعوم لصورة الصفحة.",
}
COMPARE_STEP = {"en": "Comparing file revisions", "ar": "بيقارن نسخ الملفات"}

BOQ_SCAN_NEEDS_READING = {
    "en": (
        "These scanned BOQ pages need reading first. Ask ONE to read them, or call files_read "
        "with ocr=true, then preview the BOQ again."
    ),
    "ar": (
        "صفحات المقايسة المتصورة دي محتاجة تتقري الأول. اطلب من ONE يقراها، أو استخدم "
        "files_read مع ocr=true، وبعدها اعرض المقايسة تاني."
    ),
}
OCR_ARABIC_MISSING = {
    "en": (
        "ONE read with English OCR only. Arabic reading needs the Arabic model "
        "(ara.traineddata). ONE could not download it to {folder}. "
        "It will download when online, with enough free space, "
        "the next time ONE reads a page using OCR."
    ),
    "ar": (
        "ONE قرا بالإنجليزي بس. قراية العربي محتاجة نموذج العربي (ara.traineddata). "
        "ONE مقدرش ينزّله في {folder}. هينزّله لما الإنترنت يرجع وتبقى فيه مساحة كفاية، "
        "أول ما ONE يقرا صفحة من الصورة."
    ),
}

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

TOOL_PRICE_FROM_SHEET = {
    "en": "Price existing BOQ items from build-up cells",
    "ar": "يسعّر بنود المقايسة الموجودة من خلايا تحليل السعر",
}
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

FILE_DRAWINGS_MISSING = {
    "en": "Kept. ONE's drawing reader is unavailable on this computer.",
    "ar": "اتحفظ. قارئ الرسومات بتاع ONE مش متاح على الجهاز ده.",
}
FILE_DRAWINGS_LIMIT = {
    "en": "Kept. This drawing exceeds the local reader's size limit.",
    "ar": "اتحفظ. حجم الرسم ده أكبر من حد القارئ المحلي.",
}
FILE_DRAWINGS_REPAIRED = {
    "en": "Read with repairs or limits. Some drawing content may be missing.",
    "ar": "اتقرا بإصلاحات أو حدود. ممكن يكون فيه محتوى ناقص من الرسم.",
}
FILE_DRAWING_PREVIEW = {
    "en": "A drawing preview is not available yet; ONE shows the text it read from the drawing.",
    "ar": "معاينة الرسم لسه مش متاحة؛ ONE بيعرض النص اللي قراه من الرسم.",
}
REPORT_DRAWING = {
    "en": "Drawing, {sheets} sheets: {index}",
    "ar": "رسم، {sheets} لوحات: {index}",
}

REPORT_DRAWING_REV = {"en": "rev {revision}", "ar": "مراجعة {revision}"}

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
MAP_AI_RUN = {"en": "Map them", "ar": "خطّطهم"}

MAP_AI_FAILED_REASON = {
    "en": "the AI request failed",
    "ar": "طلب الذكاء الاصطناعي فشل",
}
MAP_AI_FAILED = {
    "en": "ONE could not map {count} files with the AI: {reason}. Local reading is kept.",
    "ar": "ONE مقدرش يعمل خريطة {count} ملف بالذكاء الاصطناعي: {reason}. القراية المحلية محفوظة.",
}

READ_ALREADY = {
    "en": "already read in this Brief; use the text already read or read another page/file.",
    "ar": "ONE قرا ده في الطلب ده؛ استخدم النص اللي اتقرا أو اقرا صفحة أو ملف تاني.",
}
READ_REPEAT_NOW = (
    "Stop searching: three identical reads were repeated. Answer using only what you have. "
    "For each remaining question say plainly 'not found in the files read: …'. "
    "A dotted or underscored template field is 'left blank in the tender documents' "
    "with its file and page, not an unknown value to search for. No more tools."
)
READ_TEMPLATE_BLANK = {
    "en": "A dotted/underscored template field is left blank in the tender documents. "
    "Report that with its file and page; do not invent its value.",
    "ar": "الخانة اللي فيها نقط أو شرطات سفلية متسابة فاضية في مستندات المناقصة. "
    "قول ده مع اسم الملف والصفحة؛ ماتخمنش قيمتها.",
}

READ_REPEAT_LIMIT = {
    "en": "ONE stopped searching after three repeated reads and will answer from the files read.",
    "ar": "ONE وقف البحث بعد تكرار القراية تلات مرات وهيرد من الملفات اللي قراها.",
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


MODEL_STOPPED = {
    "en": "ONE stopped using {model}: {provider} says it is no longer available.",
    "ar": "ONE بطل يستخدم {model}: {provider} بيقول إنه مبقاش متاح.",
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
