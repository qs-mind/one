// The one place that formats numbers and dates. Western digits and the Gregorian calendar in both languages:
// Intl gives Arabic-Indic digits for ar-EG and ar-SA, so the locale is fixed here and never read from the system.
import type { Lang } from "./types";

/** The locale to hand to Intl and to any library that formats (Base UI's Progress takes it as `locale`). */
export const intlLocale = (lang: Lang): string => (lang === "ar" ? "ar-u-nu-latn" : "en-GB");

export function formatNumber(value: number, lang: Lang, options?: Intl.NumberFormatOptions): string {
  return new Intl.NumberFormat(intlLocale(lang), options).format(value);
}

export function formatDate(
  value: Date,
  lang: Lang,
  options: Intl.DateTimeFormatOptions = { day: "numeric", month: "long" },
): string {
  return new Intl.DateTimeFormat(intlLocale(lang), { ...options, calendar: "gregory" }).format(value);
}
