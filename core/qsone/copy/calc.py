"""The QS Calc Engine: the formula, units and currencies, inputs, saving, its tools, notes."""

# ---------------------------------------------------------------------------------------------
# QS Calc Engine (Plan 3). Keep these texts together, in this block.
# Texts with values use {name} placeholders filled by `fill`; literal braces are doubled.
# ---------------------------------------------------------------------------------------------

# The formula.
CALC_UNEXPECTED = {
    "en": (
        "At character {at}, «{found}» was not expected; ONE expected {expected}. "
        "Numbers have no thousands separators."
    ),
    "ar": (
        "عند الحرف {at}، «{found}» مش مكانه هنا؛ ONE كان مستني {expected}. "
        "الأرقام من غير فواصل آلاف."
    ),
}

CALC_TOO_LONG = {
    "en": "The formula is longer than 4,000 characters. Split it into steps saved one by one.",
    "ar": "المعادلة أطول من 4000 حرف. قسّمها لخطوات تتحفظ واحدة واحدة.",
}

CALC_TOO_DEEP = {
    "en": "The formula nests more than 50 brackets or calls deep.",
    "ar": "المعادلة فيها أقواس أو دوال جوه بعض أكتر من 50 مستوى.",
}

CALC_UNKNOWN_NAME = {
    "en": (
        "«{name}» is not an input. Inputs: {names}. Add it to `inputs`, "
        'e.g. `"{name}": {{"item": "03/02", "name": "rate"}}`.'
    ),
    "ar": (
        "«{name}» مش من المدخلات. المدخلات: {names}. ضيفه في `inputs`، "
        'زي `"{name}": {{"item": "03/02", "name": "rate"}}`.'
    ),
}

CALC_UNKNOWN_FUNCTION = {
    "en": (
        "«{name}» is not a function. "
        "Functions: sum, count, avg, min, max, round, abs, sqrt, to, if."
    ),
    "ar": "«{name}» مش دالة. الدوال: sum، count، avg، min، max، round، abs، sqrt، to، if.",
}

CALC_USAGE = {
    "en": "Use {fn} like this: {usage}.",
    "ar": "استخدم {fn} كده: {usage}.",
}

CALC_LIST_HERE = {
    "en": "«{name}» is a list; use it inside sum, count, avg, min or max.",
    "ar": "«{name}» قايمة؛ استخدمها جوه sum أو count أو avg أو min أو max.",
}

CALC_POWER = {
    "en": "A power must be a whole number from -12 to 12, e.g. `side^2`.",
    "ar": "الأس لازم يكون رقم صحيح من -12 لـ 12، زي `side^2`.",
}

CALC_SQRT = {
    "en": "sqrt needs a value of zero or more whose unit powers are even, e.g. `sqrt(a^2 + b^2)`.",
    "ar": "sqrt محتاجة قيمة صفر أو أكتر، وأسس وحدتها زوجية، زي `sqrt(a^2 + b^2)`.",
}

CALC_DIVIDE_BY_ZERO = {
    "en": "«{text}» divides by zero.",
    "ar": "«{text}» فيها قسمة على صفر.",
}

CALC_TOO_BIG = {
    "en": "A value in «{text}» is too large to compute exactly.",
    "ar": "في قيمة في «{text}» أكبر من إنها تتحسب بالظبط.",
}

# Units and currencies.
CALC_UNITS_DIFFER = {
    "en": (
        "«{left}» and «{right}» cannot be added, compared or converted: their units do not match."
    ),
    "ar": "«{left}» و«{right}» مينفعش يتجمعوا أو يتقارنوا أو يتحوّلوا لبعض: وحداتهم مش متطابقة.",
}

CALC_CURRENCIES_DIFFER = {
    "en": (
        "{left} and {right} are different currencies. Multiply by an exchange rate from the "
        "Source Ledger, a number with unit {left}/{right}."
    ),
    "ar": (
        "{left} و{right} عملتين مختلفتين. اضرب في سعر صرف من سجل المصادر، رقم وحدته {left}/{right}."
    ),
}

CALC_RESULT_UNIT = {
    "en": "The formula gives {got}, not {want}. Check the formula or `result.unit`.",
    "ar": "المعادلة بتطلّع {got} مش {want}. راجع المعادلة أو `result.unit`.",
}

