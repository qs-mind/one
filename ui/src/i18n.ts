// The engineer's language. Arabic is the default; the page is right-to-left in Arabic.
import { useSyncExternalStore } from "react";

export type Language = "ar" | "en";
export type Text = { en: string; ar: string };

export const texts = {
  appName: { en: "QS Mind One", ar: "QS Mind One" },
  otherLanguage: { en: "العربية", ar: "English" },
  aiKey: { en: "Claude key", ar: "مفتاح Claude" },
  message: { en: "Message to the Lead QS", ar: "رسالة إلى كبير مهندسي الكميات" },
  empty: { en: "Ask the Lead QS about your work.", ar: "اسأل كبير مهندسي الكميات عن شغلك." },
  send: { en: "Send", ar: "إرسال" },
  stop: { en: "Stop", ar: "إيقاف" },
  thinking: { en: "Working on it…", ar: "جارٍ العمل…" },
  chatError: { en: "The reply stopped because of an error. Try again.", ar: "توقف الرد بسبب خطأ. حاول مرة أخرى." },
  aiKeyTitle: { en: "Add your Claude key", ar: "أضف مفتاح Claude الخاص بك" },
  aiKeyHelp: {
    en: "One works with your own Claude key from Anthropic. It is kept in this computer's key store, never in a file.",
    ar: "يعمل ون بمفتاح Claude الخاص بك من Anthropic. يُحفظ في مخزن المفاتيح على هذا الجهاز، ولا يُكتب في أي ملف.",
  },
  aiKeyLabel: { en: "Claude API key", ar: "مفتاح Claude API" },
  save: { en: "Save", ar: "حفظ" },
  keyAdded: { en: "Key added.", ar: "تمت إضافة المفتاح." },
  keyFailed: { en: "The key was not saved. Try again.", ar: "لم يُحفظ المفتاح. حاول مرة أخرى." },
  close: { en: "Close", ar: "إغلاق" },
  checking: { en: "Starting…", ar: "جارٍ التشغيل…" },
  coreDown: {
    en: "One's core is not running, so the chat cannot work. Its log is here:",
    ar: "محرك ون لا يعمل، لذلك لا تعمل المحادثة. سجله موجود هنا:",
  },
  retry: { en: "Retry", ar: "إعادة المحاولة" },
  // Plan 4 (agent engine). Arabic in plain Egyptian colloquial, as in core/qsone/copy.py, until the founder picks.
  ai: { en: "AI", ar: "الذكاء الاصطناعي" },
  aiTitle: { en: "AI settings", ar: "إعدادات الذكاء الاصطناعي" },
  aiLoading: { en: "Loading AI settings…", ar: "بنحمّل إعدادات الذكاء الاصطناعي…" },
  aiFailed: { en: "AI settings could not be loaded. Try again.", ar: "مقدرناش نجيب إعدادات الذكاء الاصطناعي. جرّب تاني." },
  noAiYet: {
    en: "No AI is connected yet. Add a Claude key, another AI Provider, or your own Claude Code.",
    ar: "لسه مفيش ذكاء اصطناعي متوصّل. ضيف مفتاح Claude، أو مزوّد تاني، أو Claude Code بتاعك.",
  },
  claudeKeySaved: {
    en: "A Claude key is saved. Add a new one only to replace it.",
    ar: "في مفتاح Claude محفوظ. ضيف مفتاح جديد بس لو عايز تغيّره.",
  },
  standardLink: { en: "Standard Link: other AI Providers", ar: "ربط عام: مزوّدين تانيين" },
  standardLinkHelp: {
    en: "Any provider with an OpenAI-compatible API, such as DeepSeek or Mistral, or a model on this computer, such as Ollama.",
    ar: "أي مزوّد عنده API متوافق مع OpenAI، زي DeepSeek أو Mistral، أو نموذج شغال على الجهاز ده، زي Ollama.",
  },
  providerName: { en: "Name", ar: "الاسم" },
  baseUrl: { en: "Base URL", ar: "رابط الـ API (Base URL)" },
  providerKey: { en: "Key (optional: models on this computer have none)", ar: "المفتاح (اختياري: النماذج اللي على الجهاز ملهاش مفتاح)" },
  addProvider: { en: "Add provider", ar: "ضيف المزوّد" },
  providerNotAdded: { en: "The provider was not added. Try again.", ar: "المزوّد ماتضافش. جرّب تاني." },
  providerUrlRefused: {
    en: "One cannot use this address. It must start with http:// or https://, and a key needs https:// unless the model runs on this computer.",
    ar: "One مش هيقدر يستخدم العنوان ده. لازم يبدأ بـ http:// أو https://، ولو في مفتاح لازم https:// إلا لو النموذج شغال على الجهاز ده.",
  },
  remove: { en: "Remove", ar: "شيل" },
  removeFailed: { en: "It was not removed. Try again.", ar: "ماتشالش. جرّب تاني." },
  onDevice: { en: "on this computer, free", ar: "على الجهاز ده، ببلاش" },
  claudeCode: { en: "Claude Code (Subscription Link)", ar: "Claude Code (ربط الاشتراك)" },
  claudeCodeHelp: {
    en: "Use the Claude Code installed on this computer, with your own Claude subscription. One never installs it or signs in for you.",
    ar: "استخدم Claude Code اللي متثبّت على الجهاز ده، باشتراك Claude بتاعك. One عمره ما هيثبّته ولا هيسجّل دخول بدالك.",
  },
  claudeCodePath: { en: "Its file (leave empty to find it by itself)", ar: "الملف بتاعه (سيبه فاضي وOne هيدوّر عليه)" },
  check: { en: "Check", ar: "افحص" },
  claudeCodeChecking: { en: "Checking Claude Code…", ar: "بنفحص Claude Code…" },
  claudeCodeReady: { en: "Claude Code {version} is ready.", ar: "Claude Code {version} جاهز." },
  claudeCodeMissing: {
    en: "Claude Code was not found on this computer. Install it from https://code.claude.com/docs/en/setup, or pick its file.",
    ar: "Claude Code مش موجود على الجهاز ده. نزّله من https://code.claude.com/docs/en/setup، أو اختار الملف بتاعه.",
  },
  claudeCodeTooOld: {
    en: "Your Claude Code lacks options One needs. Update it, then check again.",
    ar: "Claude Code اللي عندك ناقصه اختيارات One محتاجها. حدّثه وبعدين افحص تاني.",
  },
  claudeCodeShim: {
    en: "This is the npm claude.cmd, which One cannot run safely. Install the native Claude Code, then pick it.",
    ar: "ده claude.cmd بتاع npm، وOne مش هيقدر يشغّله بأمان. نزّل Claude Code الأصلي وبعدين اختاره.",
  },
  claudeCodeSignedOut: {
    en: "Claude Code is signed out. Open Claude Code once and sign in, then try again.",
    ar: "Claude Code مش مسجّل دخول. افتح Claude Code مرة وسجّل دخول، وبعدين جرّب تاني.",
  },
  claudeCodeCheckFailed: { en: "The check did not run. Try again.", ar: "الفحص ماشتغلش. جرّب تاني." },
  useClaudeCode: { en: "Use Claude Code", ar: "استخدم Claude Code" },
  claudeCodeCopy: {
    en: "Claude Code keeps its own copy of each conversation on this computer, outside One's encrypted files.",
    ar: "Claude Code بيحتفظ بنسخة خاصة بيه من كل محادثة على الجهاز ده، برّه ملفات One المتشفّرة.",
  },
  claudeCodeNotSaved: { en: "The change was not saved. Try again.", ar: "التغيير ماتحفظش. جرّب تاني." },
  roles: { en: "Which model does which job", ar: "أنهي نموذج يعمل أنهي شغلانة" },
  roleLead: { en: "Lead QS", ar: "كبير مهندسي الكميات" },
  roleChecker: { en: "Checking QS", ar: "مهندس المراجعة" },
  roleSpecialist: { en: "Specialists", ar: "المهندسين المتخصصين" },
  roleQuick: { en: "Quick answers", ar: "الإجابات السريعة" },
  recommended: { en: "Recommended", ar: "الموصى بيه" },
  noModels: { en: "No models yet. Connect an AI above first.", ar: "لسه مفيش نماذج. وصّل ذكاء اصطناعي من فوق الأول." },
  roleNotSaved: { en: "The choice was not saved. Try again.", ar: "الاختيار ماتحفظش. جرّب تاني." },
  pricePerMillion: {
    en: "{in} USD in, {out} USD out per million tokens",
    ar: "{in} دولار للداخل، {out} دولار للخارج لكل مليون توكن",
  },
  priceSource: { en: "source: {source}", ar: "المصدر: {source}" },
  priceUnknown: { en: "price unknown", ar: "السعر مش معروف" },
  enterPrice: { en: "Enter a model's price", ar: "اكتب سعر نموذج" },
  enterPriceHelp: {
    en: "One does not know these models' prices, so the Spending Cap cannot protect you with them. Type the price from the provider's own page.",
    ar: "One مش عارف سعر النماذج دي، فسقف الصرف مش هيقدر يحميك معاها. اكتب السعر من صفحة المزوّد نفسه.",
  },
  priceModel: { en: "Model", ar: "النموذج" },
  priceIn: { en: "Input, USD per million tokens", ar: "الداخل، دولار لكل مليون توكن" },
  priceOut: { en: "Output, USD per million tokens", ar: "الخارج، دولار لكل مليون توكن" },
  priceNotSaved: { en: "The price was not saved. Try again.", ar: "السعر ماتحفظش. جرّب تاني." },
  caps: { en: "Spending Caps", ar: "سقف الصرف" },
  capsHelp: {
    en: "In USD. One pauses and asks at 80% of a cap, and stops at the cap.",
    ar: "بالدولار. One بيوقف ويسألك عند 80% من السقف، وبيقف خالص عند السقف.",
  },
  capBrief: { en: "Per Brief", ar: "لكل تكليف" },
  capDay: { en: "Per day", ar: "في اليوم" },
  capMonth: { en: "Per month", ar: "في الشهر" },
  budgetAbove: { en: "Show the Brief Budget above", ar: "اعرض ميزانية التكليف لو هتعدّي" },
  capsSaved: { en: "Saved.", ar: "اتحفظ." },
  recommendedAmount: { en: "Recommended: {value} USD", ar: "الموصى بيه: {value} دولار" },
  capsNotSaved: { en: "The caps were not saved. Try again.", ar: "السقف ماتحفظش. جرّب تاني." },
  progressLine: { en: "Progress Line", ar: "سطر التقدم" },
  coordinationRoom: { en: "Coordination Room, {n} messages", ar: "غرفة التنسيق، {n} رسالة" },
  fromTo: { en: "{sender} to {recipient}", ar: "من {sender} لـ{recipient}" },
  steering: { en: "Steering the Brief", ar: "توجيه للتكليف" },
  steerFailed: { en: "The message did not reach the Brief. Try again.", ar: "الرسالة موصلتش للتكليف. جرّب تاني." },
  stopFailed: { en: "The Brief did not stop. Try again.", ar: "التكليف موقفش. جرّب تاني." },
  continueBrief: { en: "This Brief stopped at: {step}. Continue it?", ar: "التكليف ده وقف عند: {step}. نكمّله؟" },
  continue: { en: "Continue", ar: "كمّل" },
  leave: { en: "Leave it", ar: "سيبه" },
  continueFailed: { en: "The Brief did not continue. Try again.", ar: "التكليف مكمّلش. جرّب تاني." },
  generalChat: { en: "General chat", ar: "الشات العام" },
  yes: { en: "Yes", ar: "أيوه" },
  no: { en: "No", ar: "لأ" },
  allowOnce: { en: "Allow once", ar: "اسمح المرة دي" },
  allowBrief: { en: "Allow for this Brief", ar: "اسمح للتكليف ده كله" },
  capContinue: { en: "Continue to the cap", ar: "كمّل لحد السقف" },
  capRaise: { en: "Raise the cap", ar: "ارفع السقف" },
  capReport: { en: "Stop with a report", ar: "اقف بتقرير" },
  dontAllow: { en: "Don't allow", ar: "ماتسمحش" },
  useIt: { en: "Use it", ar: "استخدمه" },
  dontUseIt: { en: "Don't use it", ar: "ماتستخدموش" },
  startBrief: { en: "Start", ar: "ابدأ" },
  dontStart: { en: "Don't start", ar: "ماتبدأش" },
  keepDesk: { en: "Keep the Desk", ar: "احتفظ بالقسم" },
  dontKeep: { en: "Don't keep it", ar: "ماتحتفظش بيه" },
  keepAsIs: { en: "Keep it as it is", ar: "سيبه زي ما هو" },
  sendBackToFix: { en: "No, send it back to be fixed", ar: "لأ، رجّعه يتصلّح" },
  keepForAll: { en: "Keep it for all projects", ar: "احفظه لكل المشاريع" },
  keepTicked: { en: "Keep the ticked rows", ar: "احفظ الصفوف المعلّمة" },
  keepNone: { en: "Don't keep any", ar: "ماتحفظش حاجة" },
  goAhead: { en: "Go ahead", ar: "كمّل" },
  notNow: { en: "Not now", ar: "مش دلوقتي" },
  addConnector: { en: "Add it", ar: "ضيفه" },
  dontAdd: { en: "Don't add it", ar: "ماتضيفوش" },
  yourReply: { en: "Your reply", ar: "ردّك" },
  tickRow: { en: "Keep row {n}", ar: "احفظ الصف {n}" },
  rowsKept: { en: "{n} of {total} rows kept.", ar: "اتحفظ {n} من {total} صف." },
  answered: { en: "Your answer: {choice}", ar: "ردّك: {choice}" },
  withdrawn: { en: "No longer needed.", ar: "مبقاش له لازمة." },
  answerNotSent: { en: "Your answer was not sent. Try again.", ar: "ردّك موصلش. جرّب تاني." },
  codeA: { en: "Code A: approved", ar: "كود A: معتمد" },
  codeB: { en: "Code B: approved with comments", ar: "كود B: معتمد بملاحظات" },
  codeC: { en: "Code C: revise and resubmit", ar: "كود C: يتعدّل ويتقدّم تاني" },
  sameProvider: {
    en: "Same-provider check: the Checking QS runs on the same AI Provider that made this. Add a second AI Provider for a stronger check.",
    ar: "مراجعة من نفس الشركة: مهندس المراجعة شغال على نفس المزوّد اللي عمل الشغل ده. ضيف مزوّد تاني عشان المراجعة تبقى أقوى.",
  },
  noSource: { en: "No source yet", ar: "لسه ملوش مصدر" },
  noSourceNote: { en: "Some numbers have no source yet; they are marked.", ar: "في أرقام لسه ملهاش مصدر؛ متعلّم عليها." },
  equivalentCost: {
    en: "Equivalent cost on your Claude subscription (not billed per use).",
    ar: "تكلفة مكافئة على اشتراك Claude بتاعك (مش بتتحاسب على كل استخدام).",
  },
  projects: { en: "Projects", ar: "المشاريع" },
  projectsLoading: { en: "Loading your projects…", ar: "جارٍ تحميل مشاريعك…" },
  projectsFailed: { en: "The projects could not be loaded. Try again.", ar: "تعذّر تحميل المشاريع. حاول مرة أخرى." },
  noProjects: { en: "No projects yet. Create the first one.", ar: "لا توجد مشاريع بعد. أنشئ أول مشروع." },
  open: { en: "Open", ar: "مفتوح" },
  projectNotOpened: { en: "The project did not open. Try again.", ar: "لم يُفتح المشروع. حاول مرة أخرى." },
  newProject: { en: "New project", ar: "مشروع جديد" },
  projectName: { en: "Project name", ar: "اسم المشروع" },
  create: { en: "Create", ar: "إنشاء" },
  projectNotCreated: { en: "The project was not created. Try again.", ar: "لم يُنشأ المشروع. حاول مرة أخرى." },
  records: { en: "Project Records", ar: "سجلات المشروع" },
  pickProjectFirst: {
    en: "Open a project or create one first.",
    ar: "افتح مشروعًا أو أنشئ مشروعًا جديدًا أولًا.",
  },
  addFiles: { en: "Add files", ar: "إضافة ملفات" },
  dropHere: { en: "Drop PDF and Excel files here.", ar: "أفلت ملفات PDF وExcel هنا." },
  adding: { en: "Adding the files…", ar: "جارٍ إضافة الملفات…" },
  noFiles: { en: "No files yet.", ar: "لا توجد ملفات بعد." },
  filesFailed: { en: "The files could not be loaded. Try again.", ar: "تعذّر تحميل الملفات. حاول مرة أخرى." },
  fileNotAdded: { en: "The file was not added. Try again.", ar: "لم يُضف الملف. حاول مرة أخرى." },
  fileDuplicate: { en: "Already in Project Records.", ar: "موجود بالفعل في سجلات المشروع." },
  fileRead: { en: "Read", ar: "مقروء" },
  filePartlyRead: { en: "Partly read", ar: "مقروء جزئيًا" },
  fileStored: { en: "Kept, not read", ar: "محفوظ دون قراءة" },
  fileUnreadable: { en: "Could not be read", ar: "تعذّرت قراءته" },
  search: { en: "Search", ar: "بحث" },
  searchFailed: { en: "The search did not run. Try again.", ar: "لم يتم البحث. حاول مرة أخرى." },
  noResults: { en: "Nothing found.", ar: "لم يُعثر على شيء." },
  page: { en: "Page {page}", ar: "صفحة {page}" },
  sheetRow: { en: "Sheet {sheet}, row {row}", ar: "ورقة {sheet}، صف {row}" },
  row: { en: "Row {row}", ar: "صف {row}" },
  line: { en: "Line {line}", ar: "سطر {line}" },
  meaningOff: {
    en: "Search by meaning finds the same idea in other words, in Arabic and English. It needs a one-time download of {size} from Hugging Face; then it works without internet.",
    ar: "البحث بالمعنى يجد الفكرة نفسها بكلمات أخرى، بالعربية والإنجليزية. يحتاج إلى تنزيل لمرة واحدة بحجم {size} من Hugging Face، ثم يعمل دون إنترنت.",
  },
  meaningDownload: { en: "Download", ar: "تنزيل" },
  meaningDownloading: {
    en: "Downloading the search model: {done} of {total}",
    ar: "جارٍ تنزيل نموذج البحث: {done} من {total}",
  },
  meaningStop: { en: "Stop", ar: "إيقاف" },
  meaningStopped: { en: "The download stopped at {done} of {total}.", ar: "توقّف التنزيل عند {done} من {total}." },
  meaningResume: { en: "Resume", ar: "استكمال" },
  meaningChecking: { en: "Checking the downloaded files…", ar: "جارٍ فحص الملفات المنزّلة…" },
  meaningRetry: { en: "Try again", ar: "إعادة المحاولة" },
  meaningIndexing: {
    en: "Preparing search by meaning: {done} of {total} parts",
    ar: "جارٍ تجهيز البحث بالمعنى: {done} من {total} جزء",
  },
  meaningPause: { en: "Pause", ar: "إيقاف مؤقت" },
  meaningPaused: { en: "Paused at {done} of {total} parts.", ar: "متوقف مؤقتًا عند {done} من {total} جزء." },
  meaningReady: { en: "Search by meaning is on.", ar: "البحث بالمعنى يعمل." },
  reordering: { en: "Reordering by meaning…", ar: "جارٍ إعادة الترتيب حسب المعنى…" },
  // Plan 6 (Deliverables and review), one group per task: sheet* Task 8, doc* Task 9, the rest
  // Task 10. Arabic in plain Egyptian colloquial, as in core/qsone/copy.py, until the founder picks.
  sheetCollapse: { en: "Fold the section", ar: "اطوي الباب" },
  sheetExpand: { en: "Open the section", ar: "افتح الباب" },
  sheetFrozen: { en: "Fixed column", ar: "عمود ثابت" },
  sheetAccept: { en: "Accept", ar: "اقبل" },
  sheetReject: { en: "Reject", ar: "ارفض" },
  sheetSource: { en: "Source", ar: "المصدر" },
  sheetFormula: { en: "Formula", ar: "المعادلة" },
  sheetInputs: { en: "Inputs", ar: "المدخلات" },
  sheetSteps: { en: "Steps", ar: "الخطوات" },
  sheetDated: { en: "Dated {date}", ar: "بتاريخ {date}" },
  sheetEnteredBy: { en: "Entered by {who}", ar: "أدخله {who}" },
  sheetRecalculated: { en: "Recalculated", ar: "اتحسب تاني" },
  sheetSample: {
    en: "Sample data: these numbers are not real.",
    ar: "بيانات تجريبية: الأرقام دي مش حقيقية.",
  },
  sheetPasteRefused: { en: "Not pasted into {cells}: {why}", ar: "ماتلصقش في {cells}: {why}" },
  sheetAmountComputed: {
    en: "Amounts are computed by the QS Calc Engine from quantity × rate; change the quantity or the rate.",
    ar: "الإجمالي بيحسبه محرك الحسابات من الكمية × الفئة؛ غيّر الكمية أو الفئة.",
  },
  sheetNotEditable: { en: "this column cannot be typed in", ar: "العمود ده مينفعش يتكتب فيه" },
  sheetNotNumber: { en: "this is not a number", ar: "ده مش رقم" },
  sheetNotSent: { en: "The change was not sent. Try again.", ar: "التعديل موصلش. جرّب تاني." },
  sheetNoAnswer: { en: "One's core did not answer. Try again.", ar: "محرك One مردّش. جرّب تاني." },
  sheetPending: { en: "{n} suggested changes", ar: "{n} تعديلات مقترحة" },
  sheetTotal: { en: "Total", ar: "الإجمالي العام" },
  sheetFullScreen: { en: "Full screen", ar: "ملء الشاشة" },
  sheetLeaveFullScreen: { en: "Leave full screen", ar: "اخرج من ملء الشاشة" },
  sheetTheEngineer: { en: "the engineer", ar: "المهندس" },
  sheetBack: { en: "Back", ar: "رجوع" },
  sheetPageOf: { en: "Page {page} of {pages}", ar: "صفحة {page} من {pages}" },
  sheetNextPage: { en: "Next page", ar: "الصفحة الجاية" },
  sheetPreviousPage: { en: "Previous page", ar: "الصفحة اللي فاتت" },
  sheetSourceFailed: { en: "The source could not be loaded. Try again.", ar: "مقدرناش نجيب المصدر. جرّب تاني." },
  docUntraced: { en: "Number with no source", ar: "رقم من غير مصدر" },
  docMoved: {
    en: "Moved: the text it was on has changed.",
    ar: "اتنقلت: النص اللي كانت عليه اتغيّر.",
  },
  docUntracedCount: {
    en: "{n} numbers with no source (dotted underline): they are not linked to Project Records.",
    ar: "{n} أرقام من غير مصدر (تحتها خط منقّط): مش مربوطة بسجلات المشروع.",
  },
  docRefMissing: { en: "This number was not found in Project Records", ar: "الرقم ده مش لاقيينه في سجلات المشروع" },
  docMoveSuggested: { en: "Suggested: move this paragraph", ar: "مقترح: نقل الفقرة دي" },
  docCommitHint: {
    en: "An edit is sent as a suggested change when you leave the paragraph or press Ctrl+Enter.",
    ar: "التعديل بيتبعت كتعديل مقترح لما تسيب الفقرة أو تدوس Ctrl+Enter.",
  },
  reviewChanges: { en: "Suggested changes", ar: "التعديلات المقترحة" },
  reviewAcceptAll: { en: "Accept all", ar: "اقبل الكل" },
  reviewAcceptMine: { en: "Accept all mine", ar: "اقبل كل تعديلاتي" },
  reviewRejectAll: { en: "Reject all", ar: "ارفض الكل" },
  reviewReject: { en: "Reject", ar: "ارفض" },
  reviewStale: { en: "No longer applies", ar: "مبقاش ينفع" },
  reviewRecordsMoved: { en: "Update from Project Records", ar: "تحديث من سجلات المشروع" },
  reviewCorrected: { en: "Corrected: {reason}", ar: "اتصحح: {reason}" },
  reviewFollows: { en: "This also recalculates:", ar: "وده كمان هيتحسب تاني:" },
  reviewYou: { en: "You", ar: "إنت" },
  reviewCalcEngine: { en: "QS Calc Engine", ar: "محرك الحسابات" },
  reviewComments: { en: "Comments", ar: "الملاحظات" },
  reviewNote: { en: "One's note", ar: "ملاحظة One" },
  reviewComment: { en: "Review comment", ar: "ملاحظة مراجعة" },
  reviewAddComment: { en: "Add a comment", ar: "ضيف ملاحظة" },
  reviewReply: { en: "Reply", ar: "رد" },
  reviewClose: { en: "Close", ar: "اقفل" },
  reviewReopen: { en: "Reopen", ar: "افتح تاني" },
  reviewFixIt: { en: "Fix it", ar: "صلّحها" },
  reviewMustFix: { en: "Must fix (Code C)", ar: "لازم تتصلّح (كود C)" },
  reviewOpen: { en: "Open", ar: "مفتوحة" },
  reviewClosed: { en: "Closed", ar: "مقفولة" },
  reviewBlocking: { en: "Blocking (C)", ar: "بتوقف الاعتماد (C)" },
  reviewAll: { en: "All", ar: "الكل" },
  reviewVersions: { en: "Saved versions", ar: "النسخ المحفوظة" },
  reviewVersion: { en: "Version {n}", ar: "نسخة {n}" },
  reviewRevisions: { en: "Revisions", ar: "الإصدارات" },
  reviewRev: { en: "Rev {n}", ar: "إصدار {n}" },
  reviewIssueRevision: { en: "Issue Revision", ar: "طلّع إصدار" },
  reviewCompare: { en: "Compare", ar: "قارن" },
  reviewCloseOut: { en: "Close-out", ar: "قفل الملاحظات" },
  reviewBlockedBecause: { en: "Sign-off is blocked:", ar: "الاعتماد واقف:" },
  reviewSignOff: { en: "Sign off", ar: "اعتمد" },
  reviewSignedOff: { en: "Signed off: Rev {n}", ar: "اتعتمد: إصدار {n}" },
  reviewReport: { en: "Review report", ar: "تقرير المراجعة" },
  exportMenu: { en: "Export", ar: "تصدير" },
  exportExcel: { en: "Excel", ar: "Excel" },
  exportWord: { en: "Word", ar: "Word" },
  exportPdf: { en: "PDF", ar: "PDF" },
  exportClientFile: { en: "Fill the client's file", ar: "املا ملف العميل" },
  exportDraftMark: { en: "Draft — not signed off", ar: "مسودة — غير معتمد" },
  fillPreview: { en: "Fill preview", ar: "معاينة التعبئة" },
  fillCell: { en: "Cell", ar: "الخلية" },
  fillClientText: { en: "In the client's file", ar: "في ملف العميل" },
  fillBefore: { en: "Before", ar: "قبل" },
  fillAfter: { en: "After", ar: "بعد" },
  fillSkippedFormula: {
    en: "Holds the client's formula: left as it is",
    ar: "فيها معادلة العميل: سيبناها زي ما هي",
  },
  fillMismatch: { en: "The item code differs", ar: "كود البند مختلف" },
  fillItIsRight: { en: "It is right", ar: "مظبوط كده" },
  fillMake: { en: "Make the file", ar: "اعمل الملف" },
  statusDraft: { en: "Draft", ar: "مسودة" },
  statusChecked: { en: "Checked: Code {code}", ar: "مُراجَع: كود {code}" },
  statusSignedOff: { en: "Signed off", ar: "معتمد" },
  statusSameProvider: { en: "Same-provider check", ar: "مراجعة من نفس الشركة" },
  statusOffDesk: { en: "Off-Desk", ar: "خارج الأقسام" },
  deliverables: { en: "Project Index", ar: "فهرس المشروع" },
  deliverablesButton: { en: "Deliverables", ar: "المُخرَجات" },
  deliverablesEmpty: { en: "No Deliverables yet.", ar: "لسه مفيش مُخرَجات." },
} satisfies Record<string, Text>;

