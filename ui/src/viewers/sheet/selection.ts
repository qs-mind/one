// A range of cells, ours: react-data-grid selects one cell only. Indexes are of the rows shown (after
// collapse) and of the columns in screen order (frozen first).
export type Cell = { row: number; col: number };
export type Range = { anchor: Cell; focus: Cell };
export type Arrow = "ArrowLeft" | "ArrowRight" | "ArrowUp" | "ArrowDown";

/** Moves the range's focus one cell, as Shift+arrow does. In RTL the next column is to the left. */
export function extend(range: Range, key: Arrow, dir: "rtl" | "ltr", size: { rows: number; cols: number }): Range {
  const next = dir === "rtl" ? "ArrowLeft" : "ArrowRight";
  const vertical = key === "ArrowUp" || key === "ArrowDown";
  const dRow = vertical ? (key === "ArrowDown" ? 1 : -1) : 0;
  const dCol = vertical ? 0 : key === next ? 1 : -1;
  const clamp = (n: number, count: number) => Math.min(Math.max(n, 0), Math.max(count - 1, 0));
  return {
    anchor: range.anchor,
    focus: { row: clamp(range.focus.row + dRow, size.rows), col: clamp(range.focus.col + dCol, size.cols) },
  };
}

export function normalised(range: Range): { top: number; bottom: number; start: number; end: number } {
  const { anchor: a, focus: f } = range;
  return {
    top: Math.min(a.row, f.row),
    bottom: Math.max(a.row, f.row),
    start: Math.min(a.col, f.col),
    end: Math.max(a.col, f.col),
  };
}

export function inRange(range: Range | null, row: number, col: number): boolean {
  if (!range) return false;
  const { top, bottom, start, end } = normalised(range);
  return row >= top && row <= bottom && col >= start && col <= end;
}
