"""Reading a file completely: why a drawing or a Word 97-2003 file could not be read, and the
parts of a file ONE did not read (`unread` on a file's JSON: `part` and `why`)."""

from qsone.copy.wording import Noun

# A drawing that could not be read at all (records/drawings): the file's note.
FILE_DRAWING_NOT_DWG = {
    "en": "Kept, but this is not a DWG drawing, though its name ends in .dwg.",
    "ar": "اتحفظ، بس ده مش رسم DWG، مع إن اسمه آخره .dwg.",
}
FILE_DRAWING_TOO_OLD = {
    "en": (
        "Kept, but it was saved by an AutoCAD older than R13, which ONE cannot read. "
        "Save it as DWG 2000 or later, then drop it again."
    ),
    "ar": (
        "اتحفظ، بس متحفظ بنسخة AutoCAD أقدم من R13، وONE مش بيقراها. "
        "احفظه DWG 2000 أو أحدث وارميه تاني."
    ),
}
FILE_DRAWING_DAMAGED = {
    "en": "Kept, but the drawing is damaged or cut short, so ONE could read nothing in it.",
    "ar": "اتحفظ، بس الرسم بايظ أو ناقص، فـ ONE ماقدرش يقرا منه حاجة.",
}
FILE_DRAWING_TOO_LARGE = {
    "en": (
        "Kept, but the drawing is larger than ONE's drawing reader can open. Split it, or purge "
        "it in AutoCAD, then drop it again."
    ),
    "ar": (
        "اتحفظ، بس الرسم أكبر من اللي قارئ الرسومات بتاع ONE يقدر يفتحه. قسّمه، أو اعمله Purge "
        "في AutoCAD، وارميه تاني."
    ),
}
FILE_DRAWING_TIMEOUT = {
    "en": "Kept, but reading the drawing took too long, so ONE stopped. Try again later.",
    "ar": "اتحفظ، بس قراية الرسم خدت وقت طويل، فـ ONE وقف. جرّب تاني بعدين.",
}
FILE_PARTLY_READ = {
    "en": "Read, except the parts listed as not read.",
    "ar": "اتقرا، ما عدا الأجزاء اللي مكتوب إنها ماتقريتش.",
}

# The parts not read (`UnreadPart.part`).
UNREAD_WHOLE_FILE = {"en": "The whole file", "ar": "الملف كله"}
UNREAD_PAGES = {"en": "Pages {pages}", "ar": "الصفحات {pages}"}
UNREAD_DRAWING_ROWS = {
    "texts": Noun(
        en={"one": "1 text", "other": "{n} texts"},
        ar={"one": "نص واحد", "two": "نصين", "few": "{n} نصوص", "other": "{n} نص"},
    ),
    "inserts": Noun(
        en={"one": "1 placed block", "other": "{n} placed blocks"},
        ar={"one": "بلوك واحد", "two": "بلوكين", "few": "{n} بلوكات", "other": "{n} بلوك"},
    ),
    "dimensions": Noun(
        en={"one": "1 dimension", "other": "{n} dimensions"},
        ar={"one": "بُعد واحد", "two": "بُعدين", "few": "{n} أبعاد", "other": "{n} بُعد"},
    ),
    "tables": Noun(
        en={"one": "1 table", "other": "{n} tables"},
        ar={"one": "جدول واحد", "two": "جدولين", "few": "{n} جداول", "other": "{n} جدول"},
    ),
    "references": Noun(
        en={"one": "1 attached file", "other": "{n} attached files"},
        ar={
            "one": "ملف مرفق واحد",
            "two": "ملفين مرفقين",
            "few": "{n} ملفات مرفقة",
            "other": "{n} ملف مرفق",
        },
    ),
    "objects": Noun(
        en={"one": "1 object", "other": "{n} objects"},
        ar={"one": "عنصر واحد", "two": "عنصرين", "few": "{n} عناصر", "other": "{n} عنصر"},
    ),
}
UNREAD_DRAWING_RECORDS = {"en": "Drawing records: {count}", "ar": "سجلات في الرسم: {count}"}
UNREAD_DRAWING_REPAIRED = {"en": "Parts of the drawing: {count}", "ar": "أجزاء من الرسم: {count}"}
UNREAD_DRAWING_CUT = {"en": "Long texts cut short: {count}", "ar": "نصوص طويلة اتقصّت: {count}"}
UNREAD_DRAWING_NESTED = {"en": "Blocks inside blocks", "ar": "بلوكات جوه بلوكات"}
UNREAD_DRAWING_KIND = {"en": "{kind} objects: {count}", "ar": "عناصر {kind}: {count}"}
UNREAD_DRAWING_PROXY = {
    "en": "Objects from CAD add-ons: {count}",
    "ar": "عناصر من إضافات الـ CAD: {count}",
}
UNREAD_DRAWING_3D = {"en": "3D objects: {count}", "ar": "مجسمات 3D: {count}"}
UNREAD_PICTURE_FILE = {"en": "Picture «{name}»", "ar": "صورة «{name}»"}
UNREAD_UNDERLAY_FILE = {"en": "Underlay «{name}»", "ar": "ملف تحت الرسم «{name}»"}
UNREAD_XREF_FILE = {"en": "Attached drawing «{name}»", "ar": "رسم مرفق «{name}»"}
UNREAD_MORE_FILES = {
    "en": "{count} more attached files",
    "ar": "{count} ملفات مرفقة كمان",
}
UNREAD_PICTURES = {
    "en": "Pictures or objects inside: {count}",
    "ar": "صور أو عناصر جوه الملف: {count}",
}
UNREAD_EMBEDDED_SHEETS = {
    "en": "Excel sheets inside: {count}",
    "ar": "شيتات Excel جوه الملف: {count}",
}
UNREAD_EMBEDDED_LEFT = {
    "en": "Pictures or Excel sheets inside: {count}",
    "ar": "صور أو شيتات Excel جوه الملف: {count}",
}
UNREAD_EMBEDDED_CELLS = {"en": "Cells of Excel sheets inside", "ar": "خلايا شيتات Excel اللي جوه"}
UNREAD_DOC_END = {"en": "The end of the file", "ar": "آخر الملف"}
UNREAD_DOC_LOST = {
    "styles": {"en": "Headings", "ar": "العناوين"},
    "tables": {"en": "Tables", "ar": "الجداول"},
    "hidden": {"en": "Hidden and deleted text", "ar": "النص المخفي والممسوح"},
    "headers": {"en": "Headers and footers", "ar": "الهيدر والفوتر"},
    "sections": {"en": "Sections", "ar": "الأقسام"},
    "fields": {"en": "Fields", "ar": "الحقول"},
    "numbering": {"en": "List numbers", "ar": "أرقام القوايم"},
}
UNREAD_DOC_DELETIONS = {
    "en": "Tracked deletions: {count} characters",
    "ar": "حاجات ممسوحة بتتبع التغييرات: {count} حرف",
}
UNREAD_DOC_FORMS = {"en": "Form fields: {count}", "ar": "خانات نماذج: {count}"}
UNREAD_DOC_SYMBOLS = {"en": "Symbol characters: {count}", "ar": "رموز: {count}"}

