// The screen language. The core keeps the engineer's choice (nothing sits in web storage); until a later job wires
// that in, this store holds it in memory and starts from the system's language.
import { useSyncExternalStore } from "react";
import type { Dir, Lang } from "./types";

export const dirOf = (lang: Lang): Dir => (lang === "ar" ? "rtl" : "ltr");

const ARABIC = /[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]/;

/** The direction of a piece of data text (a message, a file name): rtl when it holds any Arabic letter.
 *  The browser's automatic direction is never used: it follows the first strong letter, so "Lead QS طلّع…" would turn left to right. */
export const textDir = (value: string): Dir => (ARABIC.test(value) ? "rtl" : "ltr");

export function systemLang(): Lang {
  const system = typeof navigator === "undefined" ? "" : navigator.language;
  return system.toLowerCase().startsWith("ar") ? "ar" : "en";
}

let current: Lang = systemLang();
const listeners = new Set<() => void>();

/** <html> carries lang and dir: portals, Tailwind's rtl: and :lang() fonts all read them there. */
function apply(): void {
  if (typeof document === "undefined") return;
  document.documentElement.lang = current;
  document.documentElement.dir = dirOf(current);
}

export const getLang = (): Lang => current;

export function setLang(next: Lang): void {
  if (next === current) return;
  current = next;
  apply();
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useLang(): { lang: Lang; dir: Dir; setLang: (next: Lang) => void } {
  const lang = useSyncExternalStore(subscribe, getLang, getLang);
  return { lang, dir: dirOf(lang), setLang };
}

apply(); // on import, before the first render
