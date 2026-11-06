// The engineer's language. Arabic is the default; the page is right-to-left in Arabic.
import { useSyncExternalStore } from "react";

export type Language = "ar" | "en";
export type Text = { en: string; ar: string };

export const texts = {
  appName: { en: "QS Mind ONE", ar: "QS Mind ONE" },
  otherLanguage: { en: "العربية", ar: "English" },
  aiKey: { en: "Claude key", ar: "مفتاح Claude" },
  message: { en: "Message to the Lead QS", ar: "رسالة إلى كبير مهندسي الكميات" },
  empty: { en: "Ask the Lead QS about your work.", ar: "اسأل كبير مهندسي الكميات عن شغلك." },
  send: { en: "Send", ar: "إرسال" },
  stop: { en: "Stop", ar: "إيقاف" },
  thinking: { en: "Thinking", ar: "بيفكّر" },
  chatError: { en: "The reply stopped because of an error. Try again.", ar: "الرد وقف بسبب غلطة. جرّب تاني." },
  aiKeyTitle: { en: "Add your Claude key", ar: "ضيف مفتاح Claude بتاعك" },
  aiKeyHelp: {
    en: "ONE works with your own Claude key from Anthropic. It is kept in this computer's key store.",
    ar: "ONE بيشتغل بمفتاح Claude بتاعك من Anthropic، وبيتحفظ في مخزن المفاتيح على الجهاز ده.",
  },
  aiKeyLabel: { en: "Claude API key", ar: "مفتاح Claude API" },
  saving: { en: "Saving…", ar: "بنحفظ…" },
  saved: { en: "Saved", ar: "اتحفظ" },
  keySaved: { en: "Key saved.", ar: "المفتاح اتحفظ." },
  keyTooShort: {
    en: "This looks too short to be a whole key. Paste all of it.",
    ar: "ده شكله أقصر من مفتاح كامل. الصق المفتاح كله.",
  },
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
  keyStoreFile: {
    en: "This computer has no key store, so ONE keeps your keys in a protected file in its own folder instead.",
    ar: "الجهاز ده مفيهوش مخزن مفاتيح، فـ ONE بيحفظ مفاتيحك في ملف محمي جوه الفولدر بتاعه.",
  },
  standardLink: { en: "Standard Link: other AI Providers", ar: "ربط عام: مزوّدين تانيين" },
  standardLinkHelp: {
    en: "Any provider with an OpenAI-compatible API, such as DeepSeek or Mistral, or a model on this computer, such as Ollama.",
    ar: "أي مزوّد عنده API متوافق مع OpenAI، زي DeepSeek أو Mistral، أو نموذج شغال على الجهاز ده، زي Ollama.",
  },
  providerName: { en: "Name", ar: "الاسم" },
  baseUrl: { en: "Base URL", ar: "رابط الـ API (Base URL)" },
  providerKey: { en: "Key (optional: models on this computer have none)", ar: "المفتاح (اختياري: النماذج اللي على الجهاز ملهاش مفتاح)" },
  providerModel: {
    en: "Model (optional: the one ONE uses first, by its name at the provider)",
    ar: "النموذج (اختياري: اللي ONE هيشتغل بيه الأول، باسمه عند المزوّد)",
  },
  addProvider: { en: "Add provider", ar: "ضيف المزوّد" },
  providerNotAdded: { en: "The provider was not added. Try again.", ar: "المزوّد ماتضافش. جرّب تاني." },
  providerUrlRefused: {
    en: "ONE cannot use this address. It must start with http:// or https://, and a key needs https:// unless the model runs on this computer.",
    ar: "ONE مش هيقدر يستخدم العنوان ده. لازم يبدأ بـ http:// أو https://، ولو في مفتاح لازم https:// إلا لو النموذج شغال على الجهاز ده.",
  },
  remove: { en: "Remove", ar: "شيل" },
  removeFailed: { en: "It was not removed. Try again.", ar: "ماتشالش. جرّب تاني." },
  onDevice: { en: "on this computer, free", ar: "على الجهاز ده، ببلاش" },
  claudeCode: { en: "Claude Code (Subscription Link)", ar: "Claude Code (ربط الاشتراك)" },
  claudeCodeHelp: {
    en: "Use the Claude Code installed on this computer, with your own Claude subscription. ONE never installs it or signs in for you.",
    ar: "استخدم Claude Code اللي متثبّت على الجهاز ده، باشتراك Claude بتاعك. ONE عمره ما هيثبّته ولا هيسجّل دخول بدالك.",
  },
  claudeCodePath: { en: "Its file (leave empty to find it by itself)", ar: "الملف بتاعه (سيبه فاضي وONE هيدوّر عليه)" },
  claudeCodeChecking: { en: "Checking Claude Code…", ar: "بنفحص Claude Code…" },
  claudeCodeReady: { en: "Claude Code {version} is ready.", ar: "Claude Code {version} جاهز." },
  claudeCodeMissing: {
    en: "Claude Code was not found on this computer. Install it from https://code.claude.com/docs/en/setup, or pick its file.",
    ar: "Claude Code مش موجود على الجهاز ده. نزّله من https://code.claude.com/docs/en/setup، أو اختار الملف بتاعه.",
  },
  claudeCodeTooOld: {
    en: "Your Claude Code lacks options ONE needs. Update it to the newest version, then try again.",
    ar: "Claude Code اللي عندك ناقصه اختيارات ONE محتاجها. حدّثه لآخر نسخة، وبعدين جرّب تاني.",
  },
  claudeCodeShim: {
    en: "This is the npm claude.cmd, which ONE cannot run safely. Install the native Claude Code, then pick it.",
    ar: "ده claude.cmd بتاع npm، وONE مش هيقدر يشغّله بأمان. نزّل Claude Code الأصلي وبعدين اختاره.",
  },
  claudeCodeSignedOut: {
    en: "Claude Code is signed out. Sign in to it once in a terminal, then try again.",
    ar: "Claude Code مش مسجّل دخول. سجّل دخولك فيه مرة من الـ terminal، وبعدين جرّب تاني.",
  },
  claudeCodeCheckFailed: { en: "The check did not run. Try again.", ar: "الفحص ماشتغلش. جرّب تاني." },
  useClaudeCode: { en: "Use Claude Code", ar: "استخدم Claude Code" },
  claudeCodeCopy: {
    en: "Claude Code keeps its own copy of each conversation on this computer, outside ONE's encrypted files.",
    ar: "Claude Code بيحتفظ بنسخة خاصة بيه من كل محادثة على الجهاز ده، برّه ملفات ONE المتشفّرة.",
  },
  claudeCodeNotSaved: { en: "The change was not saved. Try again.", ar: "التغيير ماتحفظش. جرّب تاني." },
  roles: { en: "Which model does which job", ar: "أنهي نموذج يعمل أنهي شغلانة" },
  roleLead: { en: "Lead QS", ar: "كبير مهندسي الكميات" },
  roleChecker: { en: "Checking QS", ar: "مهندس المراجعة" },
  roleSpecialist: { en: "Specialists", ar: "المهندسين المتخصصين" },
  roleQuick: { en: "Quick answers", ar: "الإجابات السريعة" },
  recommended: { en: "Recommended", ar: "الموصى بيه" },
  noModels: {
    en: "No models yet. They show here once a connected AI answers.",
    ar: "لسه مفيش نماذج. هتظهر هنا أول ما ذكاء اصطناعي متوصّل يرد.",
  },
  roleNotSaved: { en: "The choice was not saved. Try again.", ar: "الاختيار ماتحفظش. جرّب تاني." },
  pricePerMillion: {
    en: "{in} USD in, {out} USD out per million tokens",
    ar: "{in} دولار للداخل، {out} دولار للخارج لكل مليون توكن",
  },
  priceSource: { en: "source: {source}", ar: "المصدر: {source}" },
  priceUnknown: { en: "price unknown", ar: "السعر مش معروف" },
  enterPrice: { en: "Enter a model's price", ar: "اكتب سعر نموذج" },
  enterPriceHelp: {
    en: "ONE does not know these models' prices, so the Spending Cap cannot protect you with them. Type the price from the provider's own page.",
    ar: "ONE مش عارف سعر النماذج دي، فسقف الصرف مش هيقدر يحميك معاها. اكتب السعر من صفحة المزوّد نفسه.",
  },
  priceModel: { en: "Model", ar: "النموذج" },
  priceIn: { en: "Input, USD per million tokens", ar: "الداخل، دولار لكل مليون توكن" },
  priceOut: { en: "Output, USD per million tokens", ar: "الخارج، دولار لكل مليون توكن" },
  priceNotSaved: { en: "The price was not saved. Try again.", ar: "السعر ماتحفظش. جرّب تاني." },
  caps: { en: "Spending Caps", ar: "سقف الصرف" },
  capsHelp: {
    en: "In USD. ONE pauses and asks at 80% of a cap, and stops at the cap.",
    ar: "بالدولار. ONE بيوقف ويسألك عند 80% من السقف، وبيقف خالص عند السقف.",
  },
  capBrief: { en: "Per Brief", ar: "لكل تكليف" },
  capDay: { en: "Per day", ar: "في اليوم" },
  capMonth: { en: "Per month", ar: "في الشهر" },
  budgetAbove: { en: "Show the Brief Budget above", ar: "اعرض ميزانية التكليف لو هتعدّي" },
  recommendedAmount: { en: "Recommended: {value} USD", ar: "الموصى بيه: {value} دولار" },
  capsNotSaved: { en: "The caps were not saved. Try again.", ar: "السقف ماتحفظش. جرّب تاني." },
  progressLine: { en: "Progress Line", ar: "سطر التقدم" },
  fromTo: { en: "{sender} to {recipient}", ar: "من {sender} لـ{recipient}" },
  steering: { en: "Steering the Brief", ar: "توجيه للتكليف" },
  steerFailed: { en: "The message did not reach the Brief. Try again.", ar: "الرسالة موصلتش للتكليف. جرّب تاني." },
  stopFailed: { en: "The Brief did not stop. Try again.", ar: "التكليف موقفش. جرّب تاني." },
  continueBriefLine: { en: "This Brief stopped at: {step}", ar: "التكليف ده وقف عند: {step}" },
  continue: { en: "Continue", ar: "كمّل" },
  leave: { en: "Leave it", ar: "سيبه" },
  continueFailed: { en: "The Brief did not continue. Try again.", ar: "التكليف مكمّلش. جرّب تاني." },
  leaveFailed: { en: "The Brief was not left. Try again.", ar: "التكليف ماتقفلش. جرّب تاني." },
  generalChat: { en: "General chat", ar: "الشات العام" },
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
  connectorsHelp: {
    en: "A Connector lets ONE use another program or service, such as your email or your company's systems, through MCP. Anything that sends, changes or deletes something outside ONE asks you every time.",
    ar: "الموصّل بيخلّي ONE يستخدم برنامج أو خدمة تانية، زي الإيميل أو أنظمة شركتك، عن طريق MCP. أي حاجة بتبعت أو بتغيّر أو بتمسح حاجة برّه ONE بتسألك كل مرة.",
  },
  connectorsLoading: { en: "Loading the Connectors…", ar: "بنحمّل الموصّلات…" },
  connectorsFailed: { en: "The Connectors could not be loaded. Try again.", ar: "مقدرناش نجيب الموصّلات. جرّب تاني." },
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
  connectorTokenEnv: {
    en: "The environment variable it reads the token from (optional)",
    ar: "متغيّر البيئة اللي بيقرا منه التوكن (اختياري)",
  },
  connectorAdd: { en: "Add Connector", ar: "ضيف الموصّل" },
  connectorChecking: { en: "Starting the Connector to see what it can do…", ar: "بنشغّل الموصّل عشان نشوف يقدر يعمل إيه…" },
  connectorNotAdded: { en: "The Connector was not added. Try again.", ar: "الموصّل ماتضافش. جرّب تاني." },
  connectorAdded: { en: "Connector added.", ar: "الموصّل اتضاف." },
  connectorTokenKept: { en: "Token kept", ar: "التوكن محفوظ" },
  connectorSwitchedOn: { en: "Switched on", ar: "شغّال" },
  connectorNotSaved: { en: "The change was not saved. Try again.", ar: "التغيير ماتحفظش. جرّب تاني." },
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
  searchTitle: { en: "Web search", ar: "البحث في الويب" },
  searchKey: { en: "Your Brave Search key", ar: "مفتاح Brave Search بتاعك" },
  searchKeyHelp: {
    en: "ONE can search the web with your own Brave Search key. It is kept in this computer's key store and is never shown again.",
    ar: "ONE يقدر يدوّر في الويب بمفتاح Brave Search بتاعك. بيتحفظ في مخزن المفاتيح على الجهاز ده، ومش بيظهر تاني.",
  },
  searchKeyKept: { en: "A key is kept. A new one replaces it.", ar: "في مفتاح محفوظ. لو حطّيت واحد جديد هياخد مكانه." },
  searchProvider: { en: "Search in use:", ar: "البحث المستخدم:" },
  searchByBrave: { en: "Brave Search, with your key", ar: "Brave Search، بمفتاحك" },
  searchByNative: { en: "Your AI's own search (Claude)", ar: "البحث بتاع الذكاء الاصطناعي نفسه (Claude)" },
  searchByConnector: { en: "A search Connector", ar: "موصّل بحث" },
  searchByNone: {
    en: "None yet. Add a search key here, connect an AI that can search (Claude), or add a search Connector.",
    ar: "لسه مفيش. ضيف مفتاح بحث هنا، أو وصّل ذكاء اصطناعي بيعرف يدوّر (Claude)، أو ضيف موصّل بحث.",
  },
  searchFailedToLoad: { en: "Which search is in use could not be loaded.", ar: "مقدرناش نعرف أي بحث مستخدم دلوقتي." },
  // core/qsone/copy.py DATED_RECEIVED and DATED_READ: a source with no date of its own
  sourceDatedReceived: { en: "Date received: {date}", ar: "تاريخ الاستلام: {date}" },
  sourceDatedRead: { en: "Date read: {date}", ar: "تاريخ القراية: {date}" },
  yourReply: { en: "Your reply", ar: "ردّك" },
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
  codeA: { en: "Code A: approved", ar: "كود A: معتمد" },
  codeB: { en: "Code B: approved with comments", ar: "كود B: معتمد بملاحظات" },
  codeC: { en: "Code C: revise and resubmit", ar: "كود C: يتعدّل ويتقدّم تاني" },
  sameProvider: {
    en: "Same-provider check: the Checking QS runs on the same AI Provider that made this. Add a second AI Provider for a stronger check.",
    ar: "مراجعة من نفس الشركة: مهندس المراجعة شغال على نفس المزوّد اللي عمل الشغل ده. ضيف مزوّد تاني عشان المراجعة تبقى أقوى.",
  },
  noSource: { en: "No source yet", ar: "لسه ملوش مصدر" },
  noSourceNote: { en: "Some numbers have no source yet; they are marked.", ar: "في أرقام لسه ملهاش مصدر؛ متعلّم عليها." },
  // A view the Lead QS shows in the chat (decision 16.1): each number's source chip, and a block that failed to draw.
  viewSourceOf: { en: "Where {value} comes from", ar: "{value} جاي منين" },
  viewBlockFailed: { en: "This part of the view could not be shown.", ar: "معرفناش نعرض الجزء ده." },
  equivalentCost: {
    en: "Equivalent cost on your Claude subscription (not billed per use).",
    ar: "تكلفة مكافئة على اشتراك Claude بتاعك (مش بتتحاسب على كل استخدام).",
  },
  projects: { en: "Projects", ar: "المشاريع" },
  projectsLoading: { en: "Loading your projects…", ar: "جارٍ تحميل مشاريعك…" },
  projectsFailed: { en: "The projects could not be loaded. Try again.", ar: "تعذّر تحميل المشاريع. حاول مرة أخرى." },
  open: { en: "Open", ar: "مفتوح" },
  findProject: { en: "Find a project", ar: "دوّر على مشروع" },
  noProjectMatch: { en: "No project by that name.", ar: "مفيش مشروع بالاسم ده." },
  // what another chat's Briefs are doing (shell/chatActivity.ts): the top bar's mark, the projects' rows, the notice
  activityWorking: { en: "Working", ar: "شغال" },
  activityWaiting: { en: "Waiting for you", ar: "مستنيك" },
  activityFailed: { en: "Failed", ar: "اتعطل" },
  activityDone: { en: "Done", ar: "خلص" },
  activityElsewhere: { en: "Another chat: {state}", ar: "شات تاني: {state}" },
  activityNoticeDone: { en: "Work finished in “{name}”", ar: "خلص الشغل في «{name}»" },
  activityNoticeFailed: { en: "Work stopped on an error in “{name}”", ar: "الشغل اتعطل في «{name}»" },
  activityNoticeWaiting: { en: "“{name}” is waiting for you", ar: "«{name}» مستنيك" },
  activityOpen: { en: "Open", ar: "افتح" },
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
  emptyProject: {
    en: "Start with the tender files and I'll tell you where to begin. Or ask me anything.",
    ar: "ابدأ بملفات المناقصة، وأنا هقولك هنبدأ منين. أو اسألني أي حاجة.",
  },
  filesFailed: { en: "The files could not be loaded. Try again.", ar: "مقدرناش نحمّل الملفات. جرّب تاني." },
  fileNotAdded: { en: "The file was not added. Try again.", ar: "الملف ماتضافش. جرّب تاني." },
  fileDuplicate: { en: "Already in Project Records.", ar: "موجود بالفعل في سجلات المشروع." },
  fileRead: { en: "Read", ar: "مقروء" },
  fileAdded: { en: "Added", ar: "اتضاف" },
  filePartlyRead: { en: "Partly read", ar: "مقروء جزئيًا" },
  fileStored: { en: "Kept, not read", ar: "محفوظ دون قراءة" },
  fileUnreadable: { en: "Could not be read", ar: "مقدرناش نقراه" },
  search: { en: "Search", ar: "بحث" },
  searchFailed: { en: "The search did not run. Try again.", ar: "البحث مااشتغلش. جرّب تاني." },
  noResults: { en: "Nothing found.", ar: "ملقيتش حاجة." },
  page: { en: "Page {page}", ar: "صفحة {page}" },
  sheetRow: { en: "Sheet {sheet}, row {row}", ar: "ورقة {sheet}، صف {row}" },
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
  sheetFrozen: { en: "Fixed column", ar: "عمود ثابت" },
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
  sheetNotSent: { en: "The change was not sent. Try again.", ar: "التعديل موصلش. جرّب تاني." },
  sheetNoAnswer: { en: "ONE's core did not answer. Try again.", ar: "محرك ONE مردّش. جرّب تاني." },
  sheetTotal: { en: "Grand total", ar: "الإجمالي العام" },
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
  commandBar: { en: "Command bar", ar: "شريط الأوامر" },
  topBar: { en: "Top bar", ar: "الشريط العلوي" },
  projectFiles: { en: "Project files", ar: "ملفات المشروع" },
  // The client BOQ as imported: a read-only document.
  clientBoqTitle: { en: "Client BOQ — {name}", ar: "مقايسة العميل — {name}" },
  clientBoqReadOnly: { en: "The client's document: read only", ar: "مستند العميل: للقراءة بس" },
  clientBoqLoading: { en: "Loading the client's BOQ…", ar: "بنحمّل مقايسة العميل…" },
  // The workspace's open document (workspace Task 5)
  noViewer: { en: "No viewer for this kind yet", ar: "لسه مافيش عرض للنوع ده" },
  sourceOpenFile: { en: "Open source", ar: "افتح المصدر" },
  // The source card in the workspace: the quoted line, what the quote covers, and the page opened as the document
  sourceOpenPage: { en: "Open the page", ar: "افتح الصفحة" },
  supplyOnly: { en: "Supply only, no labour", ar: "توريد بس، من غير مصنعية" },
  sourceNotMarked: {
    en: "The file is open, but the number's exact place in it couldn't be shown, so nothing is marked.",
    ar: "الملف اتفتح، بس مكان الرقم بالظبط فيه مظهرش، فمفيش حاجة متعلّمة.",
  },
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
  selectedMany: { en: "{n} selected", ar: "{n} مختارين" },
  selectedRange: { en: "{title}, {label}", ar: "{title}، {label}" },
  clearSelection: { en: "Clear the selection", ar: "شيل الاختيار" },
  // the message box's placeholders: one line in the narrowest chat (320 px), in both languages
  commandBox: { en: "Ask about the selection", ar: "اطلب حاجة في اللي اخترته" },
  commandBoxEmpty: { en: "Ask the Lead QS", ar: "اطلب من كبير مهندسي الكميات" },
  // The message box's model and effort, for the Lead QS of the next Brief
  modelChip: { en: "Model: {name}. Choose another", ar: "الموديل: {name}. اختار موديل تاني" },
  models: { en: "Models", ar: "الموديلات" },
  effortChip: { en: "Effort: {level}. Click for {next}", ar: "عمق التفكير: {level}. دوس عشان يبقى {next}" },
  effortAutoHelp: { en: "the model's own", ar: "اللي الموديل بيختاره" },
  effortauto: { en: "Auto", ar: "تلقائي" },
  effortlow: { en: "Low", ar: "خفيف" },
  effortmedium: { en: "Medium", ar: "متوسط" },
  efforthigh: { en: "High", ar: "عميق" },
  projectChat: { en: "Project chat", ar: "شات المشروع" },
  openChat: { en: "Open the chat", ar: "افتح الشات" },
  closeChat: { en: "Close the chat", ar: "اقفل الشات" },
  palette: { en: "Search and commands", ar: "بحث وأوامر" },
  stateIdle: { en: "Idle", ar: "فاضي" },
  stateThinking: { en: "Thinking", ar: "بيفكّر" },
  stateWorking: { en: "Working", ar: "شغال" },
  stateWaiting: { en: "Waiting for you", ar: "مستنيك" },
  stateDone: { en: "Done", ar: "خلّص" },
  stateFailed: { en: "Stopped by an error", ar: "وقف بسبب خطأ" },
  noNews: { en: "No news for a minute", ar: "مفيش جديد من دقيقة" },
  submission: { en: "Submission {date}, {days} days left", ar: "التسليم {date}، فاضل {days} يوم" },
  boqSoFar: { en: "BOQ so far", ar: "المقايسة لحد دلوقتي" },
  sampleData: { en: "Sample data", ar: "بيانات تجريبية" },
  continueInProject: { en: "Continue in «{name}»", ar: "كمّل في «{name}»" },
  createProjectNamed: { en: "Create the project «{name}»", ar: "اعمل مشروع «{name}»" },
  pageNotShown: { en: "This page could not be shown.", ar: "مقدرناش نعرض الصفحة دي." },
  // Plan 7 Task 5 (the live team on the canvas)
  agentOn: { en: "On «{title}»", ar: "على «{title}»" },
  agentOnAt: { en: "On «{title}», {place}", ar: "على «{title}»، {place}" },
  anchorRow: { en: "item {row}", ar: "البند {row}" },
  anchorPage: { en: "page {page}", ar: "صفحة {page}" },
  stopRole: { en: "Stop the Brief {role} is on", ar: "وقّف التكليف اللي {role} شغال عليه" },
  announceWorking: { en: "{role} is working", ar: "{role} شغال" },
  announceWaiting: { en: "{role} is waiting for you", ar: "{role} مستنيك" },
  announceDone: { en: "{role} is done", ar: "{role} خلّص" },
  announceFailed: { en: "{role} stopped with an error", ar: "{role} وقف بسبب خطأ" },
  announceNoNews: { en: "No news from {role} for a minute", ar: "مفيش جديد من {role} من دقيقة" },
  // Plan 7 Task 4 (the canvas frames)
  documentFailed: { en: "This document could not be opened. Try again.", ar: "مقدرناش نفتح المستند ده. جرّب تاني." },
  projectTeam: { en: "Project team", ar: "فريق المشروع" },
  showPageText: { en: "Show the page's text", ar: "اعرض نص الصفحة" },
  showPageImage: { en: "Show the page", ar: "اعرض الصفحة" },
  pageScanned: {
    en: "This page is scanned: it has no text ONE could read.",
    ar: "الصفحة دي متصوّرة سكانر: مفيهاش نص ONE يقدر يقراه.",
  },
  fileNoText: { en: "ONE read no text from this file.", ar: "ONE مقراش أي نص من الملف ده." },
  // Plan 7 Task 6 (the shell: top bar, floating chat, command bar, palette, General chat)
  searchKeys: { en: "Search {keys}", ar: "بحث {keys}" },
  more: { en: "More", ar: "أكتر" },
  chatWidth: { en: "Chat width", ar: "عرض الشات" },
  actionCheck: { en: "Check this", ar: "راجع ده" },
  actionSources: { en: "Explain the sources", ar: "اشرح المصادر" },
  actionAskFile: { en: "Ask about this file", ar: "اسأل عن الملف ده" },
  actionSaveDesk: { en: "Save this Desk", ar: "احفظ القسم ده" },
  actionWhatDoing: { en: "What are you doing?", ar: "بتعمل إيه دلوقتي؟" },
  handOffAbout: { en: "This is about «{name}». Continue there?", ar: "ده بخصوص «{name}». نكمّل هناك؟" },
  noProjectYet: { en: "No project for this yet.", ar: "لسه مفيش مشروع للموضوع ده." },
  boqFrom: { en: "From «{title}»", ar: "من «{title}»" },
  notIssued: { en: "No Revision issued yet", ar: "لسه مطلعش إصدار" },
  paletteSearch: { en: "Search documents, commands and Project Records", ar: "دوّر في المستندات والأوامر وسجلات المشروع" },
  paletteSearchGeneral: { en: "Search commands and projects", ar: "دوّر في الأوامر والمشاريع" },
  paletteCommands: { en: "Commands", ar: "الأوامر" },
  paletteRecords: { en: "In Project Records", ar: "في سجلات المشروع" },
  newBelow: { en: "New below ↓", ar: "جديد تحت ↓" },
  moreStatus: { en: "More status", ar: "باقي الحالة" },
  // Plan 8, written once here so Tasks 10, 11 and 12 never edit this file. Proposed terms (glossary): Introduction card
  // / بطاقة التعريف, "I understood this" card / بطاقة «فهمت كده», Close project / إقفال المشروع, Archived project / مشروع
  // مؤرشف, Recovery code / كود الاسترجاع, Backup key / مفتاح النسخة الاحتياطية. No text names a plan or a price.
  // Task 10: first launch. Every step has Skip and Back.
  setupTitle: { en: "Set up ONE", ar: "جهّز ONE" },
  setupStepOf: { en: "Step {n} of {total}", ar: "خطوة {n} من {total}" },
  setupSkip: { en: "Skip", ar: "تخطّى" },
  setupBack: { en: "Back", ar: "رجوع" },
  setupNext: { en: "Next", ar: "التالي" },
  setupAgain: { en: "Setup again", ar: "أول تشغيل" },
  setupAgainHelp: { en: "Go through the first steps again.", ar: "امشي على خطوات البداية تاني." },
  setupNotSaved: { en: "This step was not saved. Try again.", ar: "الخطوة دي ماتحفظتش. جرّب تاني." },
  languageTitle: { en: "Choose your language", ar: "اختار لغتك" },
  // the other language is in the top bar's More menu (shell/TopBar.tsx), on every screen of the app
  languageHelp: {
    en: "You can change it any time from “More” in ONE's top bar.",
    ar: "تقدر تغيّرها في أي وقت من «أكتر» في الشريط اللي فوق في ONE.",
  },
  languageArabic: { en: "العربية", ar: "العربية" },
  languageEnglish: { en: "English", ar: "English" },
  accountTitle: { en: "Your QS Mind account", ar: "حساب QS Mind بتاعك" },
  accountWhy: {
    en: "It keeps your Backup key, so a new computer gets your projects back. It is free, and you can skip it.",
    ar: "بيحفظ مفتاح النسخة الاحتياطية بتاعك، فلو غيّرت الجهاز مشاريعك بترجعلك. مجاني، وتقدر تتخطاه.",
  },
  // "QS Mind" in full, as the step's title names the account; QSM alone is not a name the engineer has seen.
  accountSignIn: { en: "Sign in with QS Mind", ar: "سجّل دخولك بحساب QS Mind" },
  accountSignInHow: {
    en: "Your browser opens. Already signed in to QS Mind there? It goes straight through. If not, you sign in with Google.",
    ar: "المتصفح هيفتح. لو إنت داخل على QS Mind فيه، هيكمّل على طول. لو لأ، هتسجّل دخولك بـ Google.",
  },
  accountOpening: { en: "Opening the sign-in…", ar: "بنفتح صفحة الدخول…" },
  accountWaiting: { en: "Finish signing in in your browser…", ar: "كمّل تسجيل الدخول في المتصفح…" },
  accountNoBrowser: { en: "If no browser opened, open this link:", ar: "لو المتصفح مافتحش، افتح اللينك ده:" },
  accountElsewhere: {
    en: "The browser opened on the computer running ONE. Not in front of it? Cancel, then use “Sign in on another device”.",
    ar: "المتصفح اتفتح على الكمبيوتر اللي شغّال عليه ONE. مش قدامه؟ دوس «إلغاء» واستخدم «سجّل دخولك من جهاز تاني».",
  },
  accountDevice: {
    en: "On your phone or any computer, open {uri} and type this code:",
    ar: "من موبايلك أو أي كمبيوتر، افتح {uri} واكتب الكود ده:",
  },
  accountDeviceWaiting: {
    en: "Waiting for you to sign in there. ONE carries on here by itself.",
    ar: "مستنيينك تدخل هناك. ONE هيكمّل هنا لوحده.",
  },
  accountUseDevice: { en: "Sign in on another device", ar: "سجّل دخولك من جهاز تاني" },
  accountSignedInAs: { en: "Signed in as {email}", ar: "داخل بحساب {email}" },
  accountCancel: { en: "Cancel", ar: "إلغاء" },
  accountSignOut: { en: "Sign out", ar: "سجّل خروج" },
  accountFailed: { en: "Sign-in did not finish. Try again.", ar: "تسجيل الدخول ماكملش. جرّب تاني." },
  connectAi: { en: "Connect AI", ar: "وصّل الذكاء الاصطناعي" },
  consentNeeded: {
    en: "Before ONE uses AI, say yes to the note on where your text goes.",
    ar: "قبل ما ONE يستخدم الذكاء الاصطناعي، وافق على الملاحظة اللي بتوضح نصك بيروح فين.",
  },
  consentTitle: { en: "Where your text goes", ar: "نصك بيروح فين" },
  consentBody: {
    en: "When you ask ONE for something, your words and the parts of your files it needs go to the AI provider you choose. That provider is usually outside your country and works under its own policy. Nothing in a Confidential project is used outside it, and an On-device project uses only models on this computer.",
    ar: "لما تطلب حاجة من ONE، كلامك والأجزاء اللي محتاجها من ملفاتك بتروح لمزوّد الذكاء الاصطناعي اللي إنت بتختاره. المزوّد ده غالبًا برّه بلدك وشغال بسياسته هو. المشروع السري مفيش حاجة منه بتتستخدم برّاه، والمشروع اللي على الجهاز بيستخدم نماذج على الجهاز ده بس.",
  },
  consentTerms: { en: "Terms of use", ar: "شروط الاستخدام" },
  consentPrivacy: { en: "Privacy policy", ar: "سياسة الخصوصية" },
  consentAgree: { en: "I understand", ar: "فهمت" },
  consentGiven: { en: "You said yes to this note.", ar: "وافقت على الملاحظة دي." },
  consentNotSaved: { en: "Your answer was not saved. Try again.", ar: "ردك ماتحفظش. جرّب تاني." },
  aiLinkTitle: { en: "How should ONE reach AI?", ar: "ONE يوصل للذكاء الاصطناعي إزاي؟" },
  aiLinkAfterConsent: { en: "Read the note above first.", ar: "اقرا الملاحظة اللي فوق الأول." },
  aiLinkClaudeCode: { en: "Claude Code", ar: "Claude Code" },
  aiLinkClaudeCodeHelp: {
    en: "Your own Claude subscription, through Claude Code on this computer.",
    ar: "اشتراك Claude بتاعك، عن طريق Claude Code اللي على الجهاز ده.",
  },
  aiLinkClaudeCodeFound: { en: "Found: Claude Code {version}", ar: "لقيناه: Claude Code {version}" },
  aiLinkClaudeCodeMissing: {
    en: "Claude Code is not on this computer yet. Install it from claude.com/claude-code, sign in to it once in a terminal, then try again.",
    ar: "Claude Code لسه مش على الجهاز ده. نزّله من claude.com/claude-code، وسجّل دخولك فيه مرة من الـ terminal، وبعدين جرّب تاني.",
  },
  aiLinkApiKey: { en: "An API key", ar: "مفتاح API" },
  aiLinkApiKeyHelp: {
    en: "A Claude key from Anthropic: you pay Anthropic for what you use.",
    ar: "مفتاح Claude من Anthropic: بتدفع لـ Anthropic على قد استخدامك.",
  },
  aiLinkStandard: { en: "Another AI provider", ar: "مزوّد ذكاء اصطناعي تاني" },
  aiLinkStandardHelp: {
    en: "Any provider with an OpenAI-compatible address and key: Gemini, DeepSeek, or a model on this computer.",
    ar: "أي مزوّد عنده عنوان متوافق مع OpenAI ومفتاح: Gemini أو DeepSeek أو نموذج على الجهاز ده.",
  },
  aiLinkChecking: { en: "Checking…", ar: "بنتأكد…" },
  aiLinkWorks: { en: "It works. ONE is connected to AI.", ar: "شغال. ONE اتوصّل بالذكاء الاصطناعي." },
  aiLinkLater: {
    en: "No AI is connected. You can connect it later from “AI settings” in “More”.",
    ar: "مفيش ذكاء اصطناعي متوصّل. تقدر توصّله بعدين من «إعدادات الذكاء الاصطناعي» في «أكتر».",
  },
  cardTitle: { en: "Introduction card", ar: "بطاقة التعريف" },
  cardHelp: {
    en: "The Lead QS reads one line of it, so its work fits you. It is kept in your Engineer Records on this computer.",
    ar: "كبير مهندسي الكميات بيقرا منها سطر واحد عشان شغله يناسبك. بتتحفظ في سجلات المهندس بتاعتك على الجهاز ده.",
  },
  cardRole: { en: "Your role", ar: "دورك" },
  cardRoleContractor: { en: "QS at a contractor", ar: "مهندس كميات عند مقاول" },
  cardRoleConsultant: { en: "QS at a consultant", ar: "مهندس كميات عند استشاري" },
  cardRoleOwner: { en: "QS for an owner or developer", ar: "مهندس كميات عند مالك أو مطوّر" },
  cardRoleProcurement: { en: "Procurement", ar: "مشتريات" },
  cardCountry: { en: "Country", ar: "البلد" },
  cardCountryEG: { en: "Egypt", ar: "مصر" },
  cardCountrySA: { en: "Saudi Arabia", ar: "السعودية" },
  cardCountryAE: { en: "United Arab Emirates", ar: "الإمارات" },
  cardCountryOther: { en: "Other", ar: "بلد تاني" },
  cardCity: { en: "City", ar: "المدينة" },
  cardSaving: { en: "Saving the card…", ar: "بنحفظ البطاقة…" },
  cardNotSavedRetry: { en: "The card was not saved. Try again.", ar: "البطاقة ماتحفظتش. جرّب تاني." },
  usageTitle: { en: "Usage Stats", ar: "إحصائيات الاستخدام" },
  usageHelp: {
    en: "Share a few numbers about how ONE is used, so QS Mind can make it better. You can change this any time from “Setup again” in “More”.",
    ar: "شارك شوية أرقام عن استخدامك لـ ONE، عشان QS Mind يحسّنه. تقدر تغيّر ده في أي وقت من «أول تشغيل» في «أكتر».",
  },
  usageSentTitle: { en: "What is sent", ar: "اللي بيتبعت" },
  usageSent: {
    en: "Crash reports (the kind of error and where in ONE's code it happened), and counts: Briefs finished, Desks used, AI cost and time, files added, backups made.",
    ar: "تقارير الأعطال (نوع الخطأ ومكانه في كود ONE)، وأعداد: التكليفات اللي خلصت، والأقسام اللي اتستخدمت، وتكلفة ووقت الذكاء الاصطناعي، والملفات اللي اتضافت، والنسخ الاحتياطية اللي اتعملت.",
  },
  usageNeverTitle: { en: "What is never sent", ar: "اللي عمره ما بيتبعت" },
  usageNever: {
    en: "Project names, file names, what your files say, chat text, numbers from your work, client names, Desk names.",
    ar: "أسامي المشاريع، أسامي الملفات، محتوى ملفاتك، كلام الشات، الأرقام اللي في شغلك، أسامي العملاء، أسامي الأقسام.",
  },
  usageShare: { en: "Share", ar: "شارك" },
  usageDontShare: { en: "Don't share", ar: "ماتشاركش" },
  usageSkipMeans: { en: "Skip means don't share.", ar: "التخطي معناه ماتشاركش." },
  readyTitle: { en: "ONE is ready", ar: "ONE جاهز" },
  readyDrop: { en: "Drag your tender folder here", ar: "اسحب فولدر المناقصة هنا" },
  readyChooseFolder: { en: "Choose folder", ar: "اختار فولدر" },
  readyImportOld: { en: "Import old work", ar: "استورد شغل قديم" },
  readyImportOldHelp: {
    en: "Each folder becomes an archived project you can search.",
    ar: "كل فولدر هيبقى مشروع مؤرشف تقدر تدوّر فيه.",
  },
  readyLater: { en: "Start without a folder", ar: "ابدأ من غير فولدر" },
  readyStart: { en: "Start", ar: "ابدأ" },
  readyRolePrice: { en: "${in}/${out} per million tokens", ar: "${in}/${out} لكل مليون توكن" },
  readyRolesChange: { en: "Change the models", ar: "غيّر النماذج" },
  // Task 11: tender folder import and the "I understood this" card.
  windowDropProject: { en: "Drop to add to this project", ar: "سيبهم هنا يتضافوا للمشروع ده" },
  windowDropGeneral: { en: "Drop a tender folder, or files to pick their project", ar: "سيب فولدر المناقصة، أو ملفات وتختار مشروعها" },
  importChoose: { en: "Choose folder", ar: "اختار فولدر" },
  importNewProject: { en: "New project «{name}»", ar: "مشروع جديد «{name}»" },
  importUploading: { en: "Adding files: {done} of {total}", ar: "بنضيف الملفات: {done} من {total}" },
  importReportTitle: { en: "What came in", ar: "اللي اتضاف" },
  importAdded: { en: "Added: {n}", ar: "اتضاف: {n}" },
  importDuplicates: { en: "Already there (the same file): {n}", ar: "موجود قبل كده (نفس الملف): {n}" },
  importNotRead: { en: "Kept, not read yet: {n}", ar: "اتحفظ ولسه ماتقراش: {n}" },
  importTooBig: { en: "Too big to add:", ar: "أكبر من إنه يتضاف:" },
  importUnreadable: { en: "Could not be read:", ar: "مقدرناش نقراه:" },
  importLocked: {
    en: "Locked with a password: save an open copy (without the password) and add that one:",
    ar: "مقفول بباسورد: احفظ نسخة مفتوحة (من غير الباسورد) وضيفها:",
  },
  importEmpty: { en: "Read, but its sheets are empty:", ar: "اتقرا، بس الشيتات بتاعته فاضية:" },
  importZips: { en: "Zips opened: {n}", ar: "ملفات مضغوطة اتفتحت: {n}" },
  importFailed: { en: "Some files were not added. Try again.", ar: "في ملفات ماتضافتش. جرّب تاني." },
  importUnderstanding: { en: "The Lead QS is reading the folder…", ar: "كبير مهندسي الكميات بيقرا الفولدر…" },
  importUnderstoodWaits: {
    en: "Read. The «I understood this» card waits for you in the chat.",
    ar: "اتقرا. كارت «فهمت كده» مستنيك في المحادثة.",
  },
  importUnderstoodDone: { en: "Read.", ar: "اتقرا." },
  importMissed: { en: "What did not come in", ar: "اللي ماتضافش" },
  importOldArchived: {
    en: "Added and archived, without the AI step.",
    ar: "اتضاف واتأرشف، من غير خطوة الذكاء الاصطناعي.",
  },
  importUnderstandIt: { en: "Understand it", ar: "افهمه" },
  understoodTitle: { en: "I understood this", ar: "فهمت كده" },
  understoodHelp: {
    en: "Check each fact against its source. Change anything that is wrong, then approve.",
    ar: "راجع كل معلومة على مصدرها. غيّر أي حاجة غلط، وبعدين اعتمد.",
  },
  understoodClient: { en: "Client", ar: "العميل" },
  understoodSubmissionDate: { en: "Submission date", ar: "ميعاد التقديم" },
  understoodContractType: { en: "Contract type", ar: "نوع العقد" },
  understoodItemsCount: { en: "BOQ items", ar: "بنود المقايسة" },
  understoodMissing: { en: "Missing documents", ar: "مستندات ناقصة" },
  understoodNotFound: { en: "Not found in the files", ar: "مش موجود في الملفات" },
  understoodFiles: { en: "How the files were sorted", ar: "الملفات اتقسمت إزاي" },
  understoodChange: { en: "Change", ar: "غيّر" },
  understoodApprove: { en: "Approve", ar: "اعتمد" },
  understoodApproved: { en: "Approved.", ar: "اتعتمد." },
  understoodNotSaved: { en: "Your changes were not saved. Try again.", ar: "تعديلاتك ماتحفظتش. جرّب تاني." },
  factSourcePage: { en: "{file}, page {page}", ar: "{file}، صفحة {page}" },
  factSourceRow: { en: "{file}, {sheet}, row {row}", ar: "{file}، {sheet}، صف {row}" },
  factSourceFile: { en: "{file}", ar: "{file}" },
  factSourceEngineer: { en: "You, {date}", ar: "إنت، {date}" },
  factSourceCount: { en: "Counted by ONE", ar: "ONE عدّها" },
  // Task 11: close and archive, Confidential, the recovery code, backup and restore.
  closeProject: { en: "Close project", ar: "إقفال المشروع" },
  closeProjectTitle: { en: "Close «{name}»", ar: "إقفال «{name}»" },
  closeProjectHelp: {
    en: "Nothing here stops you: it lists what is still open.",
    ar: "مفيش حاجة هنا بتمنعك: دي قايمة باللي لسه مفتوح.",
  },
  closeProjectOpenComments: { en: "Review comments still open: {n}", ar: "ملاحظات مراجعة لسه مفتوحة: {n}" },
  closeProjectUnsigned: { en: "Not signed off:", ar: "لسه ماتعتمدش:" },
  closeProjectBlockers: {
    en: "These Deliverables are not ready to go out. Fix them first, or archive anyway.",
    ar: "المُخرَجات دي لسه مش جاهزة تطلع. ظبّطها الأول، أو أرشف برضه.",
  },
  closeProjectBroken: { en: "Not right yet:", ar: "لسه فيها مشكلة:" },
  closeProjectReports: { en: "Review reports", ar: "تقارير المراجعة" },
  closeProjectAllClear: { en: "Nothing is open.", ar: "مفيش حاجة مفتوحة." },
  lessonsTitle: { en: "Lessons Learned", ar: "الدروس المستفادة" },
  lessonsHelp: {
    en: "Carry a lesson to your Engineer Records to use it in every project, or keep it in this project.",
    ar: "انقل الدرس لسجلات المهندس عشان يتستخدم في كل المشاريع، أو سيبه في المشروع ده.",
  },
  lessonsFinding: { en: "The Lead QS is picking lessons…", ar: "كبير مهندسي الكميات بيختار الدروس…" },
  lessonsNone: { en: "No lessons to carry.", ar: "مفيش دروس تتنقل." },
  lessonsAsk: {
    en: "The Lead QS can look back over the project for lessons worth keeping. It uses AI.",
    ar: "كبير مهندسي الكميات يقدر يراجع المشروع ويطلّع الدروس اللي تستاهل تتحفظ. ده بيستخدم الذكاء الاصطناعي.",
  },
  lessonsFind: { en: "Find lessons", ar: "طلّع الدروس" },
  lessonsConfidential: {
    en: "This project is Confidential, so its lessons stay in it.",
    ar: "المشروع ده سري، فدروسه بتفضل فيه.",
  },
  lessonCarry: { en: "Carry", ar: "انقله" },
  lessonKeep: { en: "Keep in project", ar: "سيبه في المشروع" },
  lessonCarried: { en: "Carried to Engineer Records.", ar: "اتنقل لسجلات المهندس." },
  archiveProject: { en: "Archive", ar: "أرشف" },
  archiveAnyway: { en: "Archive anyway", ar: "أرشف برضه" },
  archiveWorking: { en: "Making a final backup, then archiving…", ar: "بنعمل آخر نسخة احتياطية، وبعدين بنأرشف…" },
  archivedReadOnly: { en: "Archived, read-only", ar: "مؤرشف، للقراءة بس" },
  archivedGroup: { en: "Archived", ar: "المؤرشفة" },
  unarchiveProject: { en: "Unarchive", ar: "لغي الأرشفة" },
  archivedChatLine: { en: "This project is archived, so it is read-only.", ar: "المشروع ده متأرشف، فهو للقراءة بس." },
  unarchiveFailed: { en: "The project was not unarchived. Try again.", ar: "الأرشفة ماتلغتش. جرّب تاني." },
  archiveFailed: { en: "The project was not archived. Try again.", ar: "المشروع ماتأرشفش. جرّب تاني." },
  confidential: { en: "Confidential", ar: "سري" },
  confidentialHelp: {
    en: "Nothing in a Confidential project is used outside it. Its key is kept with its own recovery code, never with QS Mind.",
    ar: "المشروع السري مفيش حاجة منه بتتستخدم برّاه. مفتاحه بيتحفظ بكود استرجاع خاص بيه، وعمره ما بيروح لـ QS Mind.",
  },
  confidentialTurnOn: { en: "Make Confidential", ar: "خلّيه سري" },
  confidentialTurnOff: { en: "Stop Confidential", ar: "شيل السرية" },
  confidentialOffConfirm: {
    en: "Stop Confidential? Its lessons may then be used in your other projects, and its key will be kept with your Backup key.",
    ar: "تشيل السرية؟ ساعتها دروسه ممكن تتستخدم في مشاريعك التانية، ومفتاحه هيتحفظ مع مفتاح النسخة الاحتياطية.",
  },
  confidentialFailed: { en: "This was not changed. Try again.", ar: "ده ماتغيّرش. جرّب تاني." },
  recoveryTitle: { en: "Your recovery code", ar: "كود الاسترجاع بتاعك" },
  recoveryShownOnce: {
    en: "It is shown only once. Write it down or keep it somewhere safe: without it, this backup cannot be opened on another computer.",
    ar: "بيظهر مرة واحدة بس. اكتبه أو احفظه في مكان أمان: من غيره، النسخة دي مش هتتفتح على جهاز تاني.",
  },
  recoveryCopy: { en: "Copy", ar: "انسخ" },
  recoveryCopied: { en: "Copied.", ar: "اتنسخ." },
  recoverySaved: { en: "I saved it", ar: "حفظته" },
  recoveryLastGroup: { en: "To confirm, type its last group of five", ar: "عشان تأكد، اكتب آخر مجموعة من الخمسة" },
  recoveryConfirmed: { en: "Saved.", ar: "اتحفظ." },
  backupTitle: { en: "Backup", ar: "النسخة الاحتياطية" },
  backupFolder: { en: "Backup folder", ar: "فولدر النسخة الاحتياطية" },
  backupPickFolder: { en: "Pick a folder", ar: "اختار فولدر" },
  backupFolderPath: { en: "Folder path", ar: "مسار الفولدر" },
  backupNoFolder: {
    en: "No folder picked yet. ONE keeps 3 copies on this computer only.",
    ar: "لسه مااخترتش فولدر. ONE بيحتفظ بـ 3 نسخ على الجهاز ده بس.",
  },
  backupAskFolder: { en: "Where should ONE keep backups of your projects?", ar: "ONE يحفظ النسخ الاحتياطية لمشاريعك فين؟" },
  backupLater: { en: "Later", ar: "بعدين" },
  backupLast: { en: "Last backup: {date}", ar: "آخر نسخة: {date}" },
  backupNever: { en: "Not backed up yet", ar: "لسه مااتعملتش نسخة" },
  backupNow: { en: "Back up now", ar: "اعمل نسخة دلوقتي" },
  backupRunning: { en: "Backing up…", ar: "بنعمل نسخة…" },
  backupDone: { en: "Backed up: {n}", ar: "اتعمل نسخة: {n}" },
  backupNotSaved: { en: "This was not saved. Try again.", ar: "ده ماتحفظش. جرّب تاني." },
  backupKeyTitle: { en: "Backup key", ar: "مفتاح النسخة الاحتياطية" },
  backupKeyLocal: { en: "On this computer", ar: "على الجهاز ده" },
  backupKeyInAccount: { en: "In your QS Mind account", ar: "في حساب QS Mind بتاعك" },
  backupKeyCodeSaved: { en: "Recovery code saved", ar: "كود الاسترجاع محفوظ" },
  backupKeyNoAccount: {
    en: "Without an account, a recovery code is the only way to restore your backups on another computer.",
    ar: "من غير حساب، كود الاسترجاع هو الطريقة الوحيدة ترجّع بيها نسخك الاحتياطية على جهاز تاني.",
  },
  backupKeyMakeCode: { en: "Make a recovery code", ar: "اعمل كود استرجاع" },
  restoreTitle: { en: "Restore from a backup", ar: "استرجاع من نسخة احتياطية" },
  restorePickFolder: { en: "Pick the backup folder", ar: "اختار فولدر النسخة الاحتياطية" },
  restoreFound: { en: "Projects found", ar: "المشاريع اللي لقيناها" },
  restoreNone: { en: "No backups were found in this folder.", ar: "مالقيناش نسخ احتياطية في الفولدر ده." },
  restoreHiddenName: { en: "A project (its name shows once it opens)", ar: "مشروع (اسمه بيظهر لما يتفتح)" },
  restoreNeedsSignIn: { en: "Sign in to restore this one", ar: "سجّل دخولك عشان ترجّع ده" },
  restoreNeedsBackupCode: { en: "Needs your Backup key's recovery code", ar: "محتاج كود الاسترجاع بتاع مفتاح النسخة الاحتياطية" },
  restoreNeedsProjectCode: { en: "Confidential: needs its own recovery code", ar: "سري: محتاج كود الاسترجاع بتاعه" },
  restoreCode: { en: "Recovery code", ar: "كود الاسترجاع" },
  restoreProject: { en: "Restore", ar: "رجّعه" },
  restoreDone: { en: "«{name}» is back.", ar: "«{name}» رجع." },
  restoreFailed: { en: "It was not restored. Try again.", ar: "مارجعش. جرّب تاني." },
  // Task 11, found missing while building the screens.
  importMenu: { en: "Import a tender folder", ar: "استورد فولدر مناقصة" },
  importIntoProject: { en: "Adding «{name}» to this project", ar: "بنضيف «{name}» للمشروع ده" },
  lessonsNotStarted: { en: "The Lead QS did not start on the lessons. Try again.", ar: "كبير مهندسي الكميات مابدأش في الدروس. جرّب تاني." },
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
  searchField: { en: "Search", ar: "بحث" },
  // The honest work log, approvals that can't be pressed by mistake, Undo instead of "are you sure?".
  workedFor: { en: "Worked for {time} · {steps}", ar: "اشتغل {time} · {steps}" },
  workedForOnly: { en: "Worked for {time}", ar: "اشتغل {time}" },
  underASecond: { en: "under a second", ar: "أقل من ثانية" },
  workSteps: { en: "Steps", ar: "الخطوات" },
  durationAnd: { en: "{a} {b}", ar: "{a} و{b}" },
  tickSeconds: { en: "{s} s", ar: "{s} ث" },
  tickMinutes: { en: "{m}m {s}s", ar: "{m} د {s} ث" },
  holdHintPaid: { en: "Press and hold to go ahead: this costs money.", ar: "اضغط مطوّل عشان تكمّل: ده بيكلّف فلوس." },
  holdHintIrreversible: {
    en: "Press and hold to go ahead: this can't be taken back.",
    ar: "اضغط مطوّل عشان تكمّل: ده مش هينفع يترجع.",
  },
  undo: { en: "Undo", ar: "تراجع" },
  undoDone: { en: "Back as it was.", ar: "رجع زي ما كان." },
  removedName: { en: "Removed «{name}»", ar: "اتشال «{name}»" },
  addedName: { en: "Added «{name}»", ar: "اتضاف «{name}»" },
  undoFailed: { en: "It was not put back. Add it again if you need it.", ar: "مارجعش. ضيفه تاني لو محتاجه." },
  // The BOQ change review (ui/src/review/ChangesPanel.tsx)
  reviewAcceptedShort: { en: "Accepted", ar: "اتقبل" },
  reviewRejectedShort: { en: "Rejected", ar: "اترفض" },
  changeSource: { en: "Source: {title}", ar: "المصدر: {title}" },
  changeTyped: { en: "Typed in by the engineer", ar: "كتبه المهندس بنفسه" },
  reviewKeys: { en: "J K or ↑ ↓ to move · A accept · R reject", ar: "J K أو ↑ ↓ للتنقل · A اقبل · R ارفض" },
  // The message queue while ONE works (ui/src/shell/MessageQueue.tsx)
  queueLabel: { en: "Queued messages", ar: "رسايل في الطابور" },
  queueCount: { en: "Queued: {n}", ar: "في الطابور: {n}" },
  queueAdd: { en: "Add to the queue", ar: "ضيفها للطابور" },
  queueRemove: { en: "Remove from the queue: {text}", ar: "شيلها من الطابور: {text}" },
  queueEdit: { en: "Edit: {text}", ar: "عدّل: {text}" },
  queueEditField: { en: "Queued message", ar: "رسالة في الطابور" },
  queueResume: { en: "Carry on with the queue", ar: "كمّل الطابور" },
  queueHint: { en: "{keys} interrupts ONE", ar: "{keys} يقاطع ONE" },
  // Calm interaction details: a file frame's page shown as its picture or as its text.
  pageView: { en: "Show the page as", ar: "اعرض الصفحة" },
  pageViewImage: { en: "Picture", ar: "صورة" },
  pageViewText: { en: "Text", ar: "نص" },
  // The document's head and switcher.
  docRevision: { en: "Revision {n}", ar: "إصدار {n}" },
  fullScreen: { en: "Full screen", ar: "ملء الشاشة" },
  leaveFullScreen: { en: "Leave full screen", ar: "اخرج من ملء الشاشة" },
  // The engineer's zoom (More, and Ctrl/Cmd with = - 0): over the screen's own scale (ui/scale.ts).
  zoom: { en: "Zoom", ar: "التكبير" },
  zoomReset: { en: "Reset zoom", ar: "رجّع الحجم" },
  zoomIn: { en: "Zoom in", ar: "كبّر" },
  zoomOut: { en: "Zoom out", ar: "صغّر" },
  sampleNumbers: { en: "Sample numbers", ar: "الأرقام عينة" },
  docWorkingOn: { en: "being worked on", ar: "شغالين عليه" },
  docClientBoq: { en: "Client BOQ", ar: "مقايسة العميل" },
  docSwitch: { en: "Documents of the project", ar: "مستندات المشروع" },
  // The workspace's shell: nothing waiting (the top bar; counted.decisionsWaiting when something does), and who is
  // working now (the chat's head)
  nothingWaiting: { en: "Nothing waiting for you", ar: "مافيش حاجة مستنياك" },
  workingNow: { en: "Working: {role}", ar: "شغال: {role}" },
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
