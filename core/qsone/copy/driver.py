"""The plan driver: the words of the work it starts for a stage, in the engineer's language."""

# The question of a stage's Brief. It is the Brief's own text, so a continued Brief is told its
# stage again. {outputs}: the outputs' titles joined by STAGE_JOIN.
STAGE_BRIEF = {
    "en": (
        "Stage {n} of {total}: {title}. Owner: {owner}. It makes: {outputs}. "
        "At its end you show the engineer what to sign off: {gate}."
    ),
    "ar": (
        "المرحلة {n} من {total}: {title}. المسؤول: {owner}. بتطلّع: {outputs}. "
        "وفي آخرها اعرض على المهندس اللي هيوقّع عليه: {gate}."
    ),
}
STAGE_BRIEF_SUPPLIES = {
    "en": (
        "ONE cannot do this stage alone. Ask the engineer for it, naming what to supply: "
        "{supplies}. Then go on with what they give."
    ),
    "ar": (
        "ONE مايقدرش يعمل المرحلة دي لوحده. اطلب من المهندس اللي هيجيبه وسمّيه: "
        "{supplies}. وبعدين كمّل باللي يدّيهولك."
    ),
}
STAGE_JOIN = {"en": "; ", "ar": "؛ "}
STAGE_NO_OUTPUTS = {"en": "a short report", "ar": "تقرير قصير"}

# A stage's `result` once its work ended: what it made and what is not made yet. {made} and
# {missing}: the outputs' titles joined by STAGE_JOIN.
STAGE_RESULT_DONE = {"en": "Made: {made}.", "ar": "اتعمل: {made}."}
STAGE_RESULT_MISSING = {"en": "Not made yet: {missing}.", "ar": "لسه ما اتعملش: {missing}."}
STAGE_RESULT_ENDED = {"en": "The stage's work ended.", "ar": "شغل المرحلة خلص."}
# The live work line of a stage's work (`data-progress`): the stage and the total in the words.
STAGE_PROGRESS = {"en": "Stage {n} of {total}: {text}", "ar": "المرحلة {n} من {total}: {text}"}
