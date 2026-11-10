"""Home, a tender's header and Lessons Learned (Phase 1, C7)."""

# Lessons Learned, as the engineer sees and edits them (GET/PATCH/DELETE /engineer/lessons).
ENGINEER_LESSON_NOT_FOUND = {
    "en": "This lesson is not in your Lessons Learned.",
    "ar": "الدرس ده مش موجود في الدروس المستفادة بتاعتك.",
}
LESSON_EMPTY = {
    "en": "Write the lesson in a few words, or remove it.",
    "ar": "اكتب الدرس في كلمتين، أو امسحه.",
}
LESSON_TOO_LONG = {
    "en": "A lesson takes at most 2,000 characters. Make it shorter.",
    "ar": "الدرس ياخد 2000 حرف بالكتير. اختصره شوية.",
}

# What waits for the engineer, by kind (`WaitingItem.title`). A decision and a card keep their
# own title.
WAITING_PLAN = {"en": "Approve the tender plan", "ar": "وافق على خطة المناقصة"}
WAITING_STAGE = {"en": "Sign off «{stage}»", "ar": "اعتمد «{stage}»"}
WAITING_PLAN_CHANGE = {
    "en": "A change to the tender plan",
    "ar": "تعديل مقترح على خطة المناقصة",
}
WAITING_UNFINISHED = {
    "en": "Work was cut off: continue it or leave it",
    "ar": "الشغل اتقطع: كمّله أو سيبه",
}
