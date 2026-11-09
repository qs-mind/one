"""The Sandbox: its Python, and what stops a script."""

# The Sandbox.
SANDBOX_NOT_READY = {
    "en": (
        "The Sandbox's Python is missing or damaged, so no code ran. "
        "ONE downloads it again (about 16 MB) the next time a script runs."
    ),
    "ar": (
        "بايثون الصندوق المعزول ناقص أو بايظ، فمفيش كود اشتغل. "
        "ONE هينزّله تاني (حوالي 16 ميجا) أول ما سكريبت يشتغل."
    ),
}
SANDBOX_DOWNLOAD_FAILED = {
    "en": (
        "The Sandbox's Python did not download (no internet, or the server did not answer). "
        "What came so far is kept. Try again."
    ),
    "ar": (
        "بايثون الصندوق المعزول مانزلش (مفيش نت، أو السيرفر مارَدّش). "
        "اللي نزل لحد دلوقتي محفوظ. جرّب تاني."
    ),
}
SANDBOX_NO_SPACE = {
    "en": (
        "There is not enough free space: the Sandbox's Python needs about 300 MB while it "
        "downloads. Free some space, then try again."
    ),
    "ar": (
        "مفيش مساحة فاضية كفاية: بايثون الصندوق المعزول محتاج حوالي 300 ميجا وهو بينزل. "
        "فضّي شوية مساحة وجرّب تاني."
    ),
}
SANDBOX_SCRIPT_TOO_BIG = {
    "en": (
        "The script is larger than 200 KB. "
        "Send a shorter one that reads its data from the input files."
    ),
    "ar": "السكريبت أكبر من 200 كيلو. ابعت واحد أقصر بيقرا بياناته من ملفات الإدخال.",
}
SANDBOX_RUN_UNKNOWN = {
    "en": "There is no Sandbox run with this id here. A sandbox_run result gives its run id.",
    "ar": "مفيش تشغيلة في الصندوق المعزول بالرقم ده هنا. نتيجة sandbox_run فيها رقم التشغيلة.",
}
SANDBOX_SYNTAX = {
    "en": "The script has a mistake on line {line}: {message}",
    "ar": "في غلطة في السكريبت في سطر {line}: {message}",
}
SANDBOX_MODULE = {
    "en": (
        "The Sandbox has Python's own modules plus openpyxl and xlrd only. "
        "Rewrite the script without {module}."
    ),
    "ar": (
        "الصندوق المعزول فيه موديولات بايثون الأساسية ومعاها openpyxl و xlrd بس. "
        "اكتب السكريبت من غير {module}."
    ),
}
SANDBOX_TIMEOUT = {
    "en": "The script ran longer than {seconds} seconds and was stopped.",
    "ar": "السكريبت اشتغل أكتر من {seconds} ثانية فاتوقف.",
}
SANDBOX_MEMORY = {
    "en": "The script used more than 512 MB of memory and was stopped.",
    "ar": "السكريبت استهلك أكتر من 512 ميجا من الذاكرة فاتوقف.",
}
SANDBOX_TOO_MUCH = {
    "en": "The script's files are larger than 64 MB in all.",
    "ar": "ملفات السكريبت أكبر من 64 ميجا في المجموع.",
}
SANDBOX_FAILED = {
    "en": "The script stopped with an error; its last lines are below.",
    "ar": "السكريبت وقف بغلطة؛ آخر سطوره تحت.",
}
