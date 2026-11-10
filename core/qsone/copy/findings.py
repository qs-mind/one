"""Findings: a conflict or risk in the tender, raised to the engineer one at a time (C4)."""

FINDING_NOT_FOUND = {
    "en": "This Finding is not in this tender.",
    "ar": "الملاحظة دي مش موجودة في العطاء ده.",
}
FINDING_NOT_RAISED = {
    "en": "This Finding is not waiting for your decision yet.",
    "ar": "الملاحظة دي لسه مش مستنية قرارك.",
}
FINDING_SETTLED = {
    "en": "This Finding was already settled another way.",
    "ar": "الملاحظة دي اتحسمت خلاص بطريقة تانية.",
}
FINDINGS_TOO_MANY = {
    "en": (
        "This tender already has 100 Findings that are not settled. Join related ones into one "
        "Finding with all their items."
    ),
    "ar": (
        "العطاء ده فيه 100 ملاحظة لسه ما اتحسمتش. اجمع الملاحظات المتشابهة في ملاحظة واحدة "
        "ببنودها كلها."
    ),
}
FINDING_ITEM_UNKNOWN = {
    "en": "This item is not in the project's records: {item_id}.",
    "ar": "البند ده مش موجود في سجلات المشروع: {item_id}.",
}
# The note of the one raised Finding: what it waits for.
FINDING_WAITING = {"en": "Waiting for your decision", "ar": "مستنية قرارك"}
# The engineer's decision, as the message of the work it starts when nothing runs.
FINDING_DECIDED = {
    "en": "My decision on «{title}»: {option}",
    "ar": "قراري في «{title}»: {option}",
}
TOOL_RECORD_FINDING = {"en": "Recording a Finding", "ar": "بيسجّل ملاحظة"}
TOOL_RAISE_FINDING = {"en": "Raising a Finding to you", "ar": "بيرفع لك ملاحظة"}
