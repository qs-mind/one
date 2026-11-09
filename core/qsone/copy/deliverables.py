"""Deliverables and review: operations, changes, comments, Sign-off, exports, tender packs."""

# ---------------------------------------------------------------------------------------------
# Deliverables and review (Plan 6). Keep these texts together, in this block.
# Texts with values use {name} placeholders filled by `fill`.
# ---------------------------------------------------------------------------------------------

# The Deliverable and its Template Data Sheet.
DELIVERABLE_NOT_FOUND = {
    "en": "This Deliverable is not in the project. Open the Project Index to find it.",
    "ar": "المُخرَج ده مش موجود في المشروع. افتح فهرس المشروع ودوّر عليه.",
}

DELIVERABLE_CALC_REASON = {
    "en": "calculated in «{title}»",
    "ar": "اتحسب في «{title}»",
}

RECORDS_MOVED = {
    "en": "Update from Project Records",
    "ar": "تحديث من سجلات المشروع",
}

TEMPLATE_UNKNOWN = {
    "en": "There is no such template. A Deliverable is a Sheet or a Document.",
    "ar": "مفيش قالب بالاسم ده. المُخرَج يا إما جدول (Sheet) يا إما مستند (Document).",
}

COLUMN_NOT_ALLOWED = {
    "en": (
        "This column is not allowed. A column is text (code, field:<key>, number:<name>.unit), "
        "number (number:<name>) or calc (a formula of this row's numbers)."
    ),
    "ar": (
        "العمود ده مش مسموح. العمود يا إما text (code أو field:<key> أو number:<name>.unit)، "
        "يا إما number (number:<name>)، يا إما calc (معادلة من أرقام نفس الصف)."
    ),
}

NODE_NOT_ALLOWED = {
    "en": (
        "This part of the document is not allowed. Use p, h1-h3, ul, ol, li, table, tr, td or "
        "blockquote, with num and cell for numbers, and bold or italic."
    ),
    "ar": (
        "الجزء ده من المستند مش مسموح. استخدم p أو h1-h3 أو ul أو ol أو li أو table أو tr أو td "
        "أو blockquote، ومعاهم num وcell للأرقام، وbold أو italic."
    ),
}

# Operations.
OP_UNKNOWN = {
    "en": (
        "This operation is not known. A Sheet takes set_number, set_field, add_item_row, "
        "add_section, set_section_title, remove_row, move_row and set_columns; a Document takes "
        "set_block, insert_block, remove_block and move_block."
    ),
    "ar": (
        "العملية دي مش معروفة. الجدول بياخد set_number وset_field وadd_item_row وadd_section "
        "وset_section_title وremove_row وmove_row وset_columns؛ والمستند بياخد set_block "
        "وinsert_block وremove_block وmove_block."
    ),
}

OP_NOT_IN_TEMPLATE = {
    "en": "This Deliverable's template does not allow this operation.",
    "ar": "قالب المُخرَج ده مش بيسمح بالعملية دي.",
}

OP_NUMBER_NEEDS_NAME = {
    "en": 'A number needs its name, the column it goes in: "name": "rate" or "quantity".',
    "ar": 'الرقم محتاج اسمه، يعني العمود اللي هيتحط فيه: "name": "rate" أو "quantity".',
}

ROW_NOT_FOUND = {
    "en": "This row is not in the Deliverable, or it was removed. Read the Deliverable again.",
    "ar": "الصف ده مش موجود في المُخرَج، أو اتشال. اقرا المُخرَج تاني.",
}

NUMBER_WAS_CALCULATED = {
    "en": "This rate came from «{formula}»; typing it replaces the calculation.",
    "ar": "الفئة دي جاية من «{formula}»؛ لو كتبتها بإيدك هتحل محل الحساب.",
}

AMOUNT_IS_COMPUTED = {
    "en": (
        "Amounts are computed by the QS Calc Engine from quantity × rate; "
        "change the quantity or the rate."
    ),
    "ar": "الإجمالي بيحسبه محرك الحسابات من الكمية × الفئة؛ غيّر الكمية أو الفئة.",
}

