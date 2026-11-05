// A view the Lead QS shows in the chat (decision 16.1), as the core sends it in a `data-view` part (core/qsone/view.py).
// The model chose the blocks; the core put each number's cell (value, source id, date) where the model put a
// reference, so the screen never computes a number. Text is plain words, never HTML.
import type { NumberCell, Source } from "../../../deliverables/types";

export type HeadingBlock = { kind: "heading"; text: string };
export type ProseBlock = { kind: "prose"; text: string };
export type FiguresBlock = { kind: "figures"; items: { label: string; value: NumberCell }[] };
export type TableColumn = { key: string; label: string; type: "text" | "number" };
/** A row by column key: words in a text column, a number's cell in a number column. */
export type TableBlock = { kind: "table"; columns: TableColumn[]; rows: Record<string, string | NumberCell>[] };
export type LeafBlock = HeadingBlock | ProseBlock | FiguresBlock | TableBlock;
/** One level only: a group holds no group. */
export type GroupBlock = { kind: "group"; title: string | null; blocks: LeafBlock[] };
export type ViewBlock = LeafBlock | GroupBlock;

export type ViewData = {
  title: string;
  /** Sample data, labelled as such: the model said so, or a shown number comes from a sample source. */
  sample: boolean;
  blocks: ViewBlock[];
  sources: Record<string, Source>;
  /** Numbers in the words that no tool gave: marked where they stand, never removed. */
  unsourced: string[];
};
