// A view the Lead QS shows in the chat (decision 16.1), as the core sends it in a `data-view` part (core/qsone/view.py).
// The model chose the blocks; the core put each number's cell (value, source id, date) where the model put a
// reference, so the screen never computes a number. Text is plain words, never HTML.
import type { NumberCell, Source } from "../../../deliverables/types";

/** Any block may name its section; a run of blocks with one section shows under its title, one level deep. */
type InSection = { section?: string | null };
export type HeadingBlock = InSection & { kind: "heading"; text: string };
export type ProseBlock = InSection & { kind: "prose"; text: string };
export type FiguresBlock = InSection & { kind: "figures"; items: { label: string; value: NumberCell }[] };
/** A row's label, then its texts, then its numbers, under the columns in that order. */
export type TableRow = { label: string; texts: string[]; numbers: NumberCell[] };
export type TableBlock = InSection & { kind: "table"; columns: { label: string }[]; rows: TableRow[] };
export type ViewBlock = HeadingBlock | ProseBlock | FiguresBlock | TableBlock;

export type ViewData = {
  title: string;
  /** Sample data, labelled as such: the model said so, or a shown number comes from a sample source. */
  sample: boolean;
  blocks: ViewBlock[];
  sources: Record<string, Source>;
  /** Numbers in the words that no tool gave: marked where they stand, never removed. */
  unsourced: string[];
};