# Why (`UnreadPart.why`).
UNREAD_WHY_PAGES = {
    "en": "They are scanned: they have no text. ONE reads them from their pictures when asked.",
    "ar": "متصورة سكانر: مفيهاش نص. ONE بيقراها من صورها لما تطلب.",
}
UNREAD_WHY_PAGES_AI = {
    "en": "They are scanned: they have no text. Your AI reads them from their pictures when asked.",
    "ar": "متصورة سكانر: مفيهاش نص. نموذجك هو اللي بيقراها من صورها لما تطلب.",
}
UNREAD_WHY_TOO_MANY = {
    "en": "The drawing holds more than ONE's drawing reader keeps.",
    "ar": "الرسم فيه أكتر من اللي قارئ الرسومات بتاع ONE بيحتفظ بيه.",
}
UNREAD_WHY_CUT_SHORT = {
    "en": "Longer than ONE's drawing reader keeps: the start of each is read.",
    "ar": "أطول من اللي قارئ الرسومات بتاع ONE بيحتفظ بيه: أول كل واحد اتقرا.",
}
UNREAD_WHY_DAMAGED = {
    "en": "This part of the file is damaged; ONE read the rest.",
    "ar": "الجزء ده من الملف بايظ؛ ONE قرا الباقي.",
}
UNREAD_WHY_REPAIRED = {
    "en": "Repaired while reading, so they may be incomplete.",
    "ar": "اتصلحت وهي بتتقري، فممكن تكون ناقصة.",
}
UNREAD_WHY_NESTED = {
    "en": "Nested too deep, or too many objects for ONE's drawing reader.",
    "ar": "متداخلة أوي، أو العناصر أكتر من اللي قارئ الرسومات بتاع ONE بيقراه.",
}
UNREAD_WHY_KIND = {
    "en": "ONE does not read what is inside this kind of object yet.",
    "ar": "ONE لسه مش بيقرا اللي جوه النوع ده من العناصر.",
}
UNREAD_WHY_OTHER_FILE = {
    "en": "It is a separate file, not inside this one. Add it to the project to read it.",
    "ar": "ده ملف لوحده، مش جوه الملف ده. ضيفه للمشروع عشان يتقري.",
}
UNREAD_WHY_PICTURES = {
    "en": "ONE does not read pictures inside a file yet.",
    "ar": "ONE لسه مش بيقرا الصور اللي جوه الملف.",
}
UNREAD_WHY_SHEETS = {
    "en": "Too large, or damaged, for ONE to read.",
    "ar": "كبيرة أوي، أو بايظة، فـ ONE ماقدرش يقراها.",
}
UNREAD_WHY_CUT = {
    "en": "The file is cut short: what was there is read.",
    "ar": "الملف ناقص: اللي كان موجود اتقرا.",
}
UNREAD_WHY_PLAIN = {
    "en": "That part of the file is damaged, so its text is read as plain paragraphs.",
    "ar": "الجزء ده من الملف بايظ، فنصه اتقرا كفقرات عادية.",
}
UNREAD_WHY_DELETIONS = {
    "en": "Deleted with Track Changes; Word shows them struck through. ONE reads the text after "
    "the changes.",
    "ar": "اتمسحت بتتبع التغييرات؛ Word بيعرضها متشطبة. ONE بيقرا النص بعد التغييرات.",
}
UNREAD_WHY_FORMS = {
    "en": "The value chosen in a drop-down or a tick box is not read.",
    "ar": "القيمة المختارة في القايمة أو علامة الصح في الخانة مش بتتقري.",
}
UNREAD_WHY_SYMBOLS = {
    "en": "Characters of symbol fonts (ticks, arrows) are not read.",
    "ar": "حروف خطوط الرموز (علامات الصح والأسهم) مش بتتقري.",
}
