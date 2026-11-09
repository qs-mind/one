"""BOQ import: its refusals, why a row was left out, and the card that shows the columns."""

# BOQ import.
BOQ_NO_SHEET = {
    "en": "This file has no sheet by that name. The sheets are: {sheets}.",
    "ar": "الملف ده مفيهوش شيت بالاسم ده. الشيتات: {sheets}.",
}
BOQ_BAD_COLUMNS = {
    "en": 'Map at least the description, unit and quantity columns, by letter (e.g. "C").',
    "ar": 'حدّد على الأقل أعمدة الوصف والوحدة والكمية، بالحرف (زي "C").',
}
BOQ_ROW_SKIPPED = {
    "en": "Row {row} was not imported: {why}",
    "ar": "الصف {row} مااتستوردش: {why}",
}
# Task 9: the import's own words. Why a row was left out ({field} is a BOQ_FIELDS pair).
BOQ_WHY_TEXT = {
    "en": "the {field} in column {column} is text, not a number",
    "ar": "{field} في العمود {column} نص، مش رقم",
}
BOQ_WHY_NUMBER_FORMAT = {
    "en": (
        "the {field} in column {column} has an ambiguous decimal/thousands separator; "
        "the file does not establish one convention"
    ),
    "ar": (
        "الفاصل في {field} بالعمود {column} مش واضح: عشري ولا آلاف، وباقي الملف مش موضّح طريقة واحدة"
    ),
}
BOQ_WHY_DECIMALS = {
    "en": "the {field} in column {column} has more than 6 decimals; check the cell in Excel",
    "ar": "{field} في العمود {column} فيه أكتر من 6 أرقام عشرية؛ راجع الخانة في Excel",
}
BOQ_WHY_NO_UNIT = {"en": "a quantity with no unit", "ar": "كمية من غير وحدة"}
BOQ_WHY_NO_DESCRIPTION = {"en": "numbers with no description", "ar": "أرقام من غير وصف"}
BOQ_QUANTITY_FALLBACK = {
    "en": "Quantity taken from column {column} for rows {rows}.",
    "ar": "الكمية اتاخدت من العمود {column} للصفوف {rows}.",
}
BOQ_QUANTITY_MISSING = {
    "en": (
        "No quantity in the file for rows {rows} "
        "(the mapped and quantity-heading columns are empty)."
    ),
    "ar": "مفيش كمية في الملف للصفوف {rows} (العمود المختار وأعمدة الكمية فاضيين).",
}
BOQ_PRICE_ITEM_REQUIRED = {
    "en": (
        "The engineer did not name item {item} or request pricing. "
        "Name the intended BOQ item, request pricing, "
        "or keep a standalone price."
    ),
    "ar": (
        "المهندس محددش البند {item} ولا طلب تسعير. "
        "حدّد بند المقايسة المقصود، أو اطلب تسعير، "
        "أو سجّل السعر لوحده."
    ),
}

