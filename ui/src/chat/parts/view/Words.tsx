// Words of a view: plain text, each run in the other script isolated, and each number the numbers guard found with no
// source marked where it stands, as the Reply marks them.
import { BidiText } from "../../bidi";
import { t } from "../../../i18n";

const escape = (value: string) => value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const digit = "[0-9٠-٩]";

/** `text` cut into its words and its unsourced numbers (whole numbers only: "7,500" is not found in "17,500"). */
export function splitUnsourced(text: string, unsourced: readonly string[]): { text: string; marked: boolean }[] {
  if (!unsourced.length) return [{ text, marked: false }];
  const pattern = new RegExp(
    `(?<!${digit}[.,٫٬]?)(?:${unsourced.map(escape).join("|")})(?![.,٫٬]?${digit})`,
    "g",
  );
  const out: { text: string; marked: boolean }[] = [];
  let at = 0;
  for (const match of text.matchAll(pattern)) {
    if (match.index > at) out.push({ text: text.slice(at, match.index), marked: false });
    out.push({ text: match[0], marked: true });
    at = match.index + match[0].length;
  }
  if (at < text.length) out.push({ text: text.slice(at), marked: false });
  return out;
}

export function Words({ text, unsourced }: { text: string; unsourced: readonly string[] }) {
  return (
    <>
      {splitUnsourced(text, unsourced).map((piece, i) =>
        piece.marked ? (
          <mark key={i} title={t("noSource")} className="rounded-sm bg-stone px-0.5 text-copper underline decoration-dotted">
            {piece.text}
          </mark>
        ) : (
          <BidiText key={i} text={piece.text} />
        ),
      )}
    </>
  );
}