CALC_UNIT_UNREADABLE = {
    "en": "The unit «{unit}» cannot be read. Write it like m3, kg/m3, EGP/m3 or m3/day.",
    "ar": "الوحدة «{unit}» مش مفهومة. اكتبها زي m3 أو kg/m3 أو EGP/m3 أو m3/day.",
}

CALC_UNIT_BUILT_IN = {
    "en": "«{symbol}» is a built-in unit; it cannot be defined again.",
    "ar": "«{symbol}» وحدة أساسية في ONE؛ مينفعش تتعرّف تاني.",
}

CALC_UNIT_CURRENCY = {
    "en": (
        "A unit cannot hold a currency. "
        "An exchange rate is a Source Ledger number with a unit like EGP/USD."
    ),
    "ar": "الوحدة مينفعش يبقى فيها عملة. سعر الصرف رقم في سجل المصادر بوحدة زي EGP/USD.",
}

CALC_UNIT_LOOP = {
    "en": "«{symbol}» would be defined through itself.",
    "ar": "«{symbol}» كده هتتعرّف بنفسها.",
}

CALC_UNIT_FACTOR = {
    "en": 'A unit must equal more than zero of another unit, e.g. `"equals": "50 kg"`.',
    "ar": 'الوحدة لازم تساوي أكتر من صفر من وحدة تانية، زي `"equals": "50 kg"`.',
}

CALC_UNIT_CASE = {
    "en": (
        "«{symbol}» is already defined as «{existing}»: units that differ only in upper and "
        "lower case are one unit. Send «{existing}» with a `reason` to correct it."
    ),
    "ar": (
        "«{symbol}» متعرّفة قبل كده باسم «{existing}»: الوحدات اللي فرقها في الحروف الكبيرة "
        "والصغيرة بس وحدة واحدة. ابعت «{existing}» مع `reason` عشان تصححها."
    ),
}

# Inputs.
CALC_CONSTANT_UNIT = {
    "en": (
        "A constant is a plain number or %. "
        "A number with a unit or a currency goes in the Source Ledger with its source and date."
    ),
    "ar": (
        "الثابت رقم مجرد أو نسبة %. الرقم اللي ليه وحدة أو عملة مكانه سجل المصادر، بمصدره وتاريخه."
    ),
}

CALC_ITEM_NOT_FOUND = {
    "en": "No item has the id or code «{ref}».",
    "ar": "مفيش بند الـ id أو الكود بتاعه «{ref}».",
}

CALC_ITEM_AMBIGUOUS = {
    "en": "«{ref}» matches {n} items: {choices}. Send the item id.",
    "ar": "«{ref}» بيطابق {n} بنود: {choices}. ابعت الـ id بتاع البند.",
}

CALC_NUMBER_NOT_FOUND = {
    "en": "No number has the id «{ref}».",
    "ar": "مفيش رقم الـ id بتاعه «{ref}».",
}

CALC_NUMBER_OLD = {
    "en": "Number «{ref}» was corrected; the current entry is «{now}».",
    "ar": "الرقم «{ref}» اتصحح؛ القيمة الحالية هي «{now}».",
}

CALC_NUMBER_MISSING = {
    "en": "Item {item} has no current «{name}».",
    "ar": "البند {item} مفيهوش «{name}» حالي.",
}

CALC_NUMBER_AMBIGUOUS = {
    "en": (
        "Item {item} has {n} current «{name}» numbers: {choices}. "
        'Send `{{"number": "<id>"}}` for the one to use.'
    ),
    "ar": (
        "البند {item} فيه {n} أرقام حالية باسم «{name}»: {choices}. "
        'ابعت `{{"number": "<id>"}}` للرقم اللي هتستخدمه.'
    ),
}

CALC_NO_MATCH = {
    "en": "No item matches {selector}.",
    "ar": "مفيش بند بيطابق {selector}.",
}

CALC_MISSING_IN_ITEMS = {
    "en": '{n} items have no «{name}»: {codes}. Add it first, or send `"skip_missing": true`.',
    "ar": '{n} بنود مفيهاش «{name}»: {codes}. ضيفه الأول، أو ابعت `"skip_missing": true`.',
}

