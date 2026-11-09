"""Prices: QS Mind Prices, the engineer's own, and the card that proposes them."""

# Prices.
PRICES_ASK = {
    "en": "Keep these prices? Tick the rows to keep.",
    "ar": "أحفظ الأسعار دي؟ علّم على الصفوف اللي تتحفظ.",
}
PRICES_NOT_SUBSCRIBED = {
    "en": (
        "QS Mind Prices come with a QS Mind subscription. "
        "Showing your own prices and this project's."
    ),
    "ar": "أسعار QS Mind بتيجي مع اشتراك QS Mind. بنعرض أسعارك وأسعار المشروع ده.",
}
PRICES_OFFLINE = {
    "en": "No internet: showing the QS Mind prices saved on {date}.",
    "ar": "مفيش نت: بنعرض أسعار QS Mind المحفوظة يوم {date}.",
}
PRICES_DOWN = {
    "en": "QS Mind Prices did not answer. Showing the prices saved on {date}.",
    "ar": "أسعار QS Mind مارَدّتش. بنعرض الأسعار المحفوظة يوم {date}.",
}
PRICES_NONE_FOUND = {
    "en": "No price was found for this item. Try other words, or search the market.",
    "ar": "مالقيناش سعر للبند ده. جرّب كلام تاني، أو دوّر في السوق.",
}
PRICES_COUNTRY = {
    "en": "Prices cover Egypt, Saudi Arabia and the UAE: send EG, SA or AE.",
    "ar": "الأسعار لمصر والسعودية والإمارات: ابعت EG أو SA أو AE.",
}
PRICES_ON_DEVICE = {
    "en": "This is an On-device Project, so ONE did not fetch QS Mind Prices: showing the "
    "prices saved on {date}.",
    "ar": "ده مشروع على الجهاز، فـ ONE ماجابش أسعار QS Mind: بنعرض الأسعار المحفوظة يوم {date}.",
}
PRICES_NONE_SAVED = {
    "en": "No QS Mind prices are saved on this computer yet, and ONE could not get them now. "
    "Showing your own prices and this project's.",
    "ar": "مفيش أسعار QS Mind محفوظة على الجهاز لسه، و ONE مقدرش يجيبها دلوقتي. "
    "بنعرض أسعارك وأسعار المشروع ده.",
}
PRICES_FOR_ALL = {
    "en": "{agent} proposes these prices. The ticked ones go into your Engineer Records, "
    "for every project, with this card as their source.",
    "ar": "{agent} بيقترح الأسعار دي. اللي تعلّم عليها هتتحفظ في سجلات المهندس، لكل مشاريعك، "
    "والبطاقة دي مصدرها.",
}
PRICES_FOR_PROJECT = {
    "en": "{agent} proposes these prices. The ticked ones are kept in this project, each with "
    "its source.",
    "ar": "{agent} بيقترح الأسعار دي. اللي تعلّم عليها هتتحفظ في المشروع ده، كل واحد بمصدره.",
}
PRICES_COLUMNS = {
    "description": {"en": "Item", "ar": "البند"},
    "unit": {"en": "Unit", "ar": "الوحدة"},
    "rate": {"en": "Rate", "ar": "السعر"},
    "currency": {"en": "Currency", "ar": "العملة"},
    "vat": {"en": "VAT", "ar": "الضريبة"},
    "dated": {"en": "Date", "ar": "التاريخ"},
    "supplier": {"en": "Supplier", "ar": "المورّد"},
}
# A price's VAT basis, as QS Mind Prices states it.
PRICES_VAT = {
    "incl": {"en": "VAT included", "ar": "شامل الضريبة"},
    "excl": {"en": "VAT not included", "ar": "من غير الضريبة"},
    "na": {"en": "No VAT", "ar": "مفيش ضريبة"},
    "unknown": {"en": "VAT not stated", "ar": "الضريبة مش مذكورة"},
}
TOOL_PRICES_PROPOSE = {
    "en": "Proposing prices for you to keep",
    "ar": "بيقترح أسعار عشان تحفظها",
}
