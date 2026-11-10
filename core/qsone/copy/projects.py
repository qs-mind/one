"""Projects and files: Project Records, the workspace, what a drop held, reading and OCR."""

# Project Records: projects.
PROJECT_NOT_FOUND = {
    "en": "This project is not on this computer.",
    "ar": "المشروع ده مش موجود على الجهاز ده.",
}

PROJECT_NAME_TAKEN = {
    "en": "A project with this name is already on this computer. Open it, or pick another name.",
    "ar": "فيه مشروع بالاسم ده على الجهاز. افتحه، أو اختار اسم تاني.",
}

PROJECT_NOT_OPEN = {
    "en": "Open the project first.",
    "ar": "افتح المشروع الأول.",
}

PROJECT_KEY_MISSING = {
    "en": "The project's key is not in the system key store, so it cannot be opened.",
    "ar": "مفتاح المشروع مش موجود في مخزن المفاتيح في الجهاز، فمش هينفع يتفتح.",
}

PROJECT_KEY_STORE_DOWN = {
    "en": (
        "The system key store is not available, so ONE cannot use the project's key. "
        "Unlock it or turn it on, then try again."
    ),
    "ar": (
        "مخزن المفاتيح في الجهاز مش متاح، فـ ONE مش قادر يوصل لمفتاح المشروع. "
        "افتحه أو شغّله وجرّب تاني."
    ),
}

PROJECT_DAMAGED = {
    "en": (
        "The project file cannot be read (it is damaged, or the key does not match). "
        "Nothing was changed."
    ),
    "ar": "ملف المشروع مش بيتقري (يا إما بايظ، يا إما المفتاح مش مطابق). ماتغيرش فيه حاجة.",
}

PROJECT_TOO_NEW = {
    "en": "A newer version of ONE saved this project. Update ONE, then open it.",
    "ar": "المشروع ده اتحفظ بنسخة أحدث من ONE. حدّث ONE وبعدين افتحه.",
}

PROJECT_DATED_NAME = {"en": "Project {date}", "ar": "مشروع {date}"}

# Project Records: files.
FILE_TOO_BIG = {
    "en": "The file is larger than 256 MB, so it was not added.",
    "ar": "الملف أكبر من 256 ميجا، فماتضافش.",
}

FILE_EMPTY = {
    "en": "The file is empty.",
    "ar": "الملف فاضي.",
}
# After the name dropped (ui: records/RecordsPanel.tsx): the same bytes are kept once.
FILE_SAME_AS = {
    "en": "is the same file as {old}; kept once.",
    "ar": "هو نفس {old}، اتحفظ مرة واحدة.",
}
FILE_SAME_AGAIN = {
    "en": "is already here; kept once.",
    "ar": "موجود بالفعل، اتحفظ مرة واحدة.",
}

FILE_NOT_READ_YET = {
    "en": "Kept in Project Records. ONE cannot read this kind of file yet.",
    "ar": "اتحفظ في سجلات المشروع. ONE لسه مش بيقرا النوع ده من الملفات.",
}

FILE_SCANNED_PAGES = {
    "en": "Some pages have no text layer (they are scanned), so they cannot be searched yet.",
    "ar": "في صفحات مفيهاش نص (متصورة سكانر)، فلسه مش هينفع ندوّر فيها.",
}

FILE_UNREADABLE = {
    "en": "Kept, but ONE could not read it (it is damaged, or locked with a password).",
    "ar": "اتحفظ، بس ONE مقدرش يقراه (يا إما بايظ، يا إما مقفول بباسورد).",
}

FILE_LOCKED = {
    "en": "Kept, but it is locked with a password, so ONE cannot read it. Save an open copy "
    "(without the password) and add that one.",
    "ar": "اتحفظ، بس مقفول بباسورد فـ ONE مش قادر يقراه. احفظ نسخة مفتوحة (من غير الباسورد) "
    "وضيفها.",
}

FILE_SHEETS_EMPTY = {
    "en": "Read: its sheets are empty, so there is nothing in it.",
    "ar": "اتقرا: الشيتات بتاعته فاضية، مفيهوش حاجة.",
}

FILE_NOT_FOUND = {
    "en": "This file is not in Project Records.",
    "ar": "الملف ده مش موجود في سجلات المشروع.",
}

