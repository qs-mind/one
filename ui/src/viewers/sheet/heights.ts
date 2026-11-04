// Row heights, ours: react-data-grid needs them up front. Wrapped columns are word-wrapped with a measure
// function (canvas measureText in the real font after document.fonts.ready; a character estimate in jsdom),
// so long Arabic descriptions are never cut. Words are never split, so Arabic letters stay joined.
import type { ViewColumn, ViewRow } from "../../deliverables/types";
import { isNumber } from "../../deliverables/types";

const LINE = 22; // 14px text at line-height 1.6
const PAD = 14; // block padding inside a cell
const INLINE_PAD = 16; // the grid's 8px inline padding on each side
export const FONT = `14px "Kumbh Sans Variable", "Zain", system-ui, sans-serif`;
const BOLD = `700 ${FONT}`;

export type Measure = (text: string, font: string) => number;

/** The height of a row whose tallest cell holds n lines. */
export const linesHeight = (lines: number) => lines * LINE + PAD;

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

export function rowHeight(row: ViewRow, columns: ViewColumn[], measure: Measure): number {
  const titleColumn = titleColumnOf(columns);
  const font = row.kind === "section" ? BOLD : FONT;
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
    if (text) most = Math.max(most, lineCount(text, column.width - INLINE_PAD, font, measure));
  }
  return linesHeight(most);
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
