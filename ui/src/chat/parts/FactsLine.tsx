// The facts beside a Brief's reply, from ONE's own records (core: engine/truth.py, data-facts): how much of the
// BOQ is priced and whether a Deliverable exists, and a line for each thing the reply says that the records do not
// show. The core's words, never the model's.
import { type Language, pick } from "../../i18n";
import type { FactsData, RedoData } from "./types";

export function FactsLine({ facts, lang }: { facts: FactsData; lang: Language }) {
  return (
    <div data-facts className="flex flex-col gap-1 text-sm">
      {facts.text && (
        <p dir="auto" className="text-slate">
          {pick(facts.text, lang)}
        </p>
      )}
      {facts.flags.map((flag, i) => (
        <p key={i} dir="auto" role="status" className="text-copper">
          {pick(flag, lang)}
        </p>
      ))}
    </div>
  );
}

/** The reply as the engineer reads it: the words the core sent back to be fixed (data-redo) taken out. Its range
 * is in the reply's UTF-16 units, as a JavaScript string counts them. */
export function withoutRedone(text: string, redo: RedoData | undefined): string {
  if (!redo || redo.from >= redo.to) return text;
  return text.slice(0, redo.from) + text.slice(redo.to);
}