# Suggested changes.
UNDO_ACCEPT_REASON = {
    "en": "Undo of an accepted change in «{title}»",
    "ar": "تراجع عن تعديل اتقبل في «{title}»",
}

UNDO_TOO_LATE = {
    "en": "Too late to undo: this Deliverable changed since. Its Saved versions show what moved.",
    "ar": "مينفعش تتراجع: المُخرَج ده اتغيّر من ساعتها. النسخ المحفوظة بتوضّح إيه اللي اتغيّر.",
}

UNDO_RECORDS = {
    "en": (
        "An Update from Project Records cannot be undone here: correct the number in "
        "Project Records."
    ),
    "ar": "تحديث من سجلات المشروع مايتلغيش من هنا: صحّح الرقم في سجلات المشروع.",
}

CHANGE_STALE = {
    "en": "This cell changed after the change was suggested. Ask ONE again, or edit it yourself.",
    "ar": "الخلية دي اتغيرت بعد ما التعديل اتقترح. اطلب من ONE تاني، أو عدّلها بنفسك.",
}

CHANGE_NOT_PENDING = {
    "en": "This change was already accepted or rejected.",
    "ar": "التعديل ده اتقبل أو اترفض قبل كده.",
}

# Comments.
COMMENT_NOT_FOUND = {
    "en": "This comment is not in the Deliverable.",
    "ar": "الملاحظة دي مش موجودة في المُخرَج.",
}

COMMENT_NEEDS_TEXT = {
    "en": "Write the comment first.",
    "ar": "اكتب الملاحظة الأول.",
}

ANCHOR_NOT_FOUND = {
    "en": "The place this comment points to is not in the Deliverable. Pick a cell or text.",
    "ar": "المكان اللي الملاحظة بتشاور عليه مش موجود في المُخرَج. اختار خلية أو نص.",
}

COMMENT_KIND_NOT_ALLOWED = {
    "en": (
        "ONE's team writes notes, with no code. Review comments come from you or the "
        "Checking QS, with Code B or C."
    ),
    "ar": (
        "فريق ONE بيكتب ملاحظات بس، من غير كود. ملاحظات المراجعة بتيجي منك أو من مهندس "
        "المراجعة، بكود B أو C."
    ),
}

# "Fix it": the message the screen sends to the Lead QS for one Review comment.
FIX_REQUEST = {
    "en": (
        "Fix Review comment {comment} on «{title}» (Deliverable {deliverable}, {at}), "
        "at {place}: «{body}». Propose the fix with deliverable_propose and comment_id {comment}."
    ),
    "ar": (
        "صلّح ملاحظة المراجعة {comment} في «{title}» (المُخرَج {deliverable}، {at})، "
        "عند {place}: «{body}». اقترح التصليح بـ deliverable_propose ومعاه comment_id {comment}."
    ),
}

FIX_AT_REVISION = {"en": "Rev {no}, version {n}", "ar": "Rev {no}، النسخة {n}"}

FIX_AT_VERSION = {"en": "version {n}", "ar": "النسخة {n}"}

FIX_PLACE_CELL = {
    "en": "item «{row}», column «{column}» (row {id})",
    "ar": "البند «{row}»، عمود «{column}» (الصف {id})",
}

FIX_PLACE_RANGE = {
    "en": "from item «{start}» to item «{end}», columns «{first}» to «{last}» (rows {ids})",
    "ar": "من البند «{start}» للبند «{end}»، الأعمدة من «{first}» لـ «{last}» (الصفوف {ids})",
}

FIX_PLACE_ROW = {
    "en": "«{row}» (row {id})",
    "ar": "«{row}» (الصف {id})",
}

FIX_PLACE_TEXT = {
    "en": "the words «{quote}» (block {id})",
    "ar": "الكلام «{quote}» (الفقرة {id})",
}

FIX_PLACE_DELIVERABLE = {
    "en": "the whole Deliverable",
    "ar": "المُخرَج كله",
}

