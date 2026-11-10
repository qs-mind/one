// The engineer's language. Arabic is the default; the page is right-to-left in Arabic.
import { useSyncExternalStore } from "react";

export type Language = "ar" | "en";
export type Text = { en: string; ar: string };

export const texts = {
  projectMap: {en:"Project Map", ar:"خريطة المشروع"},
  mapEmpty: {en:"No files in this project yet.", ar:"لسه مفيش ملفات في المشروع."},
  mapSummary: {en:"Tender summary", ar:"ملخص المناقصة"},
  mapLinks: {en:"Links", ar:"الروابط"},
  mapUnchecked: {en:"Read by ONE, not checked", ar:"ONE قراها، لسه متراجعتش"},
  mapConfirmed: {en:"Confirmed", ar:"متأكد منها"},
  mapBlank: {en:"Blank in the template", ar:"فاضية في النموذج"},
  mapConflict: {en:"Conflict — choose a value", ar:"فيه تعارض — اختار القيمة"},
  mapConfirm: {en:"Confirm", ar:"تأكيد"},
  mapChoose: {en:"Use this value", ar:"اعتمد القيمة دي"},
  mapMore: {en:"More files", ar:"ملفات أكتر"},
  mapMoreFacts: {en:"More facts", ar:"معلومات أكتر"},
  mapMoreLinks: {en:"More links", ar:"روابط أكتر"},
  mapFailed: {en:"Could not update the Project Map. Try again.", ar:"مقدرناش نحدّث خريطة المشروع. جرّب تاني."},
  mapLoading: {en:"Loading map…", ar:"بنحمّل الخريطة…"},
  mapPages: {en:"{n} pages", ar:"{n} صفحة"},
  mapText: {en:"Text", ar:"نص"},
  mapOcr: {en:"OCR", ar:"قراءة ضوئية"},
  mapMixed: {en:"Text + OCR", ar:"نص وقراءة ضوئية"},
  mapStored: {en:"Not read yet", ar:"لسه متقراش"},

  regionSelect: { en: "Comment on a region", ar: "علّق على منطقة" },
  regionDrag: { en: "Drag a box on the page, then write your comment.", ar: "اسحب مربع على الصفحة، وبعدها اكتب تعليقك." },
  regionUnavailable: { en: "ONE could not locate regions on this page.", ar: "ONE مقدرش يحدد المناطق في الصفحة دي." },
  regionValueMissing: { en: "ONE could not find this number in the page’s text.", ar: "ONE ملقاش الرقم ده في نص الصفحة." },
  packBuild: { en: "Build pack", ar: "كوّن حزمة المناقصة" },
  packBuilding: { en: "Building pack…", ar: "بنكوّن حزمة المناقصة…" },
  packSteps: { en: "Pack steps", ar: "خطوات الحزمة" },
  packEmpty: { en: "Ask the Lead QS to propose the pack steps.", ar: "اطلب من كبير مهندسي الكميات يقترح خطوات الحزمة." },
  packFile: { en: "File pages", ar: "صفحات الملف" },
  packCover: { en: "Cover", ar: "الغلاف" },
  packDivider: { en: "Divider", ar: "فاصل" },
  packStamp: { en: "Stamp", ar: "ختم نصّي" },
  packNumbers: { en: "Page numbers", ar: "ترقيم الصفحات" },
  packSeal: { en: "Free integrity seal", ar: "ختم سلامة مجاني" },
  packSealHelp: { en: "The free seal proves the file was not changed after sealing. It is not a licensed e-signature.", ar: "الختم المجاني بيثبت إن الملف ماتغيرش بعد الختم. ده مش توقيع إلكتروني معتمد." },
  packPreview: { en: "Pack preview — page {n} of {total}", ar: "معاينة الحزمة — صفحة {n} من {total}" },
  packPrevious: { en: "Previous page", ar: "الصفحة اللي قبلها" },
  packNext: { en: "Next page", ar: "الصفحة اللي بعدها" },
  packNeedsSignoff: { en: "Sign-off is required before exporting the pack.", ar: "لازم اعتماد قبل تصدير الحزمة." },
  packTop: { en: "Top", ar: "فوق" },
  packCenter: { en: "Center", ar: "في النص" },
  packBottom: { en: "Bottom", ar: "تحت" },
  message: { en: "Message to the Lead QS", ar: "رسالة إلى كبير مهندسي الكميات" },
  empty: { en: "Ask the Lead QS about your work.", ar: "اسأل كبير مهندسي الكميات عن شغلك." },
  send: { en: "Send", ar: "إرسال" },
  stop: { en: "Stop", ar: "إيقاف" },
  thinking: { en: "Thinking", ar: "بيفكّر" },
  saving: { en: "Saving…", ar: "بنحفظ…" },
  saved: { en: "Saved", ar: "اتحفظ" },
  keyFailed: { en: "The key was not saved. Try again.", ar: "المفتاح ماتحفظش. جرّب تاني." },
  close: { en: "Close", ar: "إغلاق" },
  checking: { en: "Starting…", ar: "بيشتغل…" },
  coreDown: {
    en: "ONE's core is not running, so the chat cannot work. Its log is here:",
    ar: "محرك ONE مش شغّال، فالشات مش هيشتغل. السجل بتاعه هنا:",
  },
  retry: { en: "Retry", ar: "جرّب تاني" },
  coreRestarting: { en: "ONE's engine is restarting…", ar: "محرك ONE بيعيد التشغيل…" },
  coreRestartingLong: { en: "It is taking longer than usual. Its log:", ar: "واخد وقت أطول من العادي. السجل بتاعه:" },
  screenFailed: {
    en: "Something went wrong on this screen. Your work is saved in the project; reload to carry on.",
    ar: "حصلت مشكلة في الشاشة دي. شغلك محفوظ في المشروع؛ حمّلها تاني وكمّل.",
  },
  reload: { en: "Reload", ar: "حمّل تاني" },
  // Plan 4 (agent engine). Arabic in plain Egyptian colloquial, as in core/qsone/copy.py, until the founder picks.
  ai: { en: "AI settings", ar: "إعدادات الذكاء الاصطناعي" },
  aiTitle: { en: "AI settings", ar: "إعدادات الذكاء الاصطناعي" },
  // the action a core text gets where it shows away from its fix (shell/FixAction.tsx), and a check's own retry
  openAiSettings: { en: "Open AI settings", ar: "افتح إعدادات الذكاء الاصطناعي" },
  openBackup: { en: "Open Backup", ar: "افتح النسخة الاحتياطية" },
  tryAgain: { en: "Try again", ar: "جرّب تاني" },
  baseUrl: { en: "Base URL", ar: "رابط الـ API (Base URL)" },
  remove: { en: "Remove", ar: "شيل" },
  onDevice: { en: "on this computer, free", ar: "على الجهاز ده، ببلاش" },
  claudeCode: { en: "Claude Code (Subscription Link)", ar: "Claude Code (ربط الاشتراك)" },
  useClaudeCode: { en: "Use Claude Code", ar: "استخدم Claude Code" },
  roles: { en: "Which model does which job", ar: "أنهي نموذج يعمل أنهي شغلانة" },
  roleLead: { en: "Lead QS", ar: "كبير مهندسي الكميات" },
  roleChecker: { en: "Checking QS", ar: "مهندس المراجعة" },
  recommended: { en: "Recommended", ar: "الموصى بيه" },
  noModels: {
    en: "No models yet. They show here once a connected AI answers.",
    ar: "لسه مفيش نماذج. هتظهر هنا أول ما ذكاء اصطناعي متوصّل يرد.",
  },
  pricePerMillion: { en: "{in} in / {out} out per million tokens", ar: "{in} داخل / {out} خارج لكل مليون توكن" },
  enterPrice: { en: "Enter a model's price", ar: "اكتب سعر نموذج" },
  priceIn: { en: "Input, USD per million tokens", ar: "الداخل، دولار لكل مليون توكن" },
  priceOut: { en: "Output, USD per million tokens", ar: "الخارج، دولار لكل مليون توكن" },
  priceNotSaved: { en: "The price was not saved. Try again.", ar: "السعر ماتحفظش. جرّب تاني." },
  caps: { en: "Spending Caps", ar: "سقف الصرف" },
  capBrief: { en: "Per Brief", ar: "لكل تكليف" },
  capDay: { en: "Per day", ar: "في اليوم" },
  capMonth: { en: "Per month", ar: "في الشهر" },
  budgetAbove: { en: "Show the Brief Budget above", ar: "اعرض ميزانية التكليف لو هتعدّي" },
  recommendedAmount: { en: "Recommended: {value} USD", ar: "الموصى بيه: {value} دولار" },
  capsNotSaved: { en: "The caps were not saved. Try again.", ar: "السقف ماتحفظش. جرّب تاني." },
  fromTo: { en: "{sender} to {recipient}", ar: "من {sender} لـ{recipient}" },
  steering: { en: "Steering the Brief", ar: "توجيه للتكليف" },
  steerFailed: { en: "The message did not reach the Brief. Try again.", ar: "الرسالة موصلتش للتكليف. جرّب تاني." },
  continue: { en: "Continue", ar: "كمّل" },
  leave: { en: "Leave it", ar: "سيبه" },
  yes: { en: "Yes", ar: "أيوه" },
  no: { en: "No", ar: "لأ" },
  allowOnce: { en: "Allow once", ar: "اسمح المرة دي" },
  allowBrief: { en: "Allow for this Brief", ar: "اسمح للتكليف ده كله" },
  capContinue: { en: "Continue to the cap", ar: "كمّل لحد السقف" },
  capRaise: { en: "Raise the cap", ar: "ارفع السقف" },
  capRaiseGo: { en: "Continue with the new caps", ar: "كمّل بالسقف الجديد" },
  capReport: { en: "Stop with a report", ar: "اقف بتقرير" },
  dontAllow: { en: "Don't allow", ar: "ماتسمحش" },
  useIt: { en: "Use it", ar: "استخدمه" },
  dontUseIt: { en: "Don't use it", ar: "ماتستخدموش" },
  enterItsPrice: { en: "Enter its price", ar: "اكتب سعره" },
  setUpSearch: { en: "Set up web search", ar: "اظبط البحث في الويب" },
  useWithoutPrice: { en: "Use it without a price", ar: "استخدمه من غير سعر" },
  useThisPrice: { en: "Use it at this price", ar: "استخدمه بالسعر ده" },
  startBrief: { en: "Start", ar: "ابدأ" },
  dontStart: { en: "Don't start", ar: "ماتبدأش" },
  keepDesk: { en: "Keep the Desk", ar: "احتفظ بالقسم" },
  dontKeep: { en: "Don't keep it", ar: "ماتحتفظش بيه" },
  keepAsIs: { en: "Keep it as it is", ar: "سيبه زي ما هو" },
  sendBackToFix: { en: "No, send it back to be fixed", ar: "لأ، رجّعه يتصلّح" },
  keepForAll: { en: "Keep it for all projects", ar: "احفظه لكل المشاريع" },
  keepTicked: { en: "Keep the ticked rows", ar: "احفظ الصفوف المعلّمة" },
  // a BOQ import's card: each column of the sheet with what it holds (core: tools/boq.py)
  keepColumns: { en: "Import with these columns", ar: "استورد بالأعمدة دي" },
  columnMeaning: { en: "What column {letter} holds", ar: "العمود {letter} فيه إيه" },
  keepNone: { en: "Don't keep any", ar: "ماتحفظش حاجة" },
  goAhead: { en: "Go ahead", ar: "كمّل" },
  notNow: { en: "Not now", ar: "مش دلوقتي" },
  addConnector: { en: "Add it", ar: "ضيفه" },
  dontAdd: { en: "Don't add it", ar: "ماتضيفوش" },
  // Connectors (Plan 5, Task 12): the Settings screen and the card that adds one.
  connectors: { en: "Connectors", ar: "الموصّلات" },
  noConnectors: { en: "No Connectors yet.", ar: "لسه مفيش موصّلات." },
  connectorName: { en: "Name (small English letters, digits and dashes)", ar: "الاسم (حروف إنجليزي صغيرة وأرقام وشرط)" },
  connectorWhere: { en: "Where it runs", ar: "بيشتغل فين" },
  onThisComputer: { en: "On this computer", ar: "على الجهاز ده" },
  overInternet: { en: "Over the internet", ar: "على النت" },
  connectorCommand: { en: "The command that runs it", ar: "الأمر اللي بيشغّله" },
  connectorAddress: { en: "Its address (https://)", ar: "العنوان بتاعه (https://)" },
  connectorToken: {
    en: "Token (optional; kept in this computer's key store)",
    ar: "التوكن (اختياري؛ بيتحفظ في مخزن المفاتيح على الجهاز ده)",
  },
  connectorChecking: { en: "Starting the Connector to see what it can do…", ar: "بنشغّل الموصّل عشان نشوف يقدر يعمل إيه…" },
  connectorNotAdded: { en: "The Connector was not added. Try again.", ar: "الموصّل ماتضافش. جرّب تاني." },
  connectorAdded: { en: "Connector added.", ar: "الموصّل اتضاف." },
  readWithoutAsking: {
    en: "Use its reading tools without asking me",
    ar: "استخدم أدوات القراية بتاعته من غير ما تسألني",
  },
  readWithoutAskingHelp: {
    en: "Only tools it marks as reading only. Once a Brief has read outside text, ONE asks again.",
    ar: "بس الأدوات اللي معلّم عليها إنها للقراية بس. ولما التكليف يقرا نص من برّه، ONE بيسأل تاني.",
  },
  useForSearch: { en: "Use for web search", ar: "استخدمه للبحث في الويب" },
  noSearchTool: { en: "Not for web search", ar: "مش للبحث في الويب" },
  toolReadsOnly: { en: "Reads only", ar: "قراية بس" },
  toolActs: { en: "Can send or change things: asks you every time", ar: "يقدر يبعت أو يغيّر حاجات: بيسألك كل مرة" },
  toolDeletes: { en: "Can delete: asks you every time", ar: "يقدر يمسح: بيسألك كل مرة" },
  toolOpenWorld: { en: "Reaches outside services: asks you every time", ar: "بيوصل لخدمات برّه: بيسألك كل مرة" },
  // Plan 5, Task 14: hidden-text warnings in Project Records, the web search key, and how a source was dated.
  hiddenText: { en: "Hidden text", ar: "نص مخفي" },
  hiddenTextWhy: {
    // core/qsone/copy.py FILE_HIDDEN_TEXT
    en: "This file has hidden text (white, tiny or invisible) or lines that look like orders to an AI. ONE treats them as data only and shows them to you and the Checking QS.",
    ar: "الملف ده فيه نص مخفي (أبيض أو صغير جداً أو مش ظاهر) أو سطور شكلها أوامر لذكاء اصطناعي. ONE بيتعامل معاها كبيانات بس وبيوريها ليك ولمهندس المراجعة.",
  },
  // a file whose hidden content has no line like an order to an AI: said plainly, not as a warning (real walk, 6 Nov)
  hiddenLayout: {
    en: "Hidden sheets/rows (normal in priced BOQs)",
    ar: "فيه شيتات/صفوف مخفية (عادي في المقايسات المسعّرة)",
  },
  hiddenUnseen: {
    en: "Text not shown on the page (white, tiny or off the page)",
    ar: "فيه نص مش ظاهر في الصفحة (أبيض أو صغير جداً أو برّه الصفحة)",
  },
  hiddenNoOrders: {
    en: "ONE reads it as data, like the rest of the file. No line in it looks like an order to an AI.",
    ar: "ONE بيقراه كبيانات زي باقي الملف. مفيش فيه سطر شكله أمر لذكاء اصطناعي.",
  },
  flagsFailed: { en: "The hidden text could not be loaded. Try again.", ar: "مقدرناش نجيب النص المخفي. جرّب تاني." },
  flagWhite: { en: "White text", ar: "نص أبيض" },
  flagTiny: { en: "Tiny text", ar: "نص صغير جداً" },
  flagInvisible: { en: "Invisible text", ar: "نص مش ظاهر" },
  flagOffPage: { en: "Text outside the page", ar: "نص برّه الصفحة" },
  flagHiddenSheet: { en: "A hidden sheet", ar: "ورقة مخفية" },
  flagHiddenRows: { en: "Hidden rows", ar: "صفوف مخفية" },
  flagHiddenColumns: { en: "Hidden columns", ar: "أعمدة مخفية" },
  flagHiddenElement: { en: "A hidden part of the web page", ar: "جزء مخفي من صفحة الويب" },
  flagAiOrder: { en: "Looks like an order to an AI", ar: "شكله أمر لذكاء اصطناعي" },
  flagSheet: { en: "Sheet {sheet}", ar: "ورقة {sheet}" },
  flagSheetRows: { en: "Sheet {sheet}, rows {rows}", ar: "ورقة {sheet}، صفوف {rows}" },
  flagSheetColumns: { en: "Sheet {sheet}, columns {columns}", ar: "ورقة {sheet}، أعمدة {columns}" },
  flagSheetCells: { en: "Sheet {sheet}, cells {cells}", ar: "ورقة {sheet}، خلايا {cells}" },
  flagParagraph: { en: "Paragraph {paragraph}", ar: "فقرة {paragraph}" },
  flagTableRow: { en: "Table {table}, row {row}", ar: "جدول {table}، صف {row}" },
  flagLayer: { en: "Layer {layer}", ar: "طبقة {layer}" },
  searchKey: { en: "Your Brave Search key", ar: "مفتاح Brave Search بتاعك" },
  // core/qsone/copy.py DATED_RECEIVED and DATED_READ: a source with no date of its own
  sourceDatedReceived: { en: "Date received: {date}", ar: "تاريخ الاستلام: {date}" },
  sourceDatedRead: { en: "Date read: {date}", ar: "تاريخ القراية: {date}" },
  tickRow: { en: "Keep row {n}", ar: "احفظ الصف {n}" },
  answered: { en: "Your answer: {choice}", ar: "ردّك: {choice}" },
  withdrawn: { en: "No longer needed.", ar: "مبقاش له لازمة." },
  // A folded card's answer: what the engineer did, not the button's words.
  didAllowOnce: { en: "allowed once", ar: "سمحت المرة دي" },
  didAllowBrief: { en: "allowed for this Brief", ar: "سمحت للتكليف ده كله" },
  didNotAllow: { en: "not allowed", ar: "ماسمحتش" },
  didCapContinue: { en: "went on to the cap", ar: "كمّلت لحد السقف" },
  didCapRaise: { en: "raised the cap", ar: "رفعت السقف" },
  didCapReport: { en: "stopped with a report", ar: "وقفت بتقرير" },
  didUseIt: { en: "used it", ar: "استخدمته" },
  didNotUseIt: { en: "did not use it", ar: "ماستخدمتوش" },
  didStart: { en: "started it", ar: "بدأته" },
  didNotStart: { en: "did not start it", ar: "مابدأتوش" },
  didKeepDesk: { en: "kept the Desk", ar: "احتفظت بالقسم" },
  didNotKeep: { en: "did not keep it", ar: "ماحتفظتش بيه" },
  didKeepAsIs: { en: "kept it as it is", ar: "سبته زي ما هو" },
  didSendBack: { en: "sent it back to be fixed", ar: "رجّعته يتصلّح" },
  didKeepForAll: { en: "kept it for all projects", ar: "حفظته لكل المشاريع" },
  didKeepNone: { en: "kept none", ar: "ماحفظتش حاجة" },
  didGoAhead: { en: "went ahead", ar: "كمّلت" },
  didNotNow: { en: "not now", ar: "قلت مش دلوقتي" },
  didAdd: { en: "added it", ar: "ضفته" },
  didNotAdd: { en: "did not add it", ar: "ماضفتوش" },
  didYes: { en: "yes", ar: "أيوه" },
  didNo: { en: "no", ar: "لأ" },
  noAnswers: { en: "sent with no answers", ar: "بعته من غير ردود" },
  answerNotSent: { en: "Your answer was not sent. Try again.", ar: "ردّك موصلش. جرّب تاني." },
  noSource: { en: "No source yet", ar: "لسه ملوش مصدر" },
  noSourceNote: { en: "Some numbers have no source yet; they are marked.", ar: "في أرقام لسه ملهاش مصدر؛ متعلّم عليها." },
  // A view the Lead QS shows in the chat (decision 16.1): each number's source chip, and a block that failed to draw.
  viewSourceOf: { en: "Where {value} comes from", ar: "{value} جاي منين" },
  viewBlockFailed: { en: "This part of the view could not be shown.", ar: "معرفناش نعرض الجزء ده." },
  projects: { en: "Projects", ar: "المشاريع" },
  open: { en: "Open", ar: "مفتوح" },
  // what another chat's Briefs are doing (shell/chatActivity.ts): the top bar's mark, the projects' rows, the notice
  projectNotOpened: { en: "The project did not open. Try again.", ar: "لم يُفتح المشروع. حاول مرة أخرى." },
  newProject: { en: "New project", ar: "مشروع جديد" },
  checkColumns: { en: "Check the columns", ar: "راجع الأعمدة" },
  hideColumns: { en: "Hide the columns", ar: "اخفي الأعمدة" },
  create: { en: "Create", ar: "إنشاء" },
  projectNotCreated: { en: "The project was not created. Try again.", ar: "لم يُنشأ المشروع. حاول مرة أخرى." },
  records: { en: "Project Records", ar: "سجلات المشروع" },
  pickProjectFirst: {
    en: "Open a project or create one first.",
    ar: "افتح مشروعًا أو أنشئ مشروعًا جديدًا أولًا.",
  },
  addFiles: { en: "Add files", ar: "إضافة ملفات" },
  dropHere: { en: "Drop PDF and Excel files here.", ar: "أفلت ملفات PDF و Excel هنا." },
  adding: { en: "Adding the files…", ar: "بنضيف الملفات…" },
  noFiles: { en: "No files yet.", ar: "لسه مفيش ملفات." },
  // An empty project's Project files: one drop area, nothing else (records/RecordsPanel.tsx EmptyFiles).
  emptyFilesTitle: { en: "Drop the tender files here", ar: "حط ملفات المناقصة هنا" },
  emptyFilesWhat: {
    en: "The BOQ, specs, supplier quotes and drawings, as PDF or Excel. ONE reads them and tells you what it found.",
    ar: "المقايسة والمواصفات وعروض الأسعار والرسومات، PDF أو Excel. ONE هيقرأها ويقولك لقى فيها إيه.",
  },
  chooseFiles: { en: "Choose files", ar: "اختار ملفات" },
  orTenderFolder: { en: "or the whole tender folder", ar: "أو فولدر المناقصة كله" },
  // the project chat before anything is said, while the project has no files
  filesFailed: { en: "The files could not be loaded. Try again.", ar: "مقدرناش نحمّل الملفات. جرّب تاني." },
  fileNotAdded: { en: "The file was not added. Try again.", ar: "الملف ماتضافش. جرّب تاني." },
  fileDuplicate: { en: "Already in Project Records.", ar: "موجود بالفعل في سجلات المشروع." },
  fileRead: { en: "Read", ar: "مقروء" },
  fileAdded: { en: "Added", ar: "اتضاف" },
  filePartlyRead: { en: "Partly read", ar: "مقروء جزئيًا" },
  fileZoomIn: { en: "Zoom in", ar: "كبّر" },
  fileZoomOut: { en: "Zoom out", ar: "صغّر" },
  fileFit: { en: "Fit page", ar: "اعرض الصفحة كلها" },
  fileStored: { en: "Kept, not read", ar: "محفوظ دون قراءة" },
  fileUnreadable: { en: "Could not be read", ar: "مقدرناش نقراه" },
  search: { en: "Search", ar: "بحث" },
  searchFailed: { en: "The search did not run. Try again.", ar: "البحث مااشتغلش. جرّب تاني." },
  noResults: { en: "Nothing found.", ar: "ملقيتش حاجة." },
  page: { en: "Page {page}", ar: "صفحة {page}" },
  sheetRow: { en: "Sheet {sheet}, row {row}", ar: "ورقة {sheet}، صف {row}" },
  fileSheets: { en: "Sheets", ar: "الأوراق" },
  sheetHidden: { en: "hidden", ar: "مخفية" },
  row: { en: "Row {row}", ar: "صف {row}" },
  line: { en: "Line {line}", ar: "سطر {line}" },
  // Search by meaning gets ready by itself (5 Nov 2026): one quiet line, no button.
  meaningPreparing: { en: "Getting search by meaning ready… {percent}", ar: "بيجهّز البحث بالمعنى… {percent}" },
  meaningNotReady: {
    en: "Search by meaning isn't ready; word search works.",
    ar: "البحث بالمعنى مش جاهز، والبحث بالكلمات شغال.",
  },
  // Plan 6 (Deliverables and review), one group per task: sheet* Task 8, doc* Task 9, the rest
  // Task 10. Arabic in plain Egyptian colloquial, as in core/qsone/copy.py, until the founder picks.
  sheetCollapse: { en: "Fold the section", ar: "اطوي الباب" },
  sheetExpand: { en: "Open the section", ar: "افتح الباب" },
  sheetAccept: { en: "Accept", ar: "اقبل" },
  sheetReject: { en: "Reject", ar: "ارفض" },
  sheetSource: { en: "Source", ar: "المصدر" },
  sheetFormula: { en: "Formula", ar: "المعادلة" },
  sheetInputs: { en: "Inputs", ar: "المدخلات" },
  sheetSteps: { en: "Steps", ar: "الخطوات" },
  sheetDated: { en: "Dated {date}", ar: "بتاريخ {date}" },
  sheetEnteredBy: { en: "Recorded by {who}", ar: "سجّله {who}" },
  enteredByYou: { en: "You entered it", ar: "إنت اللي دخّلته" },
  enteredByLead: { en: "Recorded by the Lead QS", ar: "سجّله كبير مهندسي الكميات" },
  enteredByChecker: { en: "Recorded by the Checking QS", ar: "سجّله مهندس المراجعة" },
  enteredByCalc: { en: "Worked out by the QS Calc Engine", ar: "حسبه محرك الحسابات" },
  enteredByPrices: { en: "From QS Mind Prices", ar: "من أسعار كيو إس مايند" },
  sheetRecalculated: { en: "Recalculated", ar: "اتحسب تاني" },
  calculated: { en: "Calculated", ar: "محسوب" },
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
  sheetNoAnswer: { en: "ONE's core did not answer. Try again.", ar: "محرك ONE مردّش. جرّب تاني." },
  sheetTotal: { en: "Grand total", ar: "الإجمالي العام" },
  sheetFullScreen: { en: "Full screen", ar: "ملء الشاشة" },
  sheetLeaveFullScreen: { en: "Leave full screen", ar: "اخرج من ملء الشاشة" },
  sheetPageOf: { en: "Page {page} of {pages}", ar: "صفحة {page} من {pages}" },
  sheetNextPage: { en: "Next page", ar: "الصفحة الجاية" },
  sheetPreviousPage: { en: "Previous page", ar: "الصفحة اللي فاتت" },
  docUntraced: { en: "Number with no source", ar: "رقم من غير مصدر" },
  docMoved: {
    en: "Moved: the text it was on has changed.",
    ar: "اتنقلت: النص اللي كانت عليه اتغيّر.",
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
  reviewStale: { en: "No longer applies", ar: "مبقاش ينفع" },
  reviewRecordsMoved: { en: "Update from Project Records", ar: "تحديث من سجلات المشروع" },
  reviewCorrected: { en: "Corrected: {reason}", ar: "اتصحح: {reason}" },
  reviewFollows: { en: "This also recalculates:", ar: "وده كمان هيتحسب تاني:" },
  reviewYou: { en: "You", ar: "إنت" },
  reviewCalcEngine: { en: "QS Calc Engine", ar: "محرك الحسابات" },
  reviewComments: { en: "Comments", ar: "الملاحظات" },
  reviewNote: { en: "ONE's note", ar: "ملاحظة ONE" },
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
  // a saved version (نسخة) stays in ONE; an issue (إصدار) is what goes to the client: the two never read alike
  reviewVersionsHelp: {
    en: "Each accepted change saves a version. Versions stay in ONE.",
    ar: "كل مرة بتقبل فيها تعديل بتتحفظ نسخة. النسخ بتفضل جوّه ONE.",
  },
  reviewRevisionsHelp: {
    en: "A Revision is what you send to the client: Rev 1, Rev 2 and so on.",
    ar: "الإصدار هو اللي بتبعته للعميل: إصدار 1، إصدار 2، وهكذا.",
  },
  reviewVersionNoChanges: { en: "No changes", ar: "من غير تعديلات" },
  reviewIssueRevision: { en: "Issue Revision", ar: "طلّع إصدار" },
  reviewCompare: { en: "Compare", ar: "قارن" },
  reviewCloseOut: { en: "Sign-off", ar: "الاعتماد" },
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
  fillItIsRight: { en: "It is right", ar: "مظبوط كده" },
  fillMake: { en: "Make the file", ar: "اعمل الملف" },
  statusDraft: { en: "Draft", ar: "مسودة" },
  statusChecked: { en: "Checked: Code {code}", ar: "مُراجَع: كود {code}" },
  statusSignedOff: { en: "Signed off", ar: "معتمد" },
  statusSameProvider: { en: "Same-provider check", ar: "مراجعة من نفس الشركة" },
  statusOffDesk: { en: "Off-Desk", ar: "خارج الأقسام" },
  deliverables: { en: "Project Index", ar: "فهرس المشروع" },
  // Plan 6 Task 10: the review screens, the Project Index and the Deliverable card.
  deliverableSheet: { en: "Sheet", ar: "جدول" },
  deliverableDocument: { en: "Document", ar: "مستند" },
  deliverableOther: { en: "Deliverable", ar: "مُخرَج" },
  deliverableOpen: { en: "Open", ar: "افتح" },
  deliverableType: { en: "Type", ar: "النوع" },
  deliverableTitle: { en: "Title", ar: "العنوان" },
  deliverableStatus: { en: "Status", ar: "الحالة" },
  deliverableNoRevision: { en: "Not sent to the client yet", ar: "لسه ما اتبعتش للعميل" },
  deliverableFailed: { en: "This Deliverable could not be loaded. Try again.", ar: "مقدرناش نجيب المُخرَج ده. جرّب تاني." },
  deliverableNoViewer: { en: "This kind of Deliverable cannot be shown here yet.", ar: "النوع ده من المُخرَجات لسه مينفعش يتعرض هنا." },
  deliverableLoading: { en: "Loading…", ar: "بيحمّل…" },
  reviewPanels: { en: "Review", ar: "المراجعة" },
  reviewNoChanges: { en: "No suggested changes.", ar: "مفيش تعديلات مقترحة." },
  reviewStaleWhy: {
    en: "This cell changed after the change was suggested. Ask ONE again, or edit it yourself.",
    ar: "الخلية دي اتغيرت بعد ما التعديل اتقترح. اطلب من ONE تاني، أو عدّلها بنفسك.",
  },
  reviewAcceptWithUpdate: { en: "Accept with the update", ar: "اقبل مع التحديث" },
  reviewFieldChanged: { en: "Changed in Project Records", ar: "اتغيّر في سجلات المشروع" },
  reviewMore: { en: "Show {n} more", ar: "اعرض {n} كمان" },
  reviewAccepted: { en: "Accepted: version {n} saved.", ar: "اتقبل: اتحفظت نسخة {n}." },
  reviewNothingAccepted: { en: "Nothing was accepted.", ar: "مفيش حاجة اتقبلت." },
  reviewRejected: { en: "Rejected.", ar: "اترفض." },
  reviewOpAddRow: { en: "Add the row {code}", ar: "إضافة البند {code}" },
  reviewOpAddSection: { en: "Add the section «{title}»", ar: "إضافة الباب «{title}»" },
  reviewOpRemoveRow: { en: "Remove", ar: "شيل" },
  reviewOpMoveRow: { en: "Move", ar: "نقل" },
  reviewOpColumns: { en: "Change the columns", ar: "تغيير الأعمدة" },
  reviewOpInsertBlock: { en: "Add a paragraph", ar: "إضافة فقرة" },
  reviewOpRemoveBlock: { en: "Remove a paragraph", ar: "شيل فقرة" },
  reviewOpMoveBlock: { en: "Move a paragraph", ar: "نقل فقرة" },
  placeItem: { en: "Item {code}", ar: "البند {code}" },
  placeItems: { en: "Items {from}–{to}", ar: "البنود {from}–{to}" },
  placeCell: { en: "{place}, {column}", ar: "{place}، {column}" },
  placeWhole: { en: "The whole Deliverable", ar: "المُخرَج كله" },
  placeParagraph: { en: "A paragraph", ar: "فقرة" },
  placeQuote: { en: "“{quote}”", ar: "«{quote}»" },
  placeMoved: { en: "{place} (moved)", ar: "{place} (اتنقلت)" },
  reviewCommentOn: { en: "On: {place}", ar: "على: {place}" },
  reviewCommentAdd: { en: "Add", ar: "ضيف" },
  reviewCommentText: { en: "Your comment", ar: "ملاحظتك" },
  reviewReplyText: { en: "Your reply", ar: "ردّك" },
  reviewNoComments: { en: "No comments.", ar: "مفيش ملاحظات." },
  reviewFixSent: { en: "Sent to the Lead QS.", ar: "اتبعتت لكبير مهندسي الكميات." },
  reviewFilter: { en: "Show", ar: "اعرض" },
  reviewCodeC: { en: "Code C", ar: "كود C" },
  reviewFrom: { en: "From", ar: "من" },
  reviewTo: { en: "To", ar: "إلى" },
  reviewBy: { en: "by {who}", ar: "بواسطة {who}" },
  reviewIssued: { en: "Issued", ar: "صادر" },
  reviewAdded: { en: "Added", ar: "اتضاف" },
  reviewRemoved: { en: "Removed", ar: "اتشال" },
  reviewMovedRow: { en: "Moved", ar: "اتنقل" },
  reviewNoDifference: { en: "No difference.", ar: "مفيش فرق." },
  reviewCanSignOff: { en: "Nothing blocks Sign-off.", ar: "مفيش حاجة واقفة قدام الاعتماد." },
  reviewRevisionIssued: { en: "Rev {n} issued.", ar: "طلع إصدار {n}." },
  exportSaved: { en: "Saved: {name}", ar: "اتحفظ: {name}" },
  exportDownloaded: { en: "Downloaded: {name}", ar: "اتنزّل: {name}" },
  exportCancelled: { en: "Not saved.", ar: "ماتحفظش." },
  exportFailed: { en: "The file was not saved. Try again.", ar: "الملف ماتحفظش. جرّب تاني." },
  fillSkippedMerged: { en: "Inside merged cells: left as it is", ar: "جوه خلايا مدموجة: سيبناها زي ما هي" },
  fillSkipped: { en: "Left as they are", ar: "اتسابت زي ما هي" },
  fillMismatches: { en: "Codes that differ", ar: "أكواد مختلفة" },
  fillOurs: { en: "Ours: {code}", ar: "عندنا: {code}" },
  fillTheirs: { en: "The client's: {code}", ar: "عند العميل: {code}" },
  fillMarkedRight: { en: "Marked right", ar: "اتعلّم إنه مظبوط" },
  fillMismatchesFirst: { en: "Mark each differing code first.", ar: "علّم على كل كود مختلف الأول." },
  fillUnmappedItems: { en: "Not in the client's file: {codes}", ar: "مش في ملف العميل: {codes}" },
  fillNoPlan: { en: "No Fill Plan yet: ask the Lead QS to map the client's file.", ar: "لسه مفيش خطة تعبئة: اطلب من كبير مهندسي الكميات يربط ملف العميل." },
  // Plan 7 (the Project Canvas). Names proposed in glossary.md; never «لوحة» for the canvas (a drawing sheet in QS).
  projectFiles: { en: "Project files", ar: "ملفات المشروع" },
  // The client BOQ as imported: a read-only document.
  clientBoqTitle: { en: "Client BOQ — {name}", ar: "مقايسة العميل — {name}" },
  clientBoqReadOnly: { en: "The client's document: read only", ar: "مستند العميل: للقراءة بس" },
  fileReadOnly: { en: "As the file has it: read only", ar: "زي ما في الملف: للقراءة بس" },
  clientBoqLoading: { en: "Loading the client's BOQ…", ar: "بنحمّل مقايسة العميل…" },
  // The workspace's open document (workspace Task 5)
  noViewer: { en: "No viewer for this kind yet", ar: "لسه مافيش عرض للنوع ده" },
  sourceOpenFile: { en: "Open source", ar: "افتح المصدر" },
  // The source card in the workspace: the quoted line, what the quote covers, and the page opened as the document
  sourceOpenPage: { en: "Open the page", ar: "افتح الصفحة" },
  supplyOnly: { en: "Supply only, no labour", ar: "توريد بس، من غير مصنعية" },
  // A formula's terms in words (ui/src/sources/formula.ts): «الكمية × الفئة», not «quantity * rate»
  termQuantity: { en: "Quantity", ar: "الكمية" },
  termRate: { en: "Rate", ar: "الفئة" },
  termAmount: { en: "Amount", ar: "الإجمالي" },
  termTotal: { en: "Total", ar: "الإجمالي العام" },
  termSum: { en: "sum of {x}", ar: "مجموع {x}" },
  // A number's source, shown (decision 16.3): the card a number opens into.
  sourceBackTo: { en: "Back to {value}", ar: "ارجع لـ {value}" },
  sourceSaidInChat: { en: "Said in the chat", ar: "اتقال في الشات" },
  sourceSupplier: { en: "Supplier: {name}", ar: "المورّد: {name}" },
  sourceOfNumber: { en: "Source of {value}", ar: "مصدر {value}" },
  selected: { en: "Selected: {name}", ar: "المختار: {name}" },
  // the message box's placeholders: one line in the narrowest chat (320 px), in both languages
  // The message box's model and effort, for the Lead QS of the next Brief
  models: { en: "Models", ar: "الموديلات" },
  palette: { en: "Search and commands", ar: "بحث وأوامر" },
  stateWaiting: { en: "Waiting for you", ar: "مستنيك" },
  noNews: { en: "No news for a minute", ar: "مفيش جديد من دقيقة" },
  submission: { en: "Submission {date}, {days} days left", ar: "التسليم {date}، فاضل {days} يوم" },
  sampleData: { en: "Sample data", ar: "بيانات تجريبية" },
  openAsDocument: { en: "Open as a document", ar: "افتح كمستند" },
  pageNotShown: { en: "This page could not be shown.", ar: "مقدرناش نعرض الصفحة دي." },
  // Plan 7 Task 5 (the live team on the canvas)
  // Plan 7 Task 4 (the canvas frames)
  documentFailed: { en: "This document could not be opened. Try again.", ar: "مقدرناش نفتح المستند ده. جرّب تاني." },
  pageScanned: {
    en: "This page is scanned: it has no text ONE could read.",
    ar: "الصفحة دي متصوّرة سكانر: مفيهاش نص ONE يقدر يقراه.",
  },
  drawingAt: { en: "Sheet {sheet}, handle {handle}", ar: "لوحة {sheet}، معرّف {handle}" },
  drawingNoPreview: { en: "A drawing preview is not available yet. The text ONE read is shown below.", ar: "معاينة الرسم لسه مش متاحة. النص اللي ONE قراه ظاهر تحت." },
  fileNoText: { en: "ONE read no text from this file.", ar: "ONE مقراش أي نص من الملف ده." },
  // Plan 7 Task 6 (the shell: top bar, floating chat, command bar, palette, General chat)
  more: { en: "More", ar: "أكتر" },
  // Plan 8, written once here so Tasks 10, 11 and 12 never edit this file. Proposed terms (glossary): Introduction card
  // / بطاقة التعريف, "I understood this" card / بطاقة «فهمت كده», Close project / إقفال المشروع, Archived project / مشروع
  // مؤرشف, Recovery code / كود الاسترجاع, Backup key / مفتاح النسخة الاحتياطية. No text names a plan or a price.
  // Task 10: first launch. Every step has Skip and Back.
  setupAgain: { en: "Setup again", ar: "أول تشغيل" },
  languageTitle: { en: "Choose your language", ar: "اختار لغتك" },
  // the other language is in the top bar's More menu (shell/TopBar.tsx), on every screen of the app
  languageHelp: {
    en: "You can change it any time from “More” in ONE's top bar.",
    ar: "تقدر تغيّرها في أي وقت من «أكتر» في الشريط اللي فوق في ONE.",
  },
  accountWhy: {
    en: "It keeps your Backup key, so a new computer gets your projects back. It is free, and you can skip it.",
    ar: "بيحفظ مفتاح النسخة الاحتياطية بتاعك، فلو غيّرت الجهاز مشاريعك بترجعلك. مجاني، وتقدر تتخطاه.",
  },
  // "QS Mind" in full, as the step's title names the account; QSM alone is not a name the engineer has seen.
  connectAi: { en: "Connect AI", ar: "وصّل الذكاء الاصطناعي" },
  consentTitle: { en: "Where your text goes", ar: "نصك بيروح فين" },
  consentBody: {
    en: "When you ask ONE for something, your words and the parts of your files it needs go to the AI provider you choose. That provider is usually outside your country and works under its own policy. Nothing in a Confidential project is used outside it, and an On-device project uses only models on this computer.",
    ar: "لما تطلب حاجة من ONE، كلامك والأجزاء اللي محتاجها من ملفاتك بتروح لمزوّد الذكاء الاصطناعي اللي إنت بتختاره. المزوّد ده غالبًا برّه بلدك وشغال بسياسته هو. المشروع السري مفيش حاجة منه بتتستخدم برّاه، والمشروع اللي على الجهاز بيستخدم نماذج على الجهاز ده بس.",
  },
  consentNotSaved: { en: "Your answer was not saved. Try again.", ar: "ردك ماتحفظش. جرّب تاني." },
  aiLinkLater: {
    en: "No AI is connected. You can connect it later from “AI settings” in “More”.",
    ar: "مفيش ذكاء اصطناعي متوصّل. تقدر توصّله بعدين من «إعدادات الذكاء الاصطناعي» في «أكتر».",
  },
  usageHelp: {
    en: "Share a few numbers about how ONE is used, so QS Mind can make it better. You can change this any time from “Setup again” in “More”.",
    ar: "شارك شوية أرقام عن استخدامك لـ ONE، عشان QS Mind يحسّنه. تقدر تغيّر ده في أي وقت من «أول تشغيل» في «أكتر».",
  },
  // Task 11: tender folder import and the "I understood this" card.
  folderSelectionFailed: { en: "ONE could not open the folder. Choose it again.", ar: "ONE ماقدرش يفتح المجلد. اختاره تاني." },
  importFollowupFailed: { en: "ONE could not finish the import follow-up. Check Project files for the files already added.", ar: "ONE ماقدرش يكمّل متابعة الإضافة. شوف الملفات اللي اتضافت في ملفات المشروع." },
  importFailed: { en: "Some files were not added. Try again.", ar: "في ملفات ماتضافتش. جرّب تاني." },
  // Task 11: close and archive, Confidential, the recovery code, backup and restore.
  confidential: { en: "Confidential", ar: "سري" },
  restoreTitle: { en: "Restore from a backup", ar: "استرجاع من نسخة احتياطية" },
  restoreNone: { en: "No backups were found in this folder.", ar: "مالقيناش نسخ احتياطية في الفولدر ده." },
  restoreHiddenName: { en: "A project (its name shows once it opens)", ar: "مشروع (اسمه بيظهر لما يتفتح)" },
  restoreNeedsSignIn: { en: "Sign in to restore this one", ar: "سجّل دخولك عشان ترجّع ده" },
  restoreNeedsBackupCode: { en: "Needs your Backup key's recovery code", ar: "محتاج كود الاسترجاع بتاع مفتاح النسخة الاحتياطية" },
  restoreNeedsProjectCode: { en: "Confidential: needs its own recovery code", ar: "سري: محتاج كود الاسترجاع بتاعه" },
  restoreCode: { en: "Recovery code", ar: "كود الاسترجاع" },
  restoreProject: { en: "Restore", ar: "رجّعه" },
  // Task 11, found missing while building the screens.
  // Task 12: the update card.
  updateReady: { en: "ONE {version} is ready", ar: "ONE {version} جاهز" },
  updateNotes: { en: "What changed", ar: "إيه اللي اتغيّر" },
  updateNow: { en: "Update now", ar: "حدّث دلوقتي" },
  updateLater: { en: "Later", ar: "بعدين" },
  updatePreparing: {
    en: "Pausing Briefs and backing up open projects…",
    ar: "بنوقّف التكليفات مؤقتًا وبنعمل نسخة للمشاريع المفتوحة…",
  },
  updateDownloading: { en: "Downloading: {percent}%", ar: "بينزّل: {percent}%" },
  updateInstalling: { en: "Installing… ONE restarts by itself.", ar: "بيتسطّب… ONE هيفتح تاني لوحده." },
  // the same words as the core's UPDATE_FAILED (core/qsone/copy.py): the shell, not the core, says this one
  updateFailed: {
    en: "The update did not install, so ONE is still on this version and your projects are as they were. Try again later.",
    ar: "التحديث ماتسطبش، فـ ONE لسه على النسخة دي ومشاريعك زي ما هي. جرّب تاني بعدين.",
  },
  // Motion, group A: the start screen and the search field.
  startSlogan: { en: "Every number has a source", ar: "كل رقم له مصدر" },
  startEngine: { en: "Starting ONE's engine…", ar: "بيشغّل محرّك ONE…" },
  // The honest work log, approvals that can't be pressed by mistake, Undo instead of "are you sure?".
  holdHintPaid: { en: "Press and hold to go ahead: this costs money.", ar: "اضغط مطوّل عشان تكمّل: ده بيكلّف فلوس." },
  holdHintIrreversible: {
    en: "Press and hold to go ahead: this can't be taken back.",
    ar: "اضغط مطوّل عشان تكمّل: ده مش هينفع يترجع.",
  },
  undo: { en: "Undo", ar: "تراجع" },
  undoDone: { en: "Back as it was.", ar: "رجع زي ما كان." },
  undoFailed: { en: "It was not put back. Add it again if you need it.", ar: "مارجعش. ضيفه تاني لو محتاجه." },
  // The BOQ change review (ui/src/review/ChangesPanel.tsx)
  reviewAcceptedShort: { en: "Accepted", ar: "اتقبل" },
  reviewRejectedShort: { en: "Rejected", ar: "اترفض" },
  changeSource: { en: "Source: {title}", ar: "المصدر: {title}" },
  changeTyped: { en: "Typed in by the engineer", ar: "كتبه المهندس بنفسه" },
  reviewKeys: { en: "J K or ↑ ↓ to move · A accept · R reject", ar: "J K أو ↑ ↓ للتنقل · A اقبل · R ارفض" },
  // The message queue while ONE works (ui/src/shell/MessageQueue.tsx)
  // Calm interaction details: a file frame's page shown as its picture or as its text.
  // Revision comparison.
  compareOpen: { en: "Compare revisions", ar: "قارن النسخ" },
  compareOld: { en: "Old", ar: "القديمة" },
  compareNewer: { en: "New", ar: "الجديدة" },
  compareOverlay: { en: "Overlay", ar: "التراكب" },
  compareLegend: { en: "Red: removed · Green: added", ar: "أحمر: اتحذف · أخضر: اتضاف" },
  compareChoose: { en: "Choose the old PDF", ar: "اختار ملف PDF القديم" },
  compareLoading: { en: "Comparing pages…", ar: "بنقارن الصفحات…" },
  compareFailed: { en: "Could not compare these files.", ar: "مقدرناش نقارن الملفين دول." },
  compareUnchanged: { en: "Unchanged pages", ar: "صفحات ماتغيّرتش" },
  compareUnpairedOld: { en: "Unpaired old pages", ar: "صفحات قديمة من غير مقابل" },
  compareUnpairedNew: { en: "Unpaired new pages", ar: "صفحات جديدة من غير مقابل" },
  compareAdded: { en: "Words added", ar: "كلمات اتضافت" },
  compareRemoved: { en: "Words removed", ar: "كلمات اتحذفت" },
  compareNoChanges: { en: "No changes found in the paired pages.", ar: "ملقيناش تغيير في الصفحات اللي ليها مقابل." },
  compareScope: { en: "Compared from stored text and page images. File dates are upload dates.", ar: "المقارنة من النص المحفوظ وصور الصفحات. تواريخ الملفات هي تواريخ رفعها." },
  compareSheet: { en: "Paired by sheet number", ar: "المطابقة برقم اللوحة" },
  compareTitle: { en: "Paired by title", ar: "المطابقة بالعنوان" },
  compareOrder: { en: "Paired by order — review the match", ar: "المطابقة بالترتيب — راجع إنهم نفس الصفحة" },
  pageView: { en: "Show the page as", ar: "اعرض الصفحة" },
  pageViewImage: { en: "Picture", ar: "صورة" },
  pageViewText: { en: "Text", ar: "نص" },
  // The document's head and switcher.
  fullScreen: { en: "Full screen", ar: "ملء الشاشة" },
  // The engineer's zoom (More, and Ctrl/Cmd with = - 0): over the screen's own scale (ui/scale.ts).
  zoom: { en: "Zoom", ar: "التكبير" },
  zoomIn: { en: "Zoom in", ar: "كبّر" },
  zoomOut: { en: "Zoom out", ar: "صغّر" },
} satisfies Record<string, Text>;

const storageKey = "qsone.language";
const listeners = new Set<() => void>();
let current: Language = stored() ?? "ar";
// Read once, as the page loads and before main.tsx writes the language back: none on the very first launch.
const savedAtLoad = stored();

/** The language an earlier run saved, if any: the start screen speaks it, else the system's. */
export function savedLanguage(): Language | undefined {
  return savedAtLoad;
}

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
  try {
    localStorage.setItem(storageKey, lang);
  } catch {
    // private window or blocked storage: the choice lasts for this session only
  }
  followLanguage(lang);
}

