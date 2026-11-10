"""The team's identities (Phase 1, C5): the fixed members' cards, the refusals of a proposed
member, keeping a member, and the title of each tool a member is given."""

# The fixed members (contract Q15: the short names stay in Latin letters in Arabic too, as the
# mockups draw them).
LEAD_NAME = {"en": "Lead QS", "ar": "Lead QS"}
LEAD_TITLE = {"en": "Senior quantity surveyor", "ar": "مهندس كميات أول"}
LEAD_SPECIALITY = {"en": "Tender lead and planning agent", "ar": "وكيل قيادة وتخطيط العطاء"}
LEAD_STYLE = {
    "en": "Plans first, writes short, raises one decision at a time.",
    "ar": "بيخطط الأول، كلامه قصير، وبيرفع قرار واحد في المرة.",
}
CHECKER_NAME = {"en": "Checking QS", "ar": "Checking QS"}
CHECKER_TITLE = {"en": "Reviewing quantity surveyor", "ar": "مهندس كميات مراجع"}
CHECKER_SPECIALITY = {"en": "Blind checking agent", "ar": "وكيل مراجعة مستقلة"}
CHECKER_STYLE = {
    "en": "Sees only the work and its sources, checks every number, never goes online.",
    "ar": "بيشوف الشغل ومصادره بس، بيراجع كل رقم، وعمره ما بيطلع أونلاين.",
}

# What a member does now (TeamMember.doing) when it waits.
MEMBER_WAITING_FOR = {"en": "Waiting for you: {what}", "ar": "مستني ردك: {what}"}  # a card title
MEMBER_WAITING = {"en": "Waiting for you", "ar": "مستني ردك"}

# A proposed member that does not fit. The model reads the English; {field} is "team[0].title".
IDENTITY_NEEDS_BOTH = {
    "en": "{field} needs its English and its Arabic.",
    "ar": "{field} محتاج الإنجليزي والعربي.",
}
IDENTITY_TOO_LONG = {
    "en": "{field} is too long: at most {limit} characters.",
    "ar": "{field} طويل: {limit} حرف بالكتير.",
}
IDENTITY_NO_PERSON_NAME = {
    "en": (
        "A team member is never given a person's name or a form of address. Name it for its "
        "work: a QS term with a role, e.g. Contracts QS / مهندس العقود."
    ),
    "ar": (
        "عضو الفريق مايتسماش باسم شخص ولا بلقب. سمّيه بشغله: مصطلح كميات مع دور، "
        "زي Contracts QS / مهندس العقود."
    ),
}
IDENTITY_TITLE_NO_ROLE = {
    "en": (
        "{field} joins a QS term with a role, in each language: e.g. Contracts quantity "
        "surveyor / مهندس كميات العقود."
    ),
    "ar": (
        "{field} مصطلح كميات مع دور، في كل لغة: "
        "زي Contracts quantity surveyor / مهندس كميات العقود."
    ),
}
IDENTITY_SPECIALITY_NO_AGENT = {
    "en": (
        "{field} joins a QS term with an agentic one, in each language: e.g. Contract "
        "conditions agent / وكيل شروط التعاقد."
    ),
    "ar": (
        "{field} مصطلح كميات مع كلمة وكيل، في كل لغة: "
        "زي Contract conditions agent / وكيل شروط التعاقد."
    ),
}
IDENTITY_NO_CHECKER = {
    "en": (
        "The Checking QS is one of the two fixed members and checks every Deliverable on its "
        "own; no other member checks or reviews. Name the member for its own work."
    ),
    "ar": (
        "الـ Checking QS واحد من العضوين الثابتين وبيراجع كل مُخرَج لوحده؛ مفيش عضو تاني "
        "بيراجع. سمّي العضو بشغله هو."
    ),
}
IDENTITY_FIXED_MEMBER = {
    "en": "The Lead QS and the Checking QS are always in the team: leave them out of it.",
    "ar": "الـ Lead QS والـ Checking QS دايمًا في الفريق: ماتكتبهمش فيه.",
}
IDENTITY_NAME_TAKEN = {
    "en": "{field}: another member of this team has that name.",
    "ar": "{field}: في عضو تاني في الفريق ده بنفس الاسم.",
}
IDENTITY_TOOL_UNKNOWN = {
    "en": "{field}: a member has no tool named {tools}.",
    "ar": "{field}: مفيش أداة للعضو اسمها {tools}.",
}
IDENTITY_TOO_MANY = {
    "en": "A tender's team has at most {limit} members beside the Lead QS and the Checking QS.",
    "ar": "فريق العطاء فيه {limit} أعضاء بالكتير غير الـ Lead QS والـ Checking QS.",
}
IDENTITY_MEMBER_NOT_FOUND = {
    "en": "No member of this team or of your permanent team has that id.",
    "ar": "مفيش عضو في الفريق ده ولا في فريقك الدائم بالرقم ده.",
}