# Close-out and Sign-off.
SIGNOFF_PENDING_CHANGES = {
    "en": "Accept or reject every Suggested change first.",
    "ar": "اقبل أو ارفض كل التعديلات المقترحة الأول.",
}

SIGNOFF_OPEN_CODE_C = {
    "en": "A Code C comment is still open. Fix it and close it first.",
    "ar": "في ملاحظة كود C لسه مفتوحة. صلّحها واقفلها الأول.",
}

SIGNOFF_NEEDS_CHECK = {
    "en": "The Checking QS has not checked this version yet. Ask for a check first.",
    "ar": "مهندس المراجعة لسه ماراجعش النسخة دي. اطلب مراجعة الأول.",
}

SIGNOFF_CODE_C = {
    "en": "The Checking QS gave this version Code C: revise and resubmit.",
    "ar": "مهندس المراجعة إدّى النسخة دي كود C: يتعدّل ويتقدّم تاني.",
}

ALREADY_SIGNED_OFF = {
    "en": "This version is already signed off.",
    "ar": "النسخة دي اتعتمدت قبل كده.",
}

# Exports.
EXPORT_DRAFT_MARK = {
    "en": "Draft — not signed off",
    "ar": "مسودة — غير معتمد",
}

SAMPLE_DATA = {
    "en": "Sample data",
    "ar": "بيانات تجريبية",
}

SOURCES_SHEET = {
    "en": "Sources",
    "ar": "المصادر",
}

ENTERED_BY_ENGINEER = {
    "en": "Entered by the engineer",
    "ar": "أدخله المهندس",
}

MANUAL_EDIT_REASON = {
    "en": "Edited by hand in «{title}»",
    "ar": "تعديل يدوي في «{title}»",
}

EXPORT_FORMAT_NOT_ALLOWED = {
    "en": "A Sheet exports to Excel or PDF, a Document to Word or PDF.",
    "ar": "الجدول بيتصدّر Excel أو PDF، والمستند Word أو PDF.",
}

