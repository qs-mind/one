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
