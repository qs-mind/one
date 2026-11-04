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
  model: { en: "Model", ar: "النموذج" },
  modelTitle: { en: "Choose the Lead QS model", ar: "اختر نموذج كبير مهندسي الكميات" },
  modelsLoading: { en: "Loading the models your key can use…", ar: "جارٍ تحميل النماذج المتاحة لمفتاحك…" },
  modelsNoKey: {
    en: "Add your Claude key first from “Claude key” at the top.",
    ar: "أضف مفتاح Claude أولًا من «مفتاح Claude» في الأعلى.",
  },
  modelsFailed: { en: "The models could not be loaded. Try again.", ar: "تعذّر تحميل النماذج. حاول مرة أخرى." },
  modelInUse: { en: "In use", ar: "قيد الاستخدام" },
  modelNotSaved: { en: "The model was not saved. Try again.", ar: "لم يُحفظ النموذج. حاول مرة أخرى." },
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