# The exports' own labels (Excel, Word, PDF), formal like the documents they sit in, each an
# {en, ar} pair; qsone.export.say fills them in the Deliverable's language.
EXPORT_LABELS = {
    "total": {"en": "Grand total", "ar": "الإجمالي العام"},
    "sources": {"en": "Sources", "ar": "المصادر"},
    "deliverable": {"en": "Deliverable", "ar": "مُخرَج"},
    "draft": {"en": "Draft", "ar": "مسودة"},
    "rev": {"en": "Rev {n}", "ar": "إصدار {n}"},
    "page_of": {"en": "Page {x} of {y}", "ar": "صفحة {x} من {y}"},
    "needs_signoff": {
        "en": "This Deliverable is exported only after Sign-off. Sign it off first.",
        "ar": "المُخرَج ده بيتصدّر بعد الاعتماد بس. اعتمده الأول.",
    },
    # The sources list: one line per number shown.
    "src_where": {"en": "Item", "ar": "البند"},
    "src_column": {"en": "Column", "ar": "العمود"},
    "src_value": {"en": "Value", "ar": "القيمة"},
    "src_unit": {"en": "Unit or currency", "ar": "الوحدة أو العملة"},
    "src_title": {"en": "Source", "ar": "المصدر"},
    "src_file": {"en": "File", "ar": "الملف"},
    "src_place": {"en": "Place", "ar": "الموضع"},
    "src_link": {"en": "Link", "ar": "الرابط"},
    "src_dated": {"en": "Dated", "ar": "التاريخ"},
    "src_kind": {"en": "Kind", "ar": "النوع"},
    "page": {"en": "page", "ar": "صفحة"},
    "sheet": {"en": "sheet", "ar": "ورقة"},
    "row": {"en": "row", "ar": "صف"},
    "cell": {"en": "cell", "ar": "خلية"},
    "column": {"en": "column", "ar": "عمود"},
    "line": {"en": "line", "ar": "سطر"},
    "layer": {"en": "layer", "ar": "طبقة"},
    # A calculation's formula in words: «الكمية × الفئة», «مجموع الإجمالي».
    "fn_sum": {"en": "Sum of", "ar": "مجموع"},
    "fn_count": {"en": "Count of", "ar": "عدد"},
    "fn_avg": {"en": "Average of", "ar": "متوسط"},
    "fn_min": {"en": "Least of", "ar": "أقل"},
    "fn_max": {"en": "Greatest of", "ar": "أكبر"},
    # A file source's kind as the sources list names it; any other kind reads "Document".
    "kind_boq": {"en": "BOQ", "ar": "مقايسة"},
    "kind_quote": {"en": "Quotation", "ar": "عرض سعر"},
    "kind_specification": {"en": "Specification", "ar": "مواصفات"},
    "kind_contract": {"en": "Contract", "ar": "عقد"},
    "kind_drawing": {"en": "Drawing", "ar": "رسومات"},
    "kind_web": {"en": "Web page", "ar": "صفحة ويب"},
    "kind_prices": {"en": "QS Mind market prices", "ar": "أسعار السوق من كيو إس مايند"},
    "kind_connector": {"en": "Connector", "ar": "موصّل"},
    "kind_chat": {"en": "The chat", "ar": "الشات"},
    "kind_document": {"en": "Document", "ar": "مستند"},
    # The PDF's header block.
    "head_project": {"en": "Project", "ar": "المشروع"},
    "head_client": {"en": "Client", "ar": "العميل"},
    "head_submission": {"en": "Submission", "ar": "ميعاد التقديم"},
    "head_date": {"en": "Date", "ar": "التاريخ"},
    "prepared": {"en": "Prepared with ONE", "ar": "تم الإعداد باستخدام ONE"},
    "calc_engine": {"en": "QS Calc Engine", "ar": "محرك الحسابات"},
    "engineer": {"en": "The engineer", "ar": "المهندس"},
    # The Review report.
    "report": {"en": "Review report", "ar": "تقرير المراجعة"},
    "issued": {"en": "Issued {at} by {by}", "ar": "صدر {at} بواسطة {by}"},
    "signed_by": {"en": "Signed off {at} by {by}", "ar": "اعتمده {by} في {at}"},
    "checks": {"en": "Checks", "ar": "المراجعات"},
    "code": {"en": "Code {code}", "ar": "كود {code}"},
    "version": {"en": "Version {n}", "ar": "نسخة {n}"},
    "checker": {"en": "Checker", "ar": "المراجع"},
    "same_provider": {"en": "Same-provider check", "ar": "مراجعة من نفس الشركة"},
    "other_provider": {"en": "Another provider", "ar": "شركة أخرى"},
    "changes": {
        "en": "Changes: {accepted} accepted, {rejected} rejected",
        "ar": "التعديلات: {accepted} مقبول، {rejected} مرفوض",
    },
    "comments": {"en": "Comments", "ar": "الملاحظات"},
    "note": {"en": "ONE's note", "ar": "ملاحظة ONE"},
    "review": {"en": "Review comment", "ar": "ملاحظة مراجعة"},
    "open": {"en": "Open", "ar": "مفتوحة"},
    "closed": {"en": "Closed", "ar": "مقفولة"},
    "none": {"en": "None", "ar": "مفيش"},
}

# The client's own file.
FILL_XLS_NOT_SUPPORTED = {
    "en": "Open the file in Excel, save it as .xlsx, then drop it again.",
    "ar": "افتح الملف في Excel واحفظه بصيغة .xlsx، وبعدين ارميه تاني.",
}

FILL_NEEDS_SIGNOFF = {
    "en": "The client's file is filled only from a signed-off Revision. Sign off first.",
    "ar": "ملف العميل بيتملي من إصدار معتمد بس. اعتمد الأول.",
}

FILL_SHEET_NOT_FOUND = {
    "en": "The client's file has no sheet named «{sheet}».",
    "ar": "ملف العميل مفيهوش ورقة اسمها «{sheet}».",
}

