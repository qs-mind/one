"""Connectors: adding one, its card, and what it says when it is off or does not answer."""

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
