// One way numbers read on screen, in both languages: Western digits, "," for thousands and "." for decimals
// (viewers/sheet/format.ts formats the ledger's numbers so). A number written with Arabic-Indic digits or separators
// («٦٤٠٬٩٨٣٫٣٥», by the engineer or the Lead QS) reads «640,983.35»: in ONE's fonts «٫» looks like a comma, so the
// decimal read as a thousands mark («640,983,35»).

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
