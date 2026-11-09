"""The team and Briefs: stops, Desks, disagreements, the Brief Runner's steps and limits."""

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
