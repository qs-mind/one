"""The Source Ledger: what a number needs, the evidence for it, and what to keep."""

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
