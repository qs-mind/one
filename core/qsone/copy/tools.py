"""The tools' own words: approvals, the Progress Line, activity words, ask_engineer's card."""

# Approvals. {agent} is the agent's name; {action} its Progress Line words.
ASK_OUTSIDE = {
    "en": "{agent}: {action}. This leaves this computer. Allow it?",
    "ar": "{agent}: {action}. ده هيطلع برّه الجهاز ده. نسمح بيه؟",
}

ASK_ONLINE = {
    "en": (
        "{agent}: {action}. This goes online after reading project files, "
        "and text in files can hide instructions. Allow it?"
    ),
    "ar": (
        "{agent}: {action}. ده هيدخل على النت بعد ما قرا ملفات المشروع، "
        "والنص اللي في الملفات ممكن يكون مستخبي فيه أوامر. نسمح بيه؟"
    ),
}

# Progress Line words of the tools. {tool} is a tool's name; the other values come from its call.
# What a step is, for the Progress Line, when the tool has no words of its own for its arguments:
# never the tool's id. Every registered tool has its line here (tests/test_arabic.py checks it).
TOOL_STEP = {"en": "Working on a step", "ar": "بيشتغل على خطوة"}
TOOL_WORDS = {
    "add_item": {"en": "Adding an item to the Source Ledger", "ar": "بيضيف بند لسجل المصادر"},
    "add_source": {"en": "Adding a source to the Source Ledger", "ar": "بيضيف مصدر لسجل المصادر"},
    "ask_engineer": {"en": "Asking you a question", "ar": "بيسألك سؤال"},
    "boq_import": {"en": "Importing the BOQ", "ar": "بيستورد جدول الكميات"},
    "boq_price_from_sheet": {
        "en": "Pricing the BOQ from the build-up sheet",
        "ar": "بيسعّر المقايسة من شيت التسعير",
    },
    "boq_preview": {"en": "Looking at the BOQ's columns", "ar": "بيشوف أعمدة جدول الكميات"},
    "build_specialist": {"en": "Setting up a specialist", "ar": "بيجهّز متخصص"},
    "calculate": {"en": "Calculating a number", "ar": "بيحسب رقم"},
    "client_file_plan": {
        "en": "Planning how to fill the client's file",
        "ar": "بيخطط إزاي يملا ملف العميل",
    },
    "client_file_read": {"en": "Reading the client's file", "ar": "بيقرا ملف العميل"},
    "connector_call": {"en": "Using a connected app", "ar": "بيستخدم تطبيق متوصّل"},
    "connector_tools": {
        "en": "Looking at what the connected apps can do",
        "ar": "بيشوف التطبيقات المتوصّلة تقدر تعمل إيه",
    },
    "correct_number": {"en": "Correcting a number", "ar": "بيصحّح رقم"},
    "define_unit": {"en": "Defining a project unit", "ar": "بيعرّف وحدة للمشروع"},
    "delegate": {"en": "Handing work to the team", "ar": "بيسلّم شغل للفريق"},
    "deliverable_comment": {"en": "Commenting on a Deliverable", "ar": "بيعلّق على مُخرج"},
    "deliverable_create": {"en": "Making a Deliverable", "ar": "بيعمل مُخرج"},
    "deliverable_propose": {
        "en": "Suggesting changes to a Deliverable",
        "ar": "بيقترح تعديلات على مُخرج",
    },
    "deliverable_read": {"en": "Reading a Deliverable", "ar": "بيقرا مُخرج"},
    "explain_number": {"en": "Tracing where a number comes from", "ar": "بيتتبّع مصدر رقم"},
    "files_list": {"en": "Looking at the project files", "ar": "بيشوف ملفات المشروع"},
    "project_map": {"en": "Reading the project map", "ar": "بيقرا خريطة المشروع"},
    "files_read": {"en": "Reading a project file", "ar": "بيقرا ملف من ملفات المشروع"},
    "find_items": {"en": "Looking up items", "ar": "بيدوّر على بنود"},
    "hand_to_project": {"en": "Passing the work to a project", "ar": "بيحوّل الشغل لمشروع"},
    "keep_member": {"en": "Asking to keep a team member", "ar": "بيسأل نخلّي عضو في الفريق"},
    "ledger_numbers": {"en": "Reading the project's numbers", "ar": "بيقرا أرقام المشروع"},
    "rank_items": {"en": "Sorting the project's items", "ar": "بيرتّب بنود المشروع"},
    "make_deliverable": {"en": "Making a Deliverable", "ar": "بيعمل مُخرج"},
    "note_lesson": {"en": "Noting a lesson learned", "ar": "بيسجّل درس مستفاد"},
    "offer_new_project": {"en": "Suggesting a new project", "ar": "بيقترح مشروع جديد"},
    "plan_brief": {"en": "Planning the work", "ar": "بيخطط للشغل"},
    "prices_lookup": {"en": "Looking up market prices", "ar": "بيدوّر على أسعار السوق"},
    "prices_propose": {"en": "Proposing prices for you to keep", "ar": "بيقترح أسعار تحفظها"},
    "projects": {"en": "Looking at your projects", "ar": "بيشوف المشاريع"},
    "read_chunk": {
        "en": "Reading a passage of the project files",
        "ar": "بيقرا جزء من ملفات المشروع",
    },
    "recalculate": {"en": "Recalculating numbers", "ar": "بيعيد حساب الأرقام"},
    "record_number": {"en": "Recording a number", "ar": "بيسجّل رقم"},
    "sandbox_rerun": {"en": "Running a script again", "ar": "بيشغّل سكريبت تاني"},
    "sandbox_run": {"en": "Running a script", "ar": "بيشغّل سكريبت"},
    "save_desk": {"en": "Saving a Desk", "ar": "بيحفظ قسم"},
    "search_records": {"en": "Searching the project files", "ar": "بيدوّر في ملفات المشروع"},
    "send_message": {"en": "Sending a message to the team", "ar": "بيبعت رسالة للفريق"},
    "settings_set": {"en": "Changing a setting", "ar": "بيغيّر إعداد"},
    "show": {"en": "Laying out a view for you", "ar": "بيجهّزلك عرض"},
    "submit_for_check": {
        "en": "Sending work to the Checking QS",
        "ar": "بيبعت الشغل لمهندس المراجعة",
    },
    "understood": {
        "en": "Filling in the “I understood this” card",
        "ar": "بيملا بطاقة «فهمت كده»",
    },
    "use_desk": {"en": "Calling on a Desk", "ar": "بيستعين بقسم"},
    "web_read": {"en": "Reading a web page", "ar": "بيقرا صفحة ويب"},
    "open_tools": {"en": "Getting tools ready", "ar": "بيجهّز أدواته"},
    "compare_files": {"en": "Comparing file revisions", "ar": "بيقارن نسخ الملفات"},
    "pack_propose": {"en": "Arranging the tender pack", "ar": "بيرتّب ملف المناقصة"},
    "web_search": {"en": "Searching the web", "ar": "بيدوّر على الويب"},
    "tender_plan_write": {"en": "Writing the tender plan", "ar": "بيكتب خطة المناقصة"},
    "tender_plan_change": {
        "en": "Suggesting a change to the tender plan",
        "ar": "بيقترح تعديل على خطة المناقصة",
    },
}


