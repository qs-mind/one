"""The tender plan: its routes' refusals, the plan tools' checks and the fixed members' cards."""

# The routes (contract rows 8-12) -------------------------------------------------------------

PLAN_NOT_FOUND = {
    "en": "This tender has no plan yet.",
    "ar": "المناقصة دي لسه مالهاش خطة.",
}
PLAN_EXISTS = {
    "en": "This tender has a plan already. Discuss it with the Lead QS to change it.",
    "ar": "المناقصة دي ليها خطة بالفعل. اتكلم مع كبير مهندسي الكميات لو عايز تغيّرها.",
}
PLAN_CHANGED = {
    "en": "The plan changed since you saw it. Look at the new version, then approve it.",
    "ar": "الخطة اتغيّرت من ساعة ما شفتها. بص على النسخة الجديدة وبعدين وافق عليها.",
}
PLAN_NEEDS_SUBMISSION_DATE = {
    "en": (
        "The plan needs the tender's submission date, and the date must not have passed. "
        "Give the date first."
    ),
    "ar": "الخطة محتاجة ميعاد تقديم المناقصة، ولازم الميعاد مايكونش عدّى. حدّد الميعاد الأول.",
}
PLAN_APPROVED = {
    "en": "The plan is approved, so it changes only by a Suggested change you accept.",
    "ar": "الخطة اتوافق عليها، فمش هتتغيّر غير بتعديل مقترح توافق عليه.",
}
PLAN_NOT_APPROVED = {
    "en": "The plan is not approved yet, so it is proposed again instead of changed.",
    "ar": "الخطة لسه ما اتوافقش عليها، فبتتقترح من جديد بدل ما تتعدّل.",
}
STAGE_NOT_FOUND = {
    "en": "This stage is not in the plan.",
    "ar": "المرحلة دي مش في الخطة.",
}
STAGE_NOT_WAITING = {
    "en": "This stage's work has not ended yet, so there is nothing to sign off.",
    "ar": "شغل المرحلة دي لسه ماخلصش، فمفيش حاجة توقّع عليها.",
}
STAGE_OUTPUT_NOT_READY = {
    "en": "«{output}» is not ready to sign off: {reason}",
    "ar": "«{output}» لسه مش جاهز للتوقيع: {reason}",
}  # {reason}: STAGE_OUTPUT_MISSING, or the Deliverable's own close-out reason
STAGE_OUTPUT_MISSING = {
    "en": "it has not been made yet.",
    "ar": "لسه ما اتعملش.",
}
WORK_RUNNING = {
    "en": "Work is running here. Wait for it to end, or stop it.",
    "ar": "في شغل شغال هنا. استنى لما يخلص، أو وقّفه.",
}
# The question of the Brief that `POST .../plan/request` starts, in the engineer's language.
PLAN_REQUEST_BRIEF = {
    "en": "Write the tender plan.",
    "ar": "اكتب خطة المناقصة.",
}

# The Lead is told how the engineer answered its Suggested change (route 12), in one line: a
# steer to its running work (shown in the thread as the engineer's), else in the next work's
# instruction.
PLAN_CHANGE_ACCEPTED_TOLD = {
    "en": "I accepted your suggested change to the plan. Work goes on under the plan as changed "
    "(version {version}).",
    "ar": "وافقت على التعديل اللي اقترحته على الخطة. الشغل يكمّل على الخطة بعد التعديل "
    "(الإصدار {version}).",
}
PLAN_CHANGE_REJECTED_TOLD = {
    "en": "I rejected your suggested change to the plan. Work goes on under the approved plan as "
    "it was.",
    "ar": "رفضت التعديل اللي اقترحته على الخطة. الشغل يكمّل على الخطة المعتمدة زي ما هي.",
}

# The plan tools' checks: each names the value that does not fit -------------------------------

PLAN_TEXT_PAIR = {
    "en": "{field} needs both its English and its Arabic.",
    "ar": "{field} محتاج الإنجليزي والعربي الاتنين.",
}
PLAN_STAGE_DATES = {
    "en": "Stage {n} ends before it starts.",
    "ar": "المرحلة {n} بتخلص قبل ما تبدأ.",
}
PLAN_STAGE_ORDER = {
    "en": "Stage {n} starts before the stage before it ends.",
    "ar": "المرحلة {n} بتبدأ قبل ما المرحلة اللي قبلها تخلص.",
}
PLAN_DATE_OUTSIDE = {
    "en": "Stage {n} is dated outside {today} to {date}, today to the submission date.",
    "ar": "المرحلة {n} متاريخها برّه الفترة من {today} لـ {date}، من النهارده لميعاد التقديم.",
}
PLAN_DATE_NOT_FACT = {
    "en": "The tender's submission date is {date}: date the plan back from it.",
    "ar": "ميعاد تقديم المناقصة {date}: رتّب تواريخ الخطة بالرجوع منه.",
}
PLAN_OWNER_UNKNOWN = {
    "en": "Stage {n}'s owner «{owner}» is not on the team.",
    "ar": "مسؤول المرحلة {n} «{owner}» مش من الفريق.",
}
PLAN_STAGE_UNKNOWN = {
    "en": "Stage {n} names a stage id that is not in the plan: «{id}».",
    "ar": "المرحلة {n} بتشاور على رقم مرحلة مش في الخطة: «{id}».",
}
PLAN_STAGE_TWICE = {
    "en": "Stage {n} repeats a stage that is already in the plan: «{id}».",
    "ar": "المرحلة {n} بتكرّر مرحلة موجودة في الخطة: «{id}».",
}
PLAN_STAGE_LOCKED = {
    "en": "«{stage}» is signed off, so a change cannot remove or alter it.",
    "ar": "«{stage}» اتوقّع عليها، فالتعديل مايقدرش يشيلها أو يغيّرها.",
}
PLAN_MEMBER_REF = {
    "en": "Team member {n} has a ref that is taken or not allowed: «{ref}».",
    "ar": "عضو الفريق {n} ليه اسم مختصر مستخدم أو مش مسموح: «{ref}».",
}
PLAN_MEMBER_PERMANENT = {
    "en": "Team member {n}, «{name}», is a permanent member: bring it in with member_id "
    "«{member_id}» and its ref, without a card.",
    "ar": "عضو الفريق {n}، «{name}»، عضو دائم في فريقك: هاته بـ member_id «{member_id}» "
    "واسمه المختصر، من غير بطاقة.",
}
PLAN_MEMBER_TOOL = {
    "en": "Team member {n} cannot be given the tool «{tool}».",
    "ar": "عضو الفريق {n} مينفعش ياخد الأداة «{tool}».",
}

# The two fixed members as a plan's team shows them, until the members' own cards replace these.
PLAN_LEAD_SPECIALITY = {
    "en": "Tender planning and coordination",
    "ar": "تخطيط المناقصة وتنسيق الشغل",
}
PLAN_LEAD_STYLE = {
    "en": "Plans from the documents, asks only what the files cannot answer",
    "ar": "بيخطّط من المستندات، وبيسأل بس عن اللي الملفات مافيهوش",
}
PLAN_CHECKER_SPECIALITY = {
    "en": "Independent checking of every Deliverable",
    "ar": "مراجعة مستقلة لكل مُخرَج",
}
PLAN_CHECKER_STYLE = {
    "en": "Checks blind against the sources, gives a code and its reasons",
    "ar": "بيراجع من غير ما يعرف مين عمل الشغل، على المصادر، وبيدّي كود وأسبابه",
}