# Keeping a member for every later tender (the keep_member card).
KEEP_MEMBER_TITLE = {"en": "Keep {name} in your team?", "ar": "نخلّي {name} في فريقك؟"}
KEEP_MEMBER_DETAIL = {
    "en": (
        "{title}, {speciality}. Kept, it joins every later tender you choose it for, with its "
        "record of work in ONE."
    ),
    "ar": (
        "{title}، {speciality}. لو خلّيناه، هيبقى متاح لأي عطاء جاي تختاره فيه، "
        "ومعاه سجل شغله في ONE."
    ),
}
KEEP_MEMBER_CONFIDENTIAL = {
    "en": (
        "This is a Confidential Project: its members stay in it, so none is kept for other "
        "tenders. Do not ask again."
    ),
    "ar": "ده مشروع سري: أعضاؤه بيفضلوا فيه، فمفيش عضو بيتنقل لعطاءات تانية. ماتسألش تاني.",
}
KEEP_MEMBER_FIXED = {
    "en": "The Lead QS and the Checking QS are permanent already.",
    "ar": "الـ Lead QS والـ Checking QS دائمين أصلًا.",
}
TOOL_KEEP_MEMBER = {"en": "Asking to keep a team member", "ar": "بيسأل نخلّي عضو في الفريق"}

# The title of each tool a member may be given (Member.tools), by the tool's name.
TOOL_TITLES = {
    "search_records": {"en": "Search the project records", "ar": "البحث في سجلات المشروع"},
    "read_chunk": {"en": "Read a passage of a file", "ar": "قراءة جزء من ملف"},
    "find_items": {"en": "Find BOQ items", "ar": "إيجاد بنود المقايسة"},
    "ledger_numbers": {"en": "Read the sourced numbers", "ar": "قراءة الأرقام ومصادرها"},
    "rank_items": {"en": "Rank BOQ items", "ar": "ترتيب بنود المقايسة"},
    "add_source": {"en": "Add a source", "ar": "إضافة مصدر"},
    "add_item": {"en": "Add a BOQ item", "ar": "إضافة بند للمقايسة"},
    "record_number": {"en": "Record a number with its source", "ar": "تسجيل رقم بمصدره"},
    "correct_number": {"en": "Correct a number", "ar": "تصحيح رقم"},
    "calculate": {"en": "Calculate", "ar": "الحساب"},
    "define_unit": {"en": "Define a unit", "ar": "تعريف وحدة"},
    "explain_number": {"en": "Explain a number", "ar": "شرح رقم"},
    "recalculate": {"en": "Recalculate", "ar": "إعادة الحساب"},
    "plan_brief": {"en": "Plan the work", "ar": "تخطيط الشغل"},
    "build_specialist": {"en": "Build a specialist", "ar": "تجهيز مهندس متخصص"},
    "delegate": {"en": "Hand work to a member", "ar": "تسليم شغل لعضو"},
    "send_message": {"en": "Write to the team", "ar": "الكتابة للفريق"},
    "make_deliverable": {"en": "Make a Deliverable", "ar": "عمل مُخرَج"},
    "submit_for_check": {"en": "Send work to the Checking QS", "ar": "إرسال الشغل للـ Checking QS"},
    "save_desk": {"en": "Save a Desk", "ar": "حفظ قسم"},
    "use_desk": {"en": "Use a saved Desk", "ar": "استخدام قسم محفوظ"},
    "project_map": {"en": "Read the Project Map", "ar": "قراءة خريطة المشروع"},
    "files_list": {"en": "List the tender files", "ar": "عرض ملفات العطاء"},
    "files_read": {"en": "Read the tender files", "ar": "قراءة ملفات العطاء"},
    "compare_files": {"en": "Compare two files", "ar": "مقارنة ملفين"},
    "boq_preview": {"en": "Preview a BOQ", "ar": "معاينة مقايسة"},
    "boq_import": {"en": "Import a BOQ", "ar": "استيراد مقايسة"},
    "boq_price_from_sheet": {"en": "Price a BOQ from a sheet", "ar": "تسعير مقايسة من شيت"},
    "ask_engineer": {"en": "Ask you", "ar": "سؤالك"},
    "prices_lookup": {"en": "Look up market prices", "ar": "البحث في أسعار السوق"},
    "prices_propose": {"en": "Propose a market price", "ar": "اقتراح سعر سوق"},
    "note_lesson": {"en": "Note a lesson learned", "ar": "تسجيل درس مستفاد"},
    "connector_tools": {"en": "List a Connector's tools", "ar": "عرض أدوات الوصلة"},
    "connector_call": {"en": "Use a Connector", "ar": "استخدام وصلة"},
    "understood": {"en": "Say what it understood", "ar": "قول اللي فهمه"},
    "show": {"en": "Show a view", "ar": "عرض جدول أو شكل"},
    "pack_propose": {"en": "Propose a tender pack", "ar": "اقتراح ملف العطاء"},
    "deliverable_create": {"en": "Create a Deliverable", "ar": "إنشاء مُخرَج"},
    "deliverable_read": {"en": "Read a Deliverable", "ar": "قراءة مُخرَج"},
    "deliverable_propose": {
        "en": "Propose changes to a Deliverable",
        "ar": "اقتراح تعديلات على مُخرَج",
    },
    "deliverable_comment": {"en": "Answer a comment", "ar": "الرد على تعليق"},
    "client_file_read": {"en": "Read the client's file", "ar": "قراءة ملف العميل"},
    "client_file_plan": {"en": "Plan the client's file", "ar": "تخطيط ملف العميل"},
    "sandbox_run": {"en": "Run a calculation script", "ar": "تشغيل سكريبت حساب"},
    "sandbox_rerun": {"en": "Rerun a calculation script", "ar": "إعادة تشغيل سكريبت حساب"},
    "web_search": {"en": "Search the web", "ar": "البحث على الإنترنت"},
    "web_read": {"en": "Read a web page", "ar": "قراءة صفحة إنترنت"},
    "keep_member": {"en": "Ask to keep a member", "ar": "طلب الاحتفاظ بعضو"},
}