const storageKey = "qsone.language";
const listeners = new Set<() => void>();
let current: Language = stored() ?? "ar";

function stored(): Language | undefined {
  try {
    const value = localStorage.getItem(storageKey);
    return value === "en" || value === "ar" ? value : undefined;
  } catch {
    return undefined;
  }
}

export function language(): Language {
  return current;
}

export function dir(lang: Language = current): "rtl" | "ltr" {
  return lang === "ar" ? "rtl" : "ltr";
}

export function setLanguage(lang: Language) {
  current = lang;
  document.documentElement.lang = lang;
  document.documentElement.dir = dir(lang);
  try {
    localStorage.setItem(storageKey, lang);
  } catch {
    // private window or blocked storage: the choice lasts for this session only
  }
  for (const listener of listeners) listener();
}

export function pick(text: Text, lang: Language = current): string {
  return text[lang];
}

export function t(key: keyof typeof texts): string {
  return pick(texts[key]);
}

/** Puts values into a text's blanks: fill("Page {page}", { page: 3 }) is "Page 3". */
export function fill(template: string, values: Record<string, string | number | undefined>): string {
  return template.replace(/\{(\w+)\}/g, (_, key: string) => String(values[key]));
}

/** Re-renders the component when the language changes. */
export function useLanguage(): Language {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    language,
  );
}
