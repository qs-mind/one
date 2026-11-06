// Row heights, ours: react-data-grid needs them up front. Wrapped columns are word-wrapped with a measure
// function (canvas measureText in the real font after document.fonts.ready; a character estimate in jsdom),
// so long Arabic descriptions are never cut. Words are never split, so Arabic letters stay joined.
// Every px here is at 100 %; `sizes` (ui/scale.ts useSizes) draws them at the screen's scale: `space` for padding and
// widths, `text` for the cells' type (the grid's font follows the same floor as the body's, styles.css), so the rows
// the virtualised grid places line up with the cells the browser draws at any window size or zoom.
import type { ViewColumn, ViewRow } from "../../deliverables/types";
import { isNumber } from "../../deliverables/types";
import { formatDecimal } from "./format";

const LINE = 24; // one line of cell text: the body's 14px at 1.5 is 21 px, Arabic's 15px at 1.65 about 25 px (styles.css)
const PAD = 16; // block padding inside a cell: a one-line row is 40 px
/** The open document's (mode "workspace") denser rows: a one-line row is 32 px, so more of the bill shows. */
export const COMPACT_PAD = 8;
const INLINE_PAD = 24; // the cells' 12px inline padding on each side (styles.css)
const FIT_SLACK = 4; // a pixel or so of rounding, and room for a pending mark beside the value
/** The grid's text, 15 px at 100 % (grid.tsx --rdg-font-size). */
export const FONT_PX = 15;
const FAMILY = `"Kumbh Sans Variable", "Zain", system-ui, sans-serif`;

/** The screen's two scales (ui/scale.ts): 1 and 1 at 100 %. */
export type Sizes = { space: number; text: number };
export const FULL_SIZE: Sizes = { space: 1, text: 1 };

const fontOf = (sizes: Sizes) => `${FONT_PX * sizes.text}px ${FAMILY}`;

/** A column's width on screen: the Deliverable's width was set for 8px cell padding; the cells have 12px now, so
 * each column is 12px wider and its words keep about the room they had. */
export const shownWidth = (width: number, sizes: Sizes = FULL_SIZE) => (width + 12) * sizes.space;

export type Measure = (text: string, font: string) => number;

/** The height of a row whose tallest cell holds n lines. */
export const linesHeight = (lines: number, pad = PAD, sizes: Sizes = FULL_SIZE) => lines * LINE * sizes.text + pad * sizes.space;

function lineCount(text: string, width: number, font: string, measure: Measure): number {
  const space = measure(" ", font);
  let count = 0;
  for (const paragraph of text.split("\n")) {
    count += 1;
    let used = 0;
    for (const word of paragraph.split(/\s+/).filter(Boolean)) {
      const w = measure(word, font);
      if (used > 0 && used + space + w > width) {
        count += 1;
        used = w;
      } else used += (used > 0 ? space : 0) + w;
    }
  }
  return Math.max(count, 1);
}

/** The column a section row shows its title in: description, else the first wrapped text column. */
export function titleColumnOf(columns: ViewColumn[]): string | undefined {
  return (columns.find((c) => c.key === "description") ?? columns.find((c) => c.kind === "text" && c.wrap))?.key;
}

export function rowHeight(row: ViewRow, columns: ViewColumn[], measure: Measure, pad = PAD, sizes: Sizes = FULL_SIZE): number {
  const titleColumn = titleColumnOf(columns);
  const font = row.kind === "section" ? `700 ${fontOf(sizes)}` : fontOf(sizes);
  let most = 1;
  for (const column of columns) {
    if (!column.wrap) continue;
    const cell = row.cells[column.key];
    const text =
      row.kind === "section"
        ? column.key === titleColumn
          ? (row.title ?? "")
          : ""
        : cell && !isNumber(cell)
          ? cell.text
          : "";
    if (text) most = Math.max(most, lineCount(text, shownWidth(column.width, sizes) - INLINE_PAD * sizes.space, font, measure));
  }
  return linesHeight(most, pad, sizes);
}

/** The text a one-line cell shows: a code, a unit's words, or a number as the grid formats it. */
function shownText(row: ViewRow, column: ViewColumn): string {
  if (row.kind === "section") return "";
  if (column.from === "code" || (column.from === undefined && column.key === "code")) return row.code ?? "";
  const cell = row.cells[column.key];
  if (!cell) return "";
  return isNumber(cell) ? formatDecimal(cell.value, cell.currency ? 2 : undefined) : cell.text;
}

/** A one-line column's width, as the Deliverable sets widths (before shownWidth): at least its own, and wide enough
 * for its longest value and its header, so a code such as «02-01-001» is never cut to «02-01…» and every row reads
 * as itself. `extra` is text shown bold in the column (the total). Wrapped columns keep their width. */
export function oneLineWidth(
  column: ViewColumn,
  header: string,
  rows: readonly ViewRow[],
  measure: Measure,
  extra: string[] = [],
  sizes: Sizes = FULL_SIZE,
): number {
  if (column.wrap) return column.width;
  const font = fontOf(sizes);
  const bold = `700 ${font}`;
  // the few longest by characters are measured, not every row of a 5,000-row bill
  const texts = rows
    .map((row) => shownText(row, column))
    .filter(Boolean)
    .sort((a, b) => b.length - a.length)
    .slice(0, 5);
  const widest = Math.max(
    measure(header, bold),
    ...texts.map((text) => measure(text, font)),
    ...extra.map((text) => measure(text, bold)),
    0,
  );
  // in the Deliverable's units (at 100 %): the shown width, (width + 12) × space, holds the text and its padding
  return Math.max(column.width, Math.ceil((widest + INLINE_PAD * sizes.space + FIT_SLACK) / sizes.space) - shownWidth(0));
}

/** Canvas measureText in the page's font; in jsdom (no canvas) about 7 px a character. */
export function makeMeasure(): Measure {
  const jsdom = typeof navigator !== "undefined" && navigator.userAgent.includes("jsdom");
  const context = jsdom ? null : document.createElement("canvas").getContext("2d");
  const cache = new Map<string, number>();
  return (text, font) => {
    if (!context) return text.length * 7;
    const key = `${font}\u0000${text}`;
    let width = cache.get(key);
    if (width === undefined) {
      context.font = font;
      width = context.measureText(text).width;
      cache.set(key, width);
    }
    return width;
  };
}
