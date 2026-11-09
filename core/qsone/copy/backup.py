"""Backups, the Backup key and recovery codes."""

# Backups, the Backup key and recovery codes.
BACKUP_FOLDER_UNREACHABLE = {
    "en": (
        "The backup folder cannot be reached. The last good backup is from {date}. "
        "Connect its drive, or pick another folder."
    ),
    "ar": (
        "مقدرناش نوصل لفولدر النسخة الاحتياطية. آخر نسخة سليمة بتاريخ {date}. "
        "وصّل الهارد بتاعه، أو اختار فولدر تاني."
    ),
}
BACKUP_FOLDER_NOT_WRITABLE = {
    "en": "ONE cannot save files in this folder. Pick an existing folder you can write in.",
    "ar": "ONE مش قادر يحفظ ملفات في الفولدر ده. اختار فولدر موجود تقدر تكتب فيه.",
}
BACKUP_KEY_WRONG = {
    "en": "This backup was made with another Backup key, so this key cannot open it.",
    "ar": "النسخة دي اتعملت بمفتاح نسخة احتياطية تاني، فالمفتاح ده مش هيفتحها.",
}
BACKUP_NEEDS_SIGN_IN = {
    "en": (
        "To open this backup, sign in to the QS Mind account that keeps its Backup key, "
        "or type its recovery code."
    ),
    "ar": (
        "عشان تفتح النسخة دي، سجّل دخولك بحساب QS Mind اللي فيه مفتاح النسخة الاحتياطية، "
        "أو اكتب كود الاسترجاع بتاعها."
    ),
}
BACKUP_NEEDS_CODE = {
    "en": "Type the recovery code for this backup to open it.",
    "ar": "اكتب كود الاسترجاع بتاع النسخة دي عشان تفتحها.",
}
RECOVERY_CODE_WRONG = {
    "en": (
        "This recovery code does not open this backup. Check each group of five, then try again."
    ),
    "ar": "كود الاسترجاع ده مش بيفتح النسخة دي. راجع كل مجموعة من الخمسة وجرّب تاني.",
}
RECOVERY_LAST_GROUP_WRONG = {
    "en": "That is not the code's last group. Look at the code you saved and type its last five.",
    "ar": "دي مش آخر مجموعة في الكود. بص على الكود اللي حفظته واكتب آخر خمسة فيه.",
}
PROJECT_KEY_RESTORED = {
    "en": (
        "The project's key was missing from the system key store, so ONE put it back from "
        "the project's own key file."
    ),
    "ar": (
        "مفتاح المشروع ماكانش في مخزن المفاتيح في الجهاز، فـ ONE رجّعه من ملف المفتاح "
        "بتاع المشروع نفسه."
    ),
}