def tool_step(name: str) -> dict[str, str]:
    """The Progress Line's words for a step of tool `name`: its own line, or a plain one."""
    return TOOL_WORDS.get(name, TOOL_STEP)


TOOL_SEARCH_RECORDS = {
    "en": "Searching the project files for «{query}»",
    "ar": "بيدوّر في ملفات المشروع على «{query}»",
}

TOOL_READ_CHUNK = {
    "en": "Reading a passage of the project files",
    "ar": "بيقرا جزء من ملفات المشروع",
}

TOOL_FIND_ITEMS = {
    "en": "Looking up items in the Source Ledger",
    "ar": "بيدوّر على بنود في سجل المصادر",
}

TOOL_RANK_ITEMS = {
    "en": "Finding the top {top} items by {name}",
    "ar": "بيطلّع أعلى {top} بنود في {name}",
}
TOOL_LEDGER_NUMBERS = {
    "en": "Reading the numbers of item {item}",
    "ar": "بيقرا أرقام البند {item}",
}

TOOL_ADD_SOURCE = {
    "en": "Adding the source «{title}» to the Source Ledger",
    "ar": "بيضيف المصدر «{title}» لسجل المصادر",
}

TOOL_ADD_ITEM = {
    "en": "Adding an item to the Source Ledger",
    "ar": "بيضيف بند لسجل المصادر",
}