# The workspace.
WORKSPACE_BAD = {
    "en": "The open document was not saved: ONE does not know its name.",
    "ar": "المستند المفتوح ما اتحفظش: ONE مش عارف اسمه.",
}
CLIENT_BOQ_NOT_FOUND = {
    "en": "No BOQ was imported from this file.",
    "ar": "مفيش مقايسة اتستوردت من الملف ده.",
}
# The Checking QS's comment on a Priced BOQ row whose item is not in the client's BOQ.
NOT_IN_CLIENT_BOQ = {
    "en": "Not in the client's BOQ: {code} {description}. Keep it or remove it?",
    "ar": "البند ده مش موجود في مقايسة العميل: {code} {description}. تسيبه ولا تشيله؟",
}

PAGE_NOT_FOUND = {
    "en": "The file has no page with this number.",
    "ar": "الملف مفيهوش صفحة بالرقم ده.",
}

FILE_HAS_NO_PAGES = {
    "en": "Only a PDF file shows its pages; this file shows its text.",
    "ar": "ملف الـ PDF بس هو اللي بيعرض صفحاته؛ الملف ده بيعرض النص بتاعه.",
}

PROJECT_IS_CONFIDENTIAL = {
    "en": "This is a Confidential Project, so the General chat cannot hand anything to it.",
    "ar": "ده مشروع سري، فالشات العام مايقدرش يحوّل له أي حاجة.",
}

CHAT_BAD_SELECTION = {
    "en": "What was selected in the open document could not be read, so the message was not sent.",
    "ar": "اللي اتحدد في المستند المفتوح ماتقراش، فالرسالة ماتبعتتش.",
}

# What ONE found in a drop of files, in the project chat (records/report.py). Every number in it
# is read by the core, with the sheet, rows and cell it comes from.
REPORT_HEAD = {"en": "ONE read {files}:", "ar": "ONE قرا {files}:"}
REPORT_FILE = {"en": "{name}: {label}.", "ar": "{name}: {label}."}
REPORT_NOT_READ = {"en": "{name}: {note}", "ar": "{name}: {note}"}
REPORT_TABLES_NOT_READ = {
    "en": "ONE could not read the tables in this file; no BOQ row count is available yet.",
    "ar": "ONE ماقدرش يقرا الجداول في الملف ده؛ عدد بنود المقايسة لسه مش معروف.",
}
REPORT_PDF_PAGES = {"en": "PDF: {pages} pages.", "ar": "ملف PDF: {pages} صفحة."}
REPORT_PDF_UNREAD = {
    "en": "No text on pages: {pages}. These pages still need reading from their images.",
    "ar": "الصفحات دي مفيهاش نص: {pages}. لسه محتاجة تتقري من صورها.",
}
REPORT_PDF_BOQ = {
    "en": "The PDF tables show {rows} BOQ rows; these have not been imported by this report.",
    "ar": "جداول الـ PDF فيها {rows} بند مقايسة؛ التقرير ده ما استوردش البنود.",
}

REPORT_BOQ_SHEET = {
    "en": "Sheet «{sheet}»: {items} in {sections} (rows {first}–{last}).",
    "ar": "شيت «{sheet}»: {items} في {sections} (الصفوف {first}–{last}).",
}
REPORT_TOTAL = {
    "en": "Its own total: {total} (row {row}, column {column}).",
    "ar": "إجماليه في الملف: {total} (صف {row}، عمود {column}).",
}
REPORT_NO_TOTAL = {"en": "No total row in it.", "ar": "مفيش فيه صف إجمالي."}
REPORT_MISSING = {
    "en": "Not among the project's files yet: {missing}.",
    "ar": "لسه مش موجود في ملفات المشروع: {missing}.",
}
REPORT_LABELS = {
    "boq": {"en": "BOQ", "ar": "مقايسة"},
    "specs": {"en": "Specifications", "ar": "مواصفات"},
    "conditions": {"en": "Conditions of contract", "ar": "شروط التعاقد"},
    "quote": {"en": "Quotation", "ar": "عرض سعر"},
    "drawings": {"en": "Drawings", "ar": "رسومات"},
    "price_list": {"en": "Price list", "ar": "قائمة أسعار"},
    "sheet": {"en": "Spreadsheet, not a BOQ", "ar": "شيت إكسل، مش مقايسة"},
    "image": {"en": "Image", "ar": "صورة"},
    "document": {"en": "Document; ONE could not tell its kind", "ar": "مستند؛ ONE مقدرش يعرف نوعه"},
}

