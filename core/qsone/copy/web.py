"""The web: searching it and reading a page."""

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
