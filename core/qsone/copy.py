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

# Project Records: projects.
PROJECT_NOT_FOUND = {
    "en": "This project is not on this computer.",
    "ar": "المشروع ده مش موجود على الجهاز ده.",
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
        "The system key store is not available, so One cannot use the project's key. "
        "Unlock it or turn it on, then try again."
    ),
    "ar": (
        "مخزن المفاتيح في الجهاز مش متاح، فـ One مش قادر يوصل لمفتاح المشروع. "
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
    "en": "A newer version of One saved this project. Update One, then open it.",
    "ar": "المشروع ده اتحفظ بنسخة أحدث من One. حدّث One وبعدين افتحه.",
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

FILE_NOT_READ_YET = {
    "en": "Kept in Project Records. One cannot read this kind of file yet.",
    "ar": "اتحفظ في سجلات المشروع. One لسه مش بيقرا النوع ده من الملفات.",
}

FILE_SCANNED_PAGES = {
    "en": "Some pages have no text layer (they are scanned), so they cannot be searched yet.",
    "ar": "في صفحات مفيهاش نص (متصورة سكانر)، فلسه مش هينفع ندوّر فيها.",
}

FILE_UNREADABLE = {
    "en": "Kept, but One could not read it (it is damaged, or locked with a password).",
    "ar": "اتحفظ، بس One مقدرش يقراه (يا إما بايظ، يا إما مقفول بباسورد).",
}

SEARCH_WORDS_ONLY = {
    "en": "Searching by words only until search by meaning is ready.",
    "ar": "البحث بالكلمات بس لحد ما البحث بالمعنى يجهز.",
}

SEARCH_SUPERSEDED = {
    "en": "A newer search took its place.",
    "ar": "في بحث أحدث خد مكانه.",
}

# Search by meaning: the search model ("Search model" / «نموذج البحث» in the glossary).
MEANING_DOWNLOAD_FAILED = {
    "en": (
        "The search model did not download (no internet, or the server did not answer). "
        "What came so far is kept. Try again."
    ),
    "ar": "نموذج البحث مانزلش (مفيش نت، أو السيرفر مارَدّش). اللي نزل لحد دلوقتي محفوظ. جرّب تاني.",
}

MEANING_FILE_DAMAGED = {
    "en": "A downloaded file did not match its check, so it was deleted. Try again.",
    "ar": "ملف من اللي نزلوا ماطابقش الفحص بتاعه، فاتمسح. جرّب تاني.",
}

MEANING_NO_SPACE = {
    "en": (
        "There is not enough free space: the search model needs about 1.2 GB. "
        "Free some space, then try again."
    ),
    "ar": "مفيش مساحة فاضية كفاية: نموذج البحث محتاج حوالي 1.2 جيجا. فضّي شوية مساحة وجرّب تاني.",
}

MEANING_NOT_ON_THIS_COMPUTER = {
    "en": "Search by meaning cannot run on this computer. Search by words works as usual.",
    "ar": "البحث بالمعنى مش هينفع يشتغل على الجهاز ده. البحث بالكلمات شغال عادي.",
}

MEANING_NOT_READY = {
    "en": "Search by meaning is not ready yet.",
    "ar": "البحث بالمعنى لسه مجهزش.",
}

MEANING_MODEL_FAILED = {
    "en": "The search model would not start, so it will be downloaded again.",
    "ar": "نموذج البحث ماشتغلش، فهيتنزّل تاني.",
}

MEANING_INDEX_FAILED = {
    "en": "Preparing search by meaning stopped on this project. Try again.",
    "ar": "تجهيز البحث بالمعنى وقف في المشروع ده. جرّب تاني.",
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

# "AI" / «الذكاء الاصطناعي» is the header button that opens AI settings (`ai` in ui/src/i18n.ts):
# the reply when no AI is connected at all.
NO_AI = {
    "en": (
        "No AI is connected yet. Press “AI” at the top and add a Claude key, another AI "
        "provider, or your own Claude Code, then send your message again."
    ),
    "ar": (
        "لسه مفيش ذكاء اصطناعي متوصّل. دوس على «الذكاء الاصطناعي» فوق وضيف مفتاح Claude، "
        "أو مزوّد تاني، أو Claude Code بتاعك، وبعدين ابعت رسالتك تاني."
    ),
}

# Model errors for any AI Connector; KEY_REFUSED and the others above stay for the Native Link.
AI_KEY_REFUSED = {
    "en": "The {provider} key was refused. Check it in “AI” at the top, or add a new one.",
    "ar": "مفتاح {provider} اترفض. راجعه من «الذكاء الاصطناعي» فوق، أو ضيف مفتاح جديد.",
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
        "One paused at 80% of the Spending Cap for {scope_name}: {spent} of {cap} USD spent. "
        "Continue up to the cap, raise the cap, or stop with a report?"
    ),
    "ar": (
        "One وقّف عند 80% من سقف الصرف بتاع {scope_name}: اتصرف {spent} من {cap} دولار. "
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
        "for {scope_name}, {cap} USD. It is not billed per use, so One carries on."
    ),
    "ar": (
        "التكلفة المكافئة على اشتراك Claude بتاعك وصلت {spent} من سقف الصرف بتاع {scope_name}، "
        "{cap} دولار. الاشتراك مش بيتحاسب على كل استخدام، فـOne هيكمّل."
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
        "One does not know the price of {model}, so the Spending Cap cannot protect you. "
        "Enter its price in “AI” at the top, or mark it as running on this computer. "
        "Use it anyway in this Brief?"
    ),
    "ar": (
        "One مش عارف سعر {model}، فسقف الصرف مش هيقدر يحميك. "
        "اكتب سعره في «الذكاء الاصطناعي» فوق، أو علّم عليه إنه شغال على الجهاز ده. "
        "نستخدمه برضه في التكليف ده؟"
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
TOOL_WORKING = {"en": "Using {tool}", "ar": "بيستخدم {tool}"}

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
    "ar": "بيسجّل {name} البند {item} بمصدره",
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

BUDGET_UNKNOWN = {
    "en": (
        "One cannot tell what this Brief will cost: a model in its plan has no known price. "
        "It should take about {minutes} minutes. Start?"
    ),
    "ar": (
        "One مش عارف التكليف ده هيكلّف كام: في نموذج في الخطة سعره مش معروف. "
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
        "Claude Code was not found on this computer. "
        "Install it from https://code.claude.com/docs/en/setup, or pick its file."
    ),
    "ar": (
        "Claude Code مش موجود على الجهاز ده. "
        "نزّله من https://code.claude.com/docs/en/setup، أو اختار الملف بتاعه."
    ),
}

CLAUDE_CODE_TOO_OLD = {
    "en": "Your Claude Code lacks options One needs. Update it, then check again.",
    "ar": "Claude Code اللي عندك ناقصه اختيارات One محتاجها. حدّثه وبعدين افحص تاني.",
}

CLAUDE_CODE_SHIM = {
    "en": (
        "This is the npm claude.cmd, which One cannot run safely. "
        "Install the native Claude Code, then pick it."
    ),
    "ar": (
        "ده claude.cmd بتاع npm، وOne مش هيقدر يشغّله بأمان. نزّل Claude Code الأصلي وبعدين اختاره."
    ),
}

CLAUDE_CODE_SIGNED_OUT = {
    "en": "Claude Code is signed out. Open Claude Code once and sign in, then try again.",
    "ar": "Claude Code مش مسجّل دخول. افتح Claude Code مرة وسجّل دخول، وبعدين جرّب تاني.",
}

CLAUDE_CODE_LIMIT = {
    "en": (
        "Your Claude subscription's limit is reached for now. "
        "One waits, or moves the role to another model you have."
    ),
    "ar": "اشتراك Claude بتاعك وصل لحدّه دلوقتي. One هيستنى، أو هينقل الدور لنموذج تاني عندك.",
}

CLAUDE_CODE_COPY = {
    "en": (
        "Claude Code keeps its own copy of each conversation on this computer, "
        "outside One's encrypted files."
    ),
    "ar": "Claude Code بيحتفظ بنسخة خاصة بيه من كل محادثة على الجهاز ده، برّه ملفات One المتشفّرة.",
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

CONTINUE_AFTER_RESTART = "One restarted. Continue from your last step."  # the model reads it

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


def fill(text: dict[str, str], /, **values) -> dict[str, str]:
    """Both languages of `text` with its {placeholders} filled from `values`.

    A value that is itself an {en, ar} pair gives each language its own words."""
    return {
        lang: s.format(**{k: v[lang] if isinstance(v, dict) else v for k, v in values.items()})
        for lang, s in text.items()
    }


# The formula.
CALC_UNEXPECTED = {
    "en": (
        "At character {at}, «{found}» was not expected; One expected {expected}. "
        "Numbers have no thousands separators."
    ),
    "ar": (
        "عند الحرف {at}، «{found}» مش مكانه هنا؛ One كان مستني {expected}. "
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
    "ar": "«{symbol}» وحدة أساسية في One؛ مينفعش تتعرّف تاني.",
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
CHANGE_STALE = {
    "en": "This cell changed after the change was suggested. Ask One again, or edit it yourself.",
    "ar": "الخلية دي اتغيرت بعد ما التعديل اتقترح. اطلب من One تاني، أو عدّلها بنفسك.",
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

# Accepting while Project Records moved.
UPDATE_FIRST = {
    "en": (
        "First review «Update from Project Records»: "
        "the Project Records changed since this version."
    ),
    "ar": "راجع «تحديث من سجلات المشروع» الأول: سجلات المشروع اتغيرت من ساعة الإصدار ده.",
}
