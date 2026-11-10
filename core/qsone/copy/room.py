"""The team room: one conversation per tender, where the team talks and the engineer writes (C6)."""

ROOM_EMPTY = {
    "en": "Write your message to the team first.",
    "ar": "اكتب رسالتك للفريق الأول.",
}
ROOM_TOO_LONG = {
    "en": "A message to the team takes at most 20,000 characters. Make it shorter.",
    "ar": "الرسالة للفريق تاخد 20000 حرف بالكتير. اختصرها شوية.",
}
ROOM_CURSOR_INVALID = {
    "en": "This page of the team room cannot be found. Open the room again.",
    "ar": "الصفحة دي من غرفة الفريق مش لاقيينها. افتح الغرفة تاني.",
}
# The question of the work a room message starts when nothing runs, in the engineer's language.
ROOM_BRIEF = {
    "en": "A message in the team room",
    "ar": "رسالة في غرفة الفريق",
}

# A member's money question, raised to the engineer as a card ---------------------------------

ROOM_MONEY_TITLE = {
    "en": "{agent} needs your decision on money",
    "ar": "{agent} محتاج قرارك في موضوع فيه فلوس",
}
ROOM_MONEY_DETAIL = {
    "en": "This decision spends or prices money, so the team asks you before it goes on.",
    "ar": "القرار ده فيه صرف أو تسعير، فالفريق بيسألك الأول قبل ما يكمّل.",
}

# A disagreement the members did not settle in two rounds ---------------------------------------

ROOM_DISAGREE_TITLE = {
    "en": "{first} and {second} do not agree",
    "ar": "{first} و{second} مش متفقين",
}
ROOM_DISAGREE_DETAIL = {
    "en": "They did not settle it in two rounds. Each view, with what it rests on:",
    "ar": "ما اتفقوش في جولتين. رأي كل واحد، وبيستند على إيه:",
}
ROOM_VIEW = {"en": "{agent}'s view", "ar": "رأي {agent}"}
ROOM_NO_SOURCE = {"en": "No source given.", "ar": "من غير مصدر."}
ROOM_DISAGREE_ASK = {
    "en": "Which view does the team follow?",
    "ar": "الفريق يمشي على أنهي رأي؟",
}
# The Lead's message to the engineer when it raises the disagreement, and to the team after.
ROOM_DISAGREE_RAISED = {
    "en": "{first} and {second} did not agree in two rounds, so I raised it to you.",
    "ar": "{first} و{second} ما اتفقوش في جولتين، فرفعت الموضوع ليك.",
}
ROOM_DISAGREE_SETTLED = {
    "en": "The engineer chose {view}. We go on with it.",
    "ar": "المهندس اختار {view}. هنكمّل عليه.",
}