TOOL_RECORD_NUMBER = {
    "en": "Recording the {name} of item {item}, with its source",
    "ar": "بيسجّل {name} للبند {item} بمصدره",
}

TOOL_CORRECT_NUMBER = {
    "en": "Correcting a number, keeping the old one",
    "ar": "بيصحّح رقم، والرقم القديم محفوظ",
}

TOOL_PRICE_FROM_SHEET = {
    "en": "Price existing BOQ items from build-up cells",
    "ar": "يسعّر بنود المقايسة الموجودة من خلايا تحليل السعر",
}

# Tools (Plan 5). Activity words: the Progress Line and the online and outside cards show them,
# so they hold the exact thing that would leave One.
DOING_WEB_SEARCH = {"en": "Search the web for: {query}", "ar": "يدوّر في الويب على: {query}"}
DOING_WEB_READ = {"en": "Open the web page: {url}", "ar": "يفتح صفحة الويب: {url}"}
DOING_FILES_READ = {"en": "Read {name}, pages {pages}", "ar": "يقرا {name}، صفحات {pages}"}
DOING_FILES_READ_PAGE = {"en": "Read {name}, page {page}", "ar": "يقرا {name}، صفحة {page}"}
DOING_FILES_READ_ROWS = {
    "en": "Read {name}, sheet {sheet}, rows {rows}",
    "ar": "يقرا {name}، شيت {sheet}، الصفوف {rows}",
}
DOING_FILE_READ = {"en": "Read {name}", "ar": "يقرا {name}"}  # a file with no pages
DOING_BOQ_IMPORT = {
    "en": "Import the BOQ from {name}, sheet {sheet}",
    "ar": "يستورد المقايسة من {name}، شيت {sheet}",
}
DOING_PRICES = {"en": "Look up the price of: {item}", "ar": "يدوّر على سعر: {item}"}
DOING_SANDBOX = {
    "en": "Run a script in the Sandbox on {count} files",
    "ar": "يشغّل سكريبت في الصندوق المعزول على {count} ملف",
}
DOING_CONNECTOR = {
    "en": "Use {connector}: {tool} with {args}",
    "ar": "يستخدم {connector}: {tool} بـ {args}",
}
DOING_ASK = {"en": "Waiting for your answer", "ar": "مستني ردك"}

# ask_engineer's card. {agent} is the agent's name; the questions are the agent's own words.
QUESTION_OWN_REQUEST = {
    "en": "That is the engineer's own question. Answer it from the files you read "
    "(drawing reads start with sheets and block counts; project_map modes sheets/counts); "
    "if truly absent, say what you searched.",
    "ar": "ده نفس سؤال المهندس. جاوب عليه من الملفات اللي قريتها "
    "(قراءة الرسومات بتبدأ باللوحات وأعداد البلوكات؛ وأوضاع project_map هي sheets/counts)؛ "
    "ولو المعلومة مش موجودة فعلاً، قول دورت على إيه.",
}
QUESTION_TITLE = {"en": "{agent} asks", "ar": "{agent} بيسأل"}
QUESTION_DETAIL = {
    "en": "Answer every question, then press Send. Your answers are kept as the source of "
    "any number they give.",
    "ar": "جاوب على كل سؤال، وبعدين دوس إرسال. ردودك بتتحفظ كمصدر لأي رقم فيها.",
}

ON_DEVICE_NO_ONLINE = {
    "en": (
        "This is an On-device Project: nothing leaves this computer, so ONE cannot do this here."
    ),
    "ar": "ده مشروع على الجهاز: مفيش حاجة بتخرج من الجهاز، فـ ONE مش هيقدر يعمل ده هنا.",
}