FILL_ROW_MISSING = {
    "en": "Row {row} is not in the client's sheet, so nothing was written. Check the Fill Plan.",
    "ar": "الصف {row} مش موجود في ورقة العميل، فمكتبناش حاجة. راجع خطة التعبئة.",
}

FILL_ROW_TWICE = {
    "en": "Row {row} appears twice in the Fill Plan.",
    "ar": "الصف {row} متكرر مرتين في خطة التعبئة.",
}

FILL_CODE_MISMATCH = {
    "en": "Row {row}: the client's code is «{theirs}», our item is «{ours}».",
    "ar": "الصف {row}: كود العميل «{theirs}»، والبند عندنا «{ours}».",
}

FILL_FORMULA_SKIPPED = {
    "en": "{cell} holds the client's formula, so it was left as it is.",
    "ar": "{cell} فيها معادلة العميل، فسيبناها زي ما هي.",
}

FILL_COLUMN_LETTER = {
    "en": "A column of the client's sheet is a letter from A to XFD, as Excel shows it.",
    "ar": "عمود ورقة العميل حرف من A لحد XFD، زي ما Excel بيعرضه.",
}

FILL_PLAN_NOT_FOUND = {
    "en": "This Fill Plan is not in the project. Ask ONE to map the client's file again.",
    "ar": "خطة التعبئة دي مش موجودة في المشروع. اطلب من ONE يربط ملف العميل تاني.",
}

# Accepting while Project Records moved.
UPDATE_FIRST = {
    "en": (
        "First review «Update from Project Records»: "
        "the Project Records changed since this version."
    ),
    "ar": "راجع «تحديث من سجلات المشروع» الأول: سجلات المشروع اتغيرت من ساعة الإصدار ده.",
}

# PDF page-region comments (Wave 1 E).
FILE_REGION_PLACE = {
    "en": "file {file}, page {page}, box {box}",
    "ar": "الملف {file}، صفحة {page}، المنطقة {box}",
}
FILE_REGION_FIX = {
    "en": "Review the comment on file {file}, page {page}, box {box}: {body}",
    "ar": "راجع التعليق على الملف {file}، صفحة {page}، المنطقة {box}: {body}",
}

# Tender packs (wave 1 A).
PACK_INVALID = {
    "en": "This pack step is invalid. Choose pages that exist and paired text.",
    "ar": "الخطوة دي مش صالحة. اختار صفحات موجودة ونص بالعربي والإنجليزي.",
}
PACK_PAGE = {"en": "Page {n} of {total}", "ar": "صفحة {n} من {total}"}
PACK_SEAL = {
    "en": (
        "The free seal proves the file was not changed after sealing. "
        "It is not a licensed e-signature."
    ),
    "ar": "الختم المجاني بيثبت إن الملف ماتغيرش بعد الختم. ده مش توقيع إلكتروني معتمد.",
}
PACK_KEY_UNAVAILABLE = {
    "en": "ONE could not access the key store to seal this pack.",
    "ar": "ONE مش قادر يوصل لمخزن المفاتيح عشان يختم الحزمة.",
}
PACK_LABELS = {
    "file": {"en": "File pages", "ar": "صفحات الملف"},
    "cover": {"en": "Cover", "ar": "الغلاف"},
    "divider": {"en": "Divider", "ar": "فاصل"},
    "stamp": {"en": "Stamp", "ar": "ختم نصّي"},
    "page_numbers": {"en": "Page numbers", "ar": "ترقيم الصفحات"},
    "seal": {"en": "Free integrity seal", "ar": "ختم سلامة مجاني"},
    "top": {"en": "Top", "ar": "فوق"},
    "center": {"en": "Center", "ar": "في النص"},
    "bottom": {"en": "Bottom", "ar": "تحت"},
}
PACK_LOCKED = {
    "en": "This PDF needs a password. Add an unlocked copy to the project to include its pages.",
    "ar": "الـ PDF ده محتاج كلمة سر. ضيف نسخة مفتوحة للمشروع عشان تستخدم صفحاته.",
}