# Saving.
CALC_NEEDS_LEDGER_INPUT = {
    "en": "A saved result needs at least one number from the Source Ledger.",
    "ar": "النتيجة اللي هتتحفظ محتاجة رقم واحد على الأقل من سجل المصادر.",
}

CALC_SAVE_NEEDS_REASON = {
    "en": (
        "Item {item} already has «{name}» = {value} {unit} (from {source}). "
        "Send `save.reason` to correct it."
    ),
    "ar": (
        "البند {item} فيه «{name}» = {value} {unit} بالفعل (من {source}). "
        "ابعت `save.reason` عشان تصححه."
    ),
}

CALC_SAVE_RATE = {
    "en": "A rate is a currency per unit, e.g. EGP/m3; this result is {unit}.",
    "ar": "الفئة عملة لكل وحدة، زي EGP/m3؛ النتيجة دي {unit}.",
}

CALC_SAVE_AMOUNT = {
    "en": "An amount is one currency, e.g. EGP; this result is {unit}.",
    "ar": "المبلغ عملة واحدة، زي EGP؛ النتيجة دي {unit}.",
}

CALC_SAVE_QUANTITY = {
    "en": "A quantity has no currency; this result is {unit}.",
    "ar": "الكمية مفيهاش عملة؛ النتيجة دي {unit}.",
}

CALC_SAVE_OWN_INPUT = {
    "en": "The result cannot correct one of its own inputs («{name}»).",
    "ar": "النتيجة مينفعش تصحح مدخل من مدخلاتها («{name}»).",
}

CALC_REQUEST_SHAPE = {
    "en": "The request is not complete at «{field}». Send it like this: {example}.",
    "ar": "الطلب ناقص عند «{field}». ابعته كده: {example}.",
}

# The tools for agents: what each one does, in the engineer's words.
CALC_TOOL_CALCULATE = {
    "en": "Calculates a number exactly and saves it with its formula and sources.",
    "ar": "بيحسب الرقم بالظبط ويحفظه بمعادلته ومصادره.",
}

CALC_TOOL_DEFINE_UNIT = {
    "en": "Defines a project unit, like a bag of 50 kg, with its source.",
    "ar": "بيعرّف وحدة للمشروع، زي شيكارة 50 كجم، بمصدرها.",
}

CALC_TOOL_EXPLAIN = {
    "en": "Shows where a number comes from: its formula, inputs, sources and dates.",
    "ar": "بيوضّح الرقم جاي منين: معادلته ومدخلاته ومصادره وتواريخها.",
}

CALC_TOOL_RECALCULATE = {
    "en": "Lists the numbers out of date after a correction, and recalculates them in order.",
    "ar": "بيعرض الأرقام اللي محتاجة إعادة حساب بعد تصحيح، ويحسبها تاني بالترتيب.",
}

# Notes: facts about a result, not refusals.
CALC_NOTE_INEXACT = {
    "en": "The result is not exact before rounding: a division or conversion does not end.",
    "ar": "النتيجة مش مظبوطة قبل التقريب: في قسمة أو تحويل مش بيخلص.",
}

CALC_NOTE_OWN_UNIT = {
    "en": "«{unit}» is not defined, so it is a unit of its own that converts to nothing.",
    "ar": "«{unit}» مش متعرّفة، فهي وحدة لوحدها ومش بتتحوّل لأي وحدة تانية.",
}

CALC_NOTE_SKIPPED = {
    "en": "{n} items were skipped for a missing «{name}»: {codes}.",
    "ar": "اتسابت {n} بنود عشان مفيهاش «{name}»: {codes}.",
}

# Recalculation reasons. The English text is stored in the ledger; the trace keeps the cause.
CALC_RECALCULATED = {
    "en": "Recalculated: «{name}» was corrected ({reason}).",
    "ar": "اتحسب تاني: «{name}» اتصحح ({reason}).",
}

CALC_RECALC_MEMBERS = {
    "en": "Recalculated: the matching items changed.",
    "ar": "اتحسب تاني: البنود المطابقة اتغيرت.",
}