REPORT_DRAWING = {
    "en": "Drawing, {sheets} sheets: {index}",
    "ar": "رسم، {sheets} لوحات: {index}",
}

REPORT_DRAWING_REV = {"en": "rev {revision}", "ar": "مراجعة {revision}"}

# Files.
FILE_NOT_IN_PROJECT = {
    "en": "There is no file with this id here. files_list shows the files.",
    "ar": "مفيش ملف بالرقم ده هنا. files_list بيعرض الملفات.",
}
FILE_PAGES_OUT_OF_RANGE = {
    "en": "Those pages are not in the file. It has {pages}.",
    "ar": "الصفحات دي مش في الملف. الملف فيه {pages}.",
}
FILE_LIBREOFFICE_MISSING = {
    "en": "Kept. LibreOffice opens this file, but is not installed. Download it from "
    "https://www.libreoffice.org/download/download-libreoffice/.",
    "ar": "اتحفظ. LibreOffice بيفتح الملف ده، بس مش متثبت. نزّله من "
    "https://www.libreoffice.org/download/download-libreoffice/.",
}
FILE_OFFICE_CONVERSION_FAILED = {
    "en": "Kept. LibreOffice could not convert this file or took too long. "
    "Open it in LibreOffice and export a PDF or XLSX copy, then drop that copy.",
    "ar": "اتحفظ. LibreOffice مقدرش يحوّل الملف ده أو أخد وقت طويل. "
    "افتحه في LibreOffice وصدّر نسخة PDF أو XLSX، وبعدين ارمي النسخة دي.",
}
FILE_OLD_WORD = {
    "en": (
        "Kept. ONE reads Word files saved as .docx: open this one in Word, save it as .docx, "
        "then drop it again."
    ),
    "ar": (
        "اتحفظ. ONE بيقرا ملفات Word المحفوظة .docx: افتح الملف ده في Word واحفظه .docx "
        "وبعدين ارميه تاني."
    ),
}
FILE_DWG_NOT_YET = {
    "en": "This drawing was kept before ONE’s drawing reader was available.",
    "ar": "الرسم ده اتحفظ قبل ما قارئ الرسومات بتاع ONE يبقى متاح.",
}
FILE_IMAGE_STORED = {
    "en": "Kept. ONE is reading the image on this computer.",
    "ar": "اتحفظت. ONE بيقرا الصورة على الجهاز ده.",
}
FILE_HIDDEN_TEXT = {
    "en": (
        "This file has hidden text (white, tiny or invisible) or lines that look like orders to "
        "an AI. ONE treats them as data only and shows them to you and the Checking QS."
    ),
    "ar": (
        "الملف ده فيه نص مخفي (أبيض أو صغير جداً أو مش ظاهر) أو سطور شكلها أوامر لذكاء اصطناعي. "
        "ONE بيتعامل معاها كبيانات بس وبيوريها ليك ولمهندس المراجعة."
    ),
}

FILE_DRAWINGS_MISSING = {
    "en": "Kept. ONE's drawing reader is unavailable on this computer.",
    "ar": "اتحفظ. قارئ الرسومات بتاع ONE مش متاح على الجهاز ده.",
}
FILE_DRAWINGS_LIMIT = {
    "en": "Kept. This drawing exceeds the local reader's size limit.",
    "ar": "اتحفظ. حجم الرسم ده أكبر من حد القارئ المحلي.",
}
FILE_DRAWINGS_REPAIRED = {
    "en": "Read with repairs or limits. Some drawing content may be missing.",
    "ar": "اتقرا بإصلاحات أو حدود. ممكن يكون فيه محتوى ناقص من الرسم.",
}
FILE_DRAWING_PREVIEW = {
    "en": "A drawing preview is not available yet; ONE shows the text it read from the drawing.",
    "ar": "معاينة الرسم لسه مش متاحة؛ ONE بيعرض النص اللي قراه من الرسم.",
}

