// A Calc Engine formula in the screen's words: «الكمية × الفئة», not «quantity * rate». Known terms are named; any
// other name (a build-up's own, such as «materials») stays as the core wrote it. Numbers stay as they are.
import { fill, t, type texts } from "../i18n";

type TextKey = keyof typeof texts;

const TERMS: Record<string, TextKey> = {
  quantity: "termQuantity",
  qty: "termQuantity",
  rate: "termRate",
  amount: "termAmount",
  total: "termTotal",
};

/** One input's name in words. */
export function termText(name: string): string {
  const key = TERMS[name.toLowerCase()];
  return key ? t(key) : name;
}

/** A formula or a step in words, with × and ÷ for * and /. */
export function formulaText(formula: string): string {
  return formula
    .replace(/\bsum\(\s*([A-Za-z_][\w]*)\s*\)/gi, (_, x: string) => fill(t("termSum"), { x: termText(x) }))
    .replace(/[A-Za-z_][\w]*/g, (word) => termText(word))
    .replace(/\s*\*\s*/g, " × ")
    .replace(/\s*\/\s*/g, " ÷ ");
}
