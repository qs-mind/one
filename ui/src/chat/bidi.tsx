// Mixed Arabic and English in one block. Each block takes its base direction from its own first strong letter
// (dir="auto"). Inside it, a run in the other script (a file name, a cell like H18, an English word in an Arabic line)
// is isolated in a <bdi>, so the Unicode bidi rules cannot pull the punctuation and numbers around it to its side:
// «إجمالي البنود في ملف boq-priced.xls:» ends with its colon at the Arabic end, and 100,912,880.78 stays after it.
// Runs are cut only between words, never inside one, so Arabic letters always stay joined.
import { Fragment } from "react";
import { westernNumbers } from "../ui/digits";

const LATIN = "\\p{Script=Latin}";
const ARABIC = "\\p{Script=Arabic}";
// a word, with its joined parts: boq-priced.xls, H18:H23, v1.2, 30mm
const latinUnit = `(?:\\p{Nd}+(?:[.,]\\p{Nd}+)*)?${LATIN}[${LATIN}\\p{Nd}\\p{M}]*(?:[-_./\\\\:@#+&'’][${LATIN}\\p{Nd}]+)*`;
const arabicUnit = `[${ARABIC}\\u0640][${ARABIC}\\p{M}\\u0640\\u200c\\u200d]*`;
// words of one script with the spaces (and bare numbers) between them: "Project Records", "Section 3 Concrete"
const run = (unit: string) => new RegExp(`${unit}(?:\\s+(?:\\p{Nd}+\\s+)*${unit})*`, "gu");
const latinRun = run(latinUnit);
const arabicRun = run(arabicUnit);
const RTL = /[\p{Script=Arabic}\p{Script=Hebrew}]/u;
const STRONG = /[\p{L}]/u;

/** The direction dir="auto" gives this text: its first strong letter's; none: null. */
export function baseDirection(text: string): "rtl" | "ltr" | null {
  const first = STRONG.exec(text)?.[0];
  if (!first) return null;
  return RTL.test(first) ? "rtl" : "ltr";
}

export type Piece = { text: string; isolate: boolean };

/** `text` cut into pieces; the runs in the other script than `base` are marked to isolate. */
export function pieces(text: string, base: "rtl" | "ltr" | null): Piece[] {
  if (!base) return [{ text, isolate: false }];
  const pattern = base === "rtl" ? latinRun : arabicRun;
  const out: Piece[] = [];
  let at = 0;
  for (const match of text.matchAll(pattern)) {
    if (match.index > at) out.push({ text: text.slice(at, match.index), isolate: false });
    out.push({ text: match[0], isolate: true });
    at = match.index + match[0].length;
  }
  if (at < text.length) out.push({ text: text.slice(at), isolate: false });
  return out.length ? out : [{ text, isolate: false }];
}

type Node = { type: string; value?: string; children?: Node[]; data?: object };

const BLOCKS = new Set(["paragraph", "heading", "tableCell"]);
const isolate = (children: Node[]): Node => ({ type: "isolate", data: { hName: "bdi" }, children });

/** Text as dir="auto" reads it: a <bdi> (here: inline code) does not count. */
function plain(node: Node): string {
  if (node.type === "text") return node.value ?? "";
  if (node.type === "inlineCode") return "";
  return (node.children ?? []).map(plain).join("");
}

function wrap(node: Node, base: "rtl" | "ltr" | null) {
  if (!node.children) return;
  node.children = node.children.flatMap((child): Node[] => {
    if (child.type === "text") {
      return pieces(child.value ?? "", base).map((piece) =>
        piece.isolate ? isolate([{ type: "text", value: piece.text }]) : { type: "text", value: piece.text },
      );
    }
    if (child.type === "inlineCode") return [isolate([child])]; // code is often a file name or a formula
    wrap(child, base);
    return [child];
  });
}

/** A remark step: in each paragraph, heading and table cell, the runs in the other script are isolated. */
export function isolateOtherScript() {
  const walk = (node: Node) => {
    if (BLOCKS.has(node.type)) return wrap(node, baseDirection(plain(node)));
    for (const child of node.children ?? []) walk(child);
  };
  return () => walk;
}

/** Plain text (the engineer's own message, a card's cell) with the other script's runs isolated. */
export function BidiText({ text }: { text: string }) {
  return (
    <>
      {pieces(westernNumbers(text), baseDirection(text)).map((piece, i) =>
        piece.isolate ? <bdi key={i}>{piece.text}</bdi> : <Fragment key={i}>{piece.text}</Fragment>,
      )}
    </>
  );
}
