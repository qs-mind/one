// One way numbers read on screen, in both languages: Western digits, "," for thousands and "." for decimals
// (viewers/sheet/format.ts formats the ledger's numbers so). A number written with Arabic-Indic digits or separators
// («٦٤٠٬٩٨٣٫٣٥», in ONE's output) reads «640,983.35». Engineer-authored text is preserved. In ONE's fonts «٫» looks like a comma, so the
// decimal read as a thousands mark («640,983,35»).

import { fill, t } from "../i18n";

const DIGITS: Record<string, string> = {};
for (let d = 0; d < 10; d++) {
  DIGITS[String.fromCharCode(0x0660 + d)] = String(d); // Arabic-Indic
  DIGITS[String.fromCharCode(0x06f0 + d)] = String(d); // Extended (Persian)
}
const NUMBER = /[0-9٠-٩۰-۹]+(?:[٬٫,.][0-9٠-٩۰-۹]+)*/g;
const EASTERN = /[٠-٩۰-۹٫٬]/;

/** `text` with each number in Western digits, "," for thousands and "." for decimals; everything else as written. */
export function westernNumbers(text: string): string {
  if (!EASTERN.test(text)) return text;
  return text.replace(NUMBER, (number) =>
    EASTERN.test(number) ? number.replace(/[٠-٩۰-۹]/g, (d) => DIGITS[d]!).replace(/٬/g, ",").replace(/٫/g, ".") : number,
  );
}

const LRI = "⁦"; // left-to-right isolate
const PDI = "⁩"; // its end

/** A price in USD as the core sent it (exact decimal text), at least two decimals: «$1.50». Isolated, so an Arabic line
 * never turns it into «1.5$»; it works in a select's options too, where no <bdi> can go. */
export function usd(text: string): string {
  const [whole, part = ""] = text.split(".");
  return `${LRI}$${whole}.${part.padEnd(2, "0")}${PDI}`;
}

/** A model's price per million tokens, one way everywhere (first launch, AI settings). */
export function perMillion(priceIn: string, priceOut: string): string {
  return fill(t("pricePerMillion"), { in: usd(priceIn), out: usd(priceOut) });
}