BOQ_WHY_TOTAL = {"en": "a total row", "ar": "صف إجمالي"}
BOQ_WHY_NUMBER_ONLY = {
    "en": "a rate or amount with no quantity and no unit",
    "ar": "فئة أو إجمالي من غير كمية ولا وحدة",
}
BOQ_WHY_HIDDEN = {"en": "the row is hidden in Excel", "ar": "الصف مخفي في Excel"}
BOQ_WHY_HEADER = {"en": "the column headings again", "ar": "عناوين الأعمدة تاني"}
BOQ_FIELDS = {
    "code": {"en": "Item no.", "ar": "رقم البند"},
    "description": {"en": "Description", "ar": "الوصف"},
    "description_2": {"en": "Description, other language", "ar": "الوصف باللغة التانية"},
    "unit": {"en": "Unit", "ar": "الوحدة"},
    "quantity": {"en": "Quantity", "ar": "الكمية"},
    "rate": {"en": "Rate", "ar": "الفئة"},
    "amount": {"en": "Amount", "ar": "الإجمالي"},
}
BOQ_NOT_USED = {"en": "Not used", "ar": "مش مستخدم"}
BOQ_FILE = {"en": "the BOQ file", "ar": "ملف المقايسة"}
DOING_BOQ_PREVIEW = {
    "en": "Look at the BOQ columns in {name}",
    "ar": "يبص على أعمدة المقايسة في {name}",
}
BOQ_NOT_EXCEL = {
    "en": "This file is not an Excel workbook or PDF BOQ; files_read reads it.",
    "ar": "الملف ده مش ملف Excel أو مقايسة PDF؛ files_read بيقراه.",
}
BOQ_PDF_NO_TABLES = {
    "en": "No tables were found in this PDF; files_read reads its text.",
    "ar": "مالقيناش جداول في ملف PDF ده؛ files_read بيقرا النص اللي فيه.",
}
BOQ_NO_ROWS = {
    "en": "No BOQ rows were found below the header row with these columns. Check the header row "
    "and the columns with boq_preview.",
    "ar": "مالقيناش صفوف مقايسة تحت صف العناوين بالأعمدة دي. راجع صف العناوين والأعمدة بـ "
    "boq_preview.",
}
BOQ_ASK_CURRENCY = {
    "en": "The BOQ's rates and amounts don't say their currency. Which currency are they in?",
    "ar": "الفئات والإجماليات في المقايسة مش مكتوب عملتها. هي بأنهي عملة؟",
}
BOQ_NEEDS_CURRENCY = {
    "en": "Rates and amounts need their currency: three letters, e.g. EGP, SAR, AED.",
    "ar": "الفئات والإجماليات محتاجة عملتها: تلات حروف، زي EGP أو SAR أو AED.",
}
# The card that shows the column mapping before anything is written.
BOQ_CONFIRM_TITLE = {
    "en": "Import the BOQ from {name}, sheet {sheet}?",
    "ar": "أستورد المقايسة من {name}، شيت {sheet}؟",
}
# {items}, {headings} and {count}: counted phrases (counted: ITEMS, HEADINGS, ROWS)
BOQ_CONFIRM_DETAIL = {
    "en": "Rows {first} to {last}: {items} and {headings}.",
    "ar": "الصفوف من {first} لـ {last}: {items} و{headings}.",
}
BOQ_CONFIRM_SKIPPED = {"en": "Left out: {count}.", "ar": "واتساب {count}."}
BOQ_CONFIRM_TICK = {
    "en": "Check what each column holds and change any that is wrong. A column set to «Not used» "
    "is left out.",
    "ar": "راجع كل عمود فيه إيه، وغيّر اللي غلط. العمود اللي «مش مستخدم» مش هيتستورد.",
}
BOQ_CONFIRM_HIDDEN = {
    "en": "Hidden in Excel and left out: {count}.",
    "ar": "مخفي في Excel ومتساب: {count}.",
}
BOQ_CONFIRM_HIDDEN_IN = {
    "en": "Hidden in Excel and included: {count}.",
    "ar": "مخفي في Excel وداخل في الاستيراد: {count}.",
}
BOQ_CONFIRM_FLAGGED = {
    "en": "With hidden text (white, tiny or invisible) or what looks like orders to an AI: "
    "{count}. Imported as data only.",
    "ar": "فيه نص مخفي (أبيض أو صغير جداً أو مش ظاهر) أو كلام شكله أوامر لذكاء اصطناعي: "
    "{count}. بيتستورد كبيانات بس.",
}
BOQ_CARD_COLUMNS = {
    "meaning": {"en": "What it holds", "ar": "فيه إيه"},
    "column": {"en": "Column", "ar": "العمود"},
    "header": {"en": "Its heading in the file", "ar": "عنوانه في الملف"},
    "example": {"en": "First values", "ar": "أول القيم"},
}
BOQ_NOT_CONFIRMED = {
    "en": "The engineer did not confirm the columns, so nothing was imported.",
    "ar": "المهندس ماأكدش الأعمدة، فمااتستوردش حاجة.",
}
BOQ_REQUIRED_UNTICKED = {
    "en": "The engineer did not set the {fields} column, so nothing was imported.",
    "ar": "المهندس ماحددش عمود {fields}، فمااتستوردش حاجة.",
}
BOQ_MEANING_TWICE = {
    "en": "The engineer set {fields} on more than one column, so nothing was imported.",
    "ar": "المهندس حدد {fields} لأكتر من عمود، فمااتستوردش حاجة.",
}

BOQ_SCAN_NEEDS_READING = {
    "en": (
        "These scanned BOQ pages need reading first. Ask ONE to read them, or call files_read "
        "with ocr=true, then preview the BOQ again."
    ),
    "ar": (
        "صفحات المقايسة المتصورة دي محتاجة تتقري الأول. اطلب من ONE يقراها، أو استخدم "
        "files_read مع ocr=true، وبعدها اعرض المقايسة تاني."
    ),
}