/** Follows the new interface's screen language (ui/src/texts/language.ts), in memory only: nothing new goes in web
 * storage (contract, Phase 1 row 9). */
export function followLanguage(lang: Language) {
  current = lang;
  document.documentElement.lang = lang;
  document.documentElement.dir = dir(lang);
  for (const listener of listeners) listener();
}

/** The text in `lang`. A text that is missing (a row the core sent without one) or has one language only gives what
 * there is, or nothing: a screen never breaks on a missing line. */
export function pick(text: Text | null | undefined, lang: Language = current): string {
  return text?.[lang] ?? text?.en ?? text?.ar ?? "";
}

export function t(key: keyof typeof texts, lang: Language = current): string {
  return pick(texts[key], lang);
}

/** The language of a Brief, the engineer's, from the message that started it (the core's rule, in
 * core/qsone/engine/types.py brief_language): English when it has more Latin letters than Arabic ones, else Arabic. */
export function languageOf(text: string): Language {
  const latin = text.match(/[A-Za-z]/g)?.length ?? 0;
  const arabic = text.match(/[؀-ۿ]/g)?.length ?? 0;
  return latin > arabic ? "en" : "ar";
}

/** Puts values into a text's blanks: fill("Page {page}", { page: 3 }) is "Page 3". A value that ends a sentence
 * itself («…شيت BOQ؟») takes the place of the template's own full stop after it, never «؟.». */