# Scanned pages: read on this computer first, then the engineer's AI.
OCR_LOCAL_NOT_READY = {
    "en": (
        "The text reader for pictures is still being set up on this computer, "
        "so your AI reads these pages for now."
    ),
    "ar": "قارئ النص في الصور لسه بيتجهز على الجهاز ده، فنموذجك هو اللي هيقرا الصفحات دي دلوقتي.",
}
OCR_LOCAL_FAILED = {
    "en": "ONE could not read these pages on this computer. Your AI reads them instead.",
    "ar": "ONE مقدرش يقرا الصفحات دي على الجهاز ده. نموذجك هو اللي هيقراها.",
}
OCR_NUMBERS_UNCHECKED = {
    "en": (
        "Pages {pages} were read on this computer, for search and finding places only: their "
        "numbers are not checked. Before a number from them is cited, imported or priced, your "
        "AI reads the page (files_read with ocr=true) or the engineer confirms it."
    ),
    "ar": (
        "الصفحات {pages} اتقرت على الجهاز ده للبحث وتحديد الأماكن بس: أرقامها لسه ما اتراجعتش. "
        "قبل ما رقم منها يتاخد مصدر أو يتستورد أو يتسعّر، نموذجك يقرا الصفحة "
        "(files_read مع ocr=true) أو المهندس يأكده."
    ),
}
SOURCE_READ_LOCALLY = {
    "en": (
        "This page was read from its picture on this computer, so its numbers are not checked. "
        "Have your AI read the page (files_read with ocr=true) or ask the engineer, then cite "
        "that reading."
    ),
    "ar": (
        "الصفحة دي اتقرت من صورتها على الجهاز ده، فأرقامها لسه ما اتراجعتش. خلّي نموذجك يقرا "
        "الصفحة (files_read مع ocr=true) أو اسأل المهندس، وبعدها خد المصدر من القراية دي."
    ),
}
OCR_LOW_CONFIDENCE = {
    "en": (
        "Low-confidence OCR: the Lead QS must check this page against its image "
        "before using its numbers."
    ),
    "ar": (
        "الثقة في قراية الصفحة قليلة: كبير مهندسي الكميات لازم يراجعها على الصورة "
        "قبل استخدام أرقامها."
    ),
}

OCR_NEEDS_MODEL = {
    "en": (
        "Reading scanned pages needs an AI model that can read images. Connect one, then ask again."
    ),
    "ar": "قراية الصفحات المتصورة محتاجة نموذج ذكاء اصطناعي بيقرا الصور. وصّل واحد واطلب تاني.",
}
OCR_FAILED = {
    "en": "The page image could not be read. Try again, or use another model.",
    "ar": "صورة الصفحة مااتقرتش. جرّب تاني، أو استخدم نموذج تاني.",
}
OCR_ASK = {
    "en": "Read {pages} scanned pages with {model}? About {cost}.",
    "ar": "أقرا {pages} صفحة متصورة بـ {model}؟ تقريباً {cost}.",
}
OCR_ASK_UNKNOWN = {
    "en": (
        "Read {pages} scanned pages with {model}? ONE cannot tell the cost: it has no known price."
    ),
    "ar": "أقرا {pages} صفحة متصورة بـ {model}؟ ONE مش عارف التكلفة: النموذج ملوش سعر معروف.",
}
OCR_COST = {"en": "{usd} USD", "ar": "{usd} دولار"}
OCR_COST_EQUIVALENT = {
    "en": "{usd} USD of equivalent cost on your Claude subscription",
    "ar": "{usd} دولار تكلفة مكافئة على اشتراك Claude بتاعك",
}
OCR_IMAGE_KIND = {
    "en": "ONE reads PNG and JPEG images. Save this image as PNG or JPEG, then drop it again.",
    "ar": "ONE بيقرا صور PNG و JPEG. احفظ الصورة دي PNG أو JPEG وارميها تاني.",
}
A_FILE = {"en": "a file", "ar": "ملف"}  # DOING_FILES_READ's {name} before the file is known

# Revision comparison: observed words/pixels only, never inferred engineering changes.
COMPARE_PAIRING_REVIEW = {
    "en": "This sheet pairing needs a look: more than one sheet number was found on a page.",
    "ar": "ربط اللوحتين محتاج نظرة: لقينا أكتر من رقم لوحة في صفحة.",
}
COMPARE_TEXT = {"en": "Page words changed.", "ar": "كلمات الصفحة اتغيّرت."}
COMPARE_PIXELS = {"en": "Page image changed.", "ar": "صورة الصفحة اتغيّرت."}
COMPARE_TEXT_PIXELS = {"en": "Page words and image changed.", "ar": "كلمات وصورة الصفحة اتغيّروا."}
COMPARE_WIDTH = {
    "en": "Choose a supported page image size.",
    "ar": "اختار مقاس مدعوم لصورة الصفحة.",
}
COMPARE_STEP = {"en": "Comparing file revisions", "ar": "بيقارن نسخ الملفات"}
