"""The journey and the release: first launch, the tender folder, lessons, archiving, updates."""

# Plan 8: journey and release. "Connect AI" / «وصّل الذكاء الاصطناعي» is the first-launch step
# (connectAi in ui/src/i18n.ts). Proposed terms: Backup key / مفتاح النسخة الاحتياطية, Recovery
# code / كود الاسترجاع, Archived project / مشروع مؤرشف.
PROJECT_ARCHIVED = {
    "en": "This project is archived, so it is read-only. Unarchive it to change it.",
    "ar": "المشروع ده مؤرشف، فهو للقراءة بس. لغي الأرشفة عشان تعدّل فيه.",
}
ARCHIVE_BACKUP_FAILED = {
    "en": "The project is archived, but its final backup was not made. Back it up now.",
    "ar": "المشروع اتأرشف، بس آخر نسخة احتياطية ليه ماتعملتش. اعمله نسخة احتياطية دلوقتي.",
}
AI_CONSENT_NEEDED = {
    "en": "Before ONE uses AI, say yes to the note on where your text goes.",
    "ar": "قبل ما ONE يستخدم الذكاء الاصطناعي، وافق على الملاحظة اللي بتوضح نصك بيروح فين.",
}
CLAUDE_CODE_NOT_FOUND = {
    "en": (
        "Claude Code was not found on this computer. Install it, sign in to it once in a "
        "terminal, then try again."
    ),
    "ar": (
        "مالقيناش Claude Code على الجهاز ده. نزّله، وسجّل دخولك فيه مرة من الـ terminal، "
        "وبعدين جرّب تاني."
    ),
}

# Tender folder import and the "I understood this" card. FACT_* and COUNT_* go back to the Lead
# QS from the card's check, so they say exactly what to send.
ZIP_TOO_BIG = {
    "en": (
        "This zip holds more than 2 GB once opened, so ONE kept it as a file and did not "
        "open it. Unzip it and add the folder instead."
    ),
    "ar": (
        "الملف المضغوط ده بعد ما يتفك أكبر من 2 جيجا، فـ ONE حفظه زي ما هو ومافتحهوش. "
        "فكّه وضيف الفولدر بداله."
    ),
}
ZIP_UNSAFE = {
    "en": (
        "This zip looks unsafe to open (too many files, or packed far too tightly), so ONE "
        "kept it as a file and did not open it."
    ),
    "ar": (
        "الملف المضغوط ده شكله مش أمان يتفتح (ملفات كتير قوي، أو مضغوط بزيادة)، فـ ONE "
        "حفظه زي ما هو ومافتحهوش."
    ),
}
FACT_NEEDS_SOURCE = {
    "en": (
        "{fact} has no source. Send the file_id of the file it comes from and a locator, "
        'such as {{"page": 3}} or {{"sheet": "BOQ", "row": 12}}.'
    ),
    "ar": (
        "{fact} مالوش مصدر. ابعت الـ file_id بتاع الملف اللي جاي منه ومكانه فيه، "
        'زي {{"page": 3}} أو {{"sheet": "BOQ", "row": 12}}.'
    ),
}
FACT_FILE_UNKNOWN = {
    "en": "There is no current file with file_id {file_id}. Use an id that files_list gives.",
    "ar": "مفيش ملف حالي الـ file_id بتاعه {file_id}. استخدم id من اللي files_list بيديه.",
}
FACT_LOCATOR_UNKNOWN = {
    "en": (
        "The locator for {fact} names no page or row of file {file_id}. Read the file with "
        "files_read, then send a page, or a sheet and row, that it has."
    ),
    "ar": (
        "مكان {fact} مش بيشاور على صفحة أو صف موجود في الملف {file_id}. اقرا الملف بـ "
        "files_read، وبعدين ابعت صفحة، أو شيت وصف، موجودين فيه."
    ),
}
FACT_DATE_BAD = {
    "en": "{fact} must be a real date written as YYYY-MM-DD, such as 2026-12-01.",
    "ar": "{fact} لازم يكون تاريخ حقيقي مكتوب YYYY-MM-DD، زي 2026-12-01.",
}
COUNT_NEEDS_TRACE = {
    "en": (
        "items_count must come from code, never be typed: import the BOQ with boq_import and "
        "send its import_id as the trace_id (or the id of a calculation that counts them)."
    ),
    "ar": (
        "items_count لازم ييجي من الكود، ومايتكتبش باليد: استورد جدول الكميات بـ boq_import "
        "وابعت الـ import_id بتاعه كـ trace_id (أو id حساب بيعدّهم)."
    ),
}
FACT_SUBMISSION_DATE = {"en": "The submission date", "ar": "ميعاد التقديم"}
UNDERSTAND_BRIEF = {
    "en": "Read the tender folder I just added and fill in the “I understood this” card.",
    "ar": "اقرا فولدر المناقصة اللي لسه ضايفه واملا بطاقة «فهمت كده».",
}
LESSONS_BRIEF = {
    "en": "Before I close this project, propose the lessons learned from how we worked on it.",
    "ar": "قبل ما أقفل المشروع ده، اقترح الدروس المستفادة من طريقة شغلنا فيه.",
}
LESSON_STAYS_CONFIDENTIAL = {
    "en": "This is a Confidential Project, so its lessons stay in it.",
    "ar": "ده مشروع سري، فدروسه بتفضل جوّاه.",
}
LESSON_NOT_FOUND = {
    "en": "This lesson is not in the project.",
    "ar": "الدرس ده مش موجود في المشروع.",
}
ARCHIVE_WAITS_FOR_BRIEF = {
    "en": "A Brief is still running in this project. Let it finish or stop it, then archive.",
    "ar": "فيه تكليف لسه شغال في المشروع ده. استنى لما يخلص أو وقّفه، وبعدين أرشف.",
}

# The updater.
UPDATE_FAILED = {
    "en": (
        "The update did not install, so ONE is still on this version and your projects are "
        "as they were. Try again later."
    ),
    "ar": "التحديث ماتسطبش، فـ ONE لسه على النسخة دي ومشاريعك زي ما هي. جرّب تاني بعدين.",
}
UPDATE_OFFLINE = {
    "en": "Could not check for updates. Check the internet connection, then try again.",
    "ar": "مقدرناش ندوّر على تحديثات. اتأكد إن النت شغال وجرّب تاني.",
}