export function fill(template: string, values: Record<string, string | number | undefined>): string {
  return template.replace(/\{(\w+)\}(\.?)/g, (_, key: string, stop: string) => {
    const value = String(values[key]);
    return stop && /[.?!؟…]$/.test(value) ? value : value + stop;
  });
}

type Forms = Partial<Record<Intl.LDMLPluralRule, string>> & { other: string };

/** Texts with a count in them, in each form the language needs: English one/other; Arabic zero, one, two, few (3–10)
 * and other (11 and up, where the noun is singular). count() picks the form. */
export const counted = {
  openComments: {
    en: { one: "{n} open comment", other: "{n} open comments" },
    ar: {
      zero: "مفيش ملاحظات مفتوحة",
      one: "ملاحظة واحدة مفتوحة",
      two: "ملاحظتين مفتوحتين",
      few: "{n} ملاحظات مفتوحة",
      other: "{n} ملاحظة مفتوحة",
    },
  },
  filesForWhichProject: {
    en: { one: "Which project is this file for? Pick one, or make a new one.", other: "Which project are these {n} files for? Pick one, or make a new one." },
    ar: {
      one: "الملف ده لأنهي مشروع؟ اختار واحد، أو اعمل مشروع جديد.",
      two: "الملفين دول لأنهي مشروع؟ اختار واحد، أو اعمل مشروع جديد.",
      few: "الـ{n} ملفات دول لأنهي مشروع؟ اختار واحد، أو اعمل مشروع جديد.",
      other: "الـ{n} ملف دول لأنهي مشروع؟ اختار واحد، أو اعمل مشروع جديد.",
    },
  },
  viewRows: {
    en: { one: "1 row", other: "{n} rows" },
    ar: { zero: "مفيش صفوف", one: "صف واحد", two: "صفين", few: "{n} صفوف", other: "{n} صف" },
  },
  boqItems: {
    en: { one: "{n} item", other: "{n} items" },
    ar: { one: "بند واحد", two: "بندين", few: "{n} بنود", other: "{n} بند" },
  },
  itemsLeft: {
    en: { one: "{n} item left", other: "{n} items left" },
    ar: { one: "فاضل بند واحد", two: "فاضل بندين", few: "فاضل {n} بنود", other: "فاضل {n} بند" },
  },
  // a sheet's foot while items wait for their numbers; texts.sheetTotal once all are priced
  sheetTotalSoFar: {
    en: { one: "Total so far · {done} of {n} item", other: "Total so far · {done} of {n} items" },
    ar: {
      one: "الإجمالي لحد دلوقتي · {done} من بند واحد",
      two: "الإجمالي لحد دلوقتي · {done} من بندين",
      few: "الإجمالي لحد دلوقتي · {done} من {n} بنود",
      other: "الإجمالي لحد دلوقتي · {done} من {n} بند",
    },
  },
  boqItemsOf: {
    en: { one: "{done} of {n} item", other: "{done} of {n} items" },
    ar: { one: "{done} من بند واحد", two: "{done} من بندين", few: "{done} من {n} بنود", other: "{done} من {n} بند" },
  },
  connectorTools: {
    en: { one: "{n} tool", other: "{n} tools" },
    ar: { one: "أداة واحدة", two: "أداتين", few: "{n} أدوات", other: "{n} أداة" },
  },
  sheetPending: {
    en: { one: "{n} suggested change", other: "{n} suggested changes" },
    ar: { one: "تعديل واحد مقترح", two: "تعديلين مقترحين", few: "{n} تعديلات مقترحة", other: "{n} تعديل مقترح" },
  },
  reviewChangesCount: {
    en: { one: "{n} change", other: "{n} changes" },
    ar: { one: "تعديل واحد", two: "تعديلين", few: "{n} تعديلات", other: "{n} تعديل" },
  },
  fillUnmappedRows: {
    en: { one: "{n} row of the client's file is not mapped.", other: "{n} rows of the client's file are not mapped." },
    ar: {
      one: "صف واحد في ملف العميل مش متربط.",
      two: "صفين في ملف العميل مش متربطين.",
      few: "{n} صفوف في ملف العميل مش متربطة.",
      other: "{n} صف في ملف العميل مش متربط.",
    },
  },
  docUntracedCount: {
    en: {
      one: "{n} number with no source (dotted underline): it is not linked to Project Records.",
      other: "{n} numbers with no source (dotted underline): they are not linked to Project Records.",
    },
    ar: {
      one: "رقم واحد من غير مصدر (تحته خط منقّط): مش مربوط بسجلات المشروع.",
      two: "رقمين من غير مصدر (تحتهم خط منقّط): مش مربوطين بسجلات المشروع.",
      few: "{n} أرقام من غير مصدر (تحتها خط منقّط): مش مربوطة بسجلات المشروع.",
      other: "{n} رقم من غير مصدر (تحتهم خط منقّط): مش مربوطين بسجلات المشروع.",
    },
  },
  // a folded rows card's answer, after «ردّك:»: all of them, or {kept} of {n}
  rowsApproved: {
    en: { one: "approved {n} row", other: "approved {n} rows" },
    ar: { one: "وافقت على صف واحد", two: "وافقت على صفين", few: "وافقت على {n} صفوف", other: "وافقت على {n} صف" },
  },
  // a folded BOQ columns card's answer: the columns it imports
  columnsApproved: {
    en: { one: "approved {n} column", other: "approved {n} columns" },
    ar: { one: "وافقت على عمود واحد", two: "وافقت على عمودين", few: "وافقت على {n} أعمدة", other: "وافقت على {n} عمود" },
  },
  rowsApprovedOf: {
    en: { one: "approved {kept} of {n} row", other: "approved {kept} of {n} rows" },
    ar: {
      one: "وافقت على {kept} من صف واحد",
      two: "وافقت على {kept} من صفين",
      few: "وافقت على {kept} من {n} صفوف",
      other: "وافقت على {kept} من {n} صف",
    },
  },
  coordinationRoom: {
    en: { one: "Coordination Room, {n} message", other: "Coordination Room, {n} messages" },
    ar: {
      one: "غرفة التنسيق، رسالة واحدة",
      two: "غرفة التنسيق، رسالتين",
      few: "غرفة التنسيق، {n} رسائل",
      other: "غرفة التنسيق، {n} رسالة",
    },
  },
  deskSummary: {
    en: { other: "{desk}: {n} working" },
    ar: { zero: "{desk}: مفيش حد شغال", one: "{desk}: واحد شغال", two: "{desk}: اتنين شغالين", other: "{desk}: {n} شغالين" },
  },
  // The work log: its steps, and a Brief's whole time in words.
  steps: {
    en: { one: "{n} step", other: "{n} steps" },
    ar: { one: "خطوة واحدة", two: "خطوتين", few: "{n} خطوات", other: "{n} خطوة" },
  },
  seconds: {
    en: { other: "{n}s" },
    ar: { one: "ثانية", two: "ثانيتين", few: "{n} ثواني", other: "{n} ثانية" },
  },
  minutes: {
    en: { other: "{n}m" },
    ar: { one: "دقيقة", two: "دقيقتين", few: "{n} دقايق", other: "{n} دقيقة" },
  },
  hours: {
    en: { other: "{n}h" },
    ar: { one: "ساعة", two: "ساعتين", few: "{n} ساعات", other: "{n} ساعة" },
  },
  moreWaiting: {
    en: { one: "{n} more waiting", other: "{n} more waiting" },
    ar: { one: "واحدة كمان مستنية", two: "اتنين كمان مستنيين", few: "{n} كمان مستنيين", other: "{n} كمان مستنيين" },
  },
  // Close project: cards still waiting for the engineer in the project chat
  closeProjectWaiting: {
    en: { one: "A card waits for you in the chat.", other: "{n} cards wait for you in the chat." },
    ar: {
      one: "فيه كارت مستنيك في المحادثة.",
      two: "فيه كارتين مستنيينك في المحادثة.",
      few: "فيه {n} كروت مستنيينك في المحادثة.",
      other: "فيه {n} كارت مستنيينك في المحادثة.",
    },
  },
  // The workspace's top bar: what waits for the engineer (nothingWaiting when nothing does)
  decisionsWaiting: {
    en: { one: "One decision waiting for you", other: "{n} decisions waiting for you" },
    ar: { one: "مستنيك قرار واحد", two: "مستنيك قرارين", few: "مستنيك {n} قرارات", other: "مستنيك {n} قرار" },
  },
} satisfies Record<string, { en: Forms; ar: Forms }>;

const pluralRules = { en: new Intl.PluralRules("en"), ar: new Intl.PluralRules("ar") };

/** A counted text in the form `n` takes: count("openComments", 1) is «ملاحظة واحدة مفتوحة», with 11 «11 ملاحظة مفتوحة». */
export function count(
  key: keyof typeof counted,
  n: number,
  values: Record<string, string | number> = {},
  lang: Language = current,
): string {
  const forms: Forms = counted[key][lang];
  return fill(forms[pluralRules[lang].select(n)] ?? forms.other, { ...values, n });
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
