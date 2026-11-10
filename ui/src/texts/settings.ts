// Settings: the eight sections, a setting's states, and the words of each section's own parts.
import { defineTexts } from "./types";

export const settings = defineTexts({
  sections: { en: "Settings sections", ar: "أقسام الإعدادات" },
  me: { en: "My profile", ar: "ملفي" },
  ai: { en: "AI", ar: "الذكاء الاصطناعي" },
  team: { en: "Team", ar: "الفريق" },
  caps: { en: "Spending caps", ar: "حدود الصرف" },
  connectors: { en: "Connectors", ar: "الموصلات" },
  backup: { en: "Backup", ar: "النسخ الاحتياطي" },
  privacy: { en: "Privacy", ar: "الخصوصية" },
  look: { en: "Language and look", ar: "اللغة والمظهر" },

  savesItself: {
    en: "Every change saves by itself. You can ask the Lead QS for the same by talking.",
    ar: "كل تغيير بيتحفظ لوحده. وتقدر تطلب نفس الحاجة من الـ Lead QS بالكلام.",
  },
  meLead: {
    en: "The Lead QS knows you by these details. Every change saves by itself.",
    ar: "الـ Lead QS بيعرفك من البيانات دي. كل تغيير بيتحفظ لوحده.",
  },
  teamLead: { en: "The members who stay with you from tender to tender.", ar: "الأعضاء اللي بيفضلوا معاك من عطاء للتاني." },
  connectorsLead: { en: "Tools from outside ONE that the team may use.", ar: "أدوات من بره ONE يقدر الفريق يستخدمها." },
  backupLead: { en: "ONE copies your tenders, encrypted, to a folder you choose.", ar: "ONE بينسخ عطاءاتك مشفرة في فولدر إنت بتختاره." },
  privacyLead: { en: "What leaves this computer, and what you agreed to.", ar: "إيه اللي بيخرج من جهازك، وإيه اللي وافقت عليه." },

  // A setting.
  recommended: { en: "Recommended: {value}", ar: "الموصى به: {value}" },
  recommendedChoice: { en: "Recommended", ar: "الموصى به" },
  on: { en: "on", ar: "شغال" },
  off: { en: "off", ar: "مقفول" },
  putBack: { en: "Put back the recommended value", ar: "رجّع القيمة الموصى بها" },
  saving: { en: "Saving…", ar: "جاري الحفظ…" },
  saved: { en: "Saved.", ar: "اتحفظ." },
  notSaved: { en: "ONE could not save this. Try again.", ar: "ONE مقدرش يحفظ ده. جرّب تاني." },
  example: { en: "Example: {example}", ar: "مثال: {example}" },
  range: { en: "From {min} to {max}.", ar: "من {min} لـ {max}." },
  notLoaded: { en: "ONE could not open this. Try again.", ar: "ONE مقدرش يفتح ده. جرّب تاني." },
  tryAgain: { en: "Try again", ar: "جرّب تاني" },
  notUndone: { en: "It could not be put back.", ar: "مقدرش يرجع." },
  remove: { en: "Remove", ar: "شيل" },

  // My profile: what the Lead QS learned.
  lessons: { en: "What the Lead QS learned about your work", ar: "اللي الـ Lead QS اتعلمه عن شغلك" },
  noLessons: { en: "Nothing yet. The Lead QS learns as you work together.", ar: "لسه مفيش. الـ Lead QS بيتعلم وإنتو بتشتغلوا مع بعض." },
  lessonLabel: { en: "Lesson", ar: "الدرس" },
  fromTender: { en: "From {tender}", ar: "من {tender}" },
  lessonRemoved: { en: "The lesson was removed.", ar: "الدرس اتشال." },

  // AI.
  connect: { en: "Connect a provider", ar: "وصّل مزود" },
  keyLocked: {
    en: "Agree to the AI terms in Privacy first, then paste the key.",
    ar: "وافق على شروط الذكاء الاصطناعي من الخصوصية الأول، وبعدين الصق المفتاح.",
  },
  providers: { en: "Connected providers", ar: "المزودين المتصلين" },
  noProvider: { en: "No provider is connected yet.", ar: "لسه مفيش مزود متصل." },
  works: { en: "Connected and working", ar: "متصل وشغال" },
  onDevice: { en: "On this computer", ar: "على الجهاز ده" },
  disconnect: { en: "Disconnect", ar: "افصل" },
  disconnected: { en: "{name} was disconnected.", ar: "اتفصل {name}." },
  notDisconnected: { en: "ONE could not disconnect it. Try again.", ar: "ONE مقدرش يفصله. جرّب تاني." },
  claudeCode: { en: "My own Claude Code", ar: "Claude Code بتاعي" },
  claudeCodeMeta: { en: "ONE works through your Claude Code subscription.", ar: "ONE بيشتغل من خلال اشتراك Claude Code بتاعك." },
  rolesTitle: { en: "A model for each role", ar: "موديل لكل دور" },
  role_lead: { en: "Lead QS", ar: "الـ Lead QS" },
  role_checker: { en: "Checking QS", ar: "الـ Checking QS" },
  role_specialist: { en: "Specialists", ar: "المتخصصين" },
  role_quick: { en: "Quick questions", ar: "الأسئلة السريعة" },
  noModels: { en: "Connect a provider first: its models show here.", ar: "وصّل مزود الأول: موديلاته هتظهر هنا." },
  searchKey: { en: "Web search key", ar: "مفتاح البحث على النت" },
  searchBy: { en: "ONE searches the web with {provider}.", ar: "ONE بيدور على النت بـ {provider}." },
  searchNone: { en: "No web search yet. Paste a key to add it.", ar: "لسه مفيش بحث على النت. الصق مفتاح علشان تضيفه." },
  searchKept: { en: "Your own key is kept. Paste another to change it.", ar: "مفتاحك محفوظ. الصق مفتاح تاني علشان تغيره." },
  searchSaving: { en: "Keeping the key…", ar: "جاري حفظ المفتاح…" },

  // Team.
  noMembers: { en: "No member stays with you yet.", ar: "لسه مفيش عضو بيفضل معاك." },
  model: { en: "Model: {name}", ar: "الموديل: {name}" },
  tenders: {
    en: { one: "Worked with you on {n} tender", other: "Worked with you on {n} tenders" },
    ar: {
      zero: "لسه مشتغلش معاك في أي عطاء",
      one: "اشتغل معاك في عطاء واحد",
      two: "اشتغل معاك في عطاءين",
      few: "اشتغل معاك في {n} عطاءات",
      many: "اشتغل معاك في {n} عطاء",
      other: "اشتغل معاك في {n} عطاء",
    },
  },
  checks: { en: "{passed} of {total} checks passed", ar: "{passed} من {total} مراجعة عدّت" },
  costUsd: { en: "{cost} USD paid", ar: "{cost} دولار اتدفعوا" },

  // Spending caps.
  spent: { en: "What is spent", ar: "المصروف" },
  spentToday: { en: "Today: {amount} USD", ar: "النهارده: {amount} دولار" },
  spentMonth: { en: "This month: {amount} USD", ar: "الشهر ده: {amount} دولار" },

  // Connectors.
  noConnectors: { en: "No connector is added yet.", ar: "لسه مفيش موصل متضاف." },
  connectorTools: {
    en: { one: "{n} tool", other: "{n} tools" },
    ar: { zero: "مفيش أدوات", one: "أداة واحدة", two: "أداتين", few: "{n} أدوات", many: "{n} أداة", other: "{n} أداة" },
  },
  removed: { en: "{name} was removed.", ar: "اتشال {name}." },
  notRemoved: { en: "ONE could not remove it. Try again.", ar: "ONE مقدرش يشيله. جرّب تاني." },

  // Backup.
  folder: { en: "Backup folder", ar: "فولدر النسخ الاحتياطي" },
  folderHelp: {
    en: "Write the folder's full path. ONE saves it when you leave the box.",
    ar: "اكتب مسار الفولدر كامل. ONE هيحفظه أول ما تسيب الخانة.",
  },
  chooseFolder: { en: "Choose a folder", ar: "اختار فولدر" },
  unreachable: { en: "ONE cannot reach this folder now.", ar: "ONE مش قادر يوصل للفولدر ده دلوقتي." },
  lastRun: { en: "Last backup: {when}", ar: "آخر نسخة: {when}" },
  never: { en: "No backup yet.", ar: "لسه مفيش نسخة." },
  backUpNow: { en: "Back up now", ar: "اعمل نسخة دلوقتي" },
  backedUp: { en: "Backed up.", ar: "اتعملت النسخة." },
  notBackedUp: { en: "ONE could not back up. Try again.", ar: "ONE مقدرش يعمل النسخة. جرّب تاني." },

  // Privacy.
  agreedOn: { en: "You agreed on {date}.", ar: "وافقت يوم {date}." },
  notAgreed: { en: "You have not agreed yet, so ONE sends nothing.", ar: "لسه موافقتش، فـ ONE مش بيبعت حاجة." },
});
