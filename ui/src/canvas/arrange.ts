// Arranging the whole canvas at once. "stage": columns in reading order (files, Draft, Checked, Signed off, the
// team and Desks). "tidy": rows in reading order, keeping the order the frames had. Both return a new layout.
import { STRIP_H } from "./place";
import type { DeliverableInfo, FrameKey, Placed } from "./types";

type Status = DeliverableInfo["status"];
export type ArrangeOptions = { dir: "rtl" | "ltr"; gap?: number; rowGap?: number };

const ROW_MIN = 2400;
const height = (f: Placed) => (f.collapsed ? STRIP_H : f.h);

function column(key: FrameKey, status: ReadonlyMap<FrameKey, Status>): number {
  if (key.startsWith("files:") || key.startsWith("file:")) return 0;
  if (key.startsWith("deliverable:")) {
    const s = status.get(key);
    return s === "signed_off" ? 3 : s === "checked" ? 2 : 1;
  }
  return 4; // team and Desks
}

/** Frames in reading order: rows (a frame starts a new row when it is below half the row's first frame), then by
 * side, from the start of the line. */
function readingOrder(frames: readonly Placed[], dir: "rtl" | "ltr"): Placed[] {
  const rows: Placed[][] = [];
  for (const f of [...frames].sort((a, b) => a.y - b.y)) {
    const row = rows.at(-1);
    if (row && f.y < row[0]!.y + height(row[0]!) / 2) row.push(f);
    else rows.push([f]);
  }
  return rows.flatMap((row) => row.sort((a, b) => (dir === "ltr" ? a.x - b.x : b.x + b.w - (a.x + a.w))));
}

export function arrange(
  frames: readonly Placed[],
  status: ReadonlyMap<FrameKey, Status>,
  mode: "stage" | "tidy",
  { dir, gap = 96, rowGap = 144 }: ArrangeOptions,
): Placed[] {
  if (frames.length === 0) return [];
  const minX = Math.min(...frames.map((f) => f.x));
  const maxX = Math.max(...frames.map((f) => f.x + f.w));
  const top = Math.min(...frames.map((f) => f.y));
  const ordered = readingOrder(frames, dir);
  const out: Placed[] = [];

  if (mode === "stage") {
    const columns: Placed[][] = [[], [], [], [], []];
    for (const f of ordered) columns[column(f.key, status)]!.push(f);
    let edge = dir === "ltr" ? minX : maxX; // the column's starting side
    for (const col of columns) {
      if (col.length === 0) continue;
      const width = Math.max(...col.map((f) => f.w));
      let y = top;
      for (const f of col) {
        out.push({ ...f, x: dir === "ltr" ? edge : edge - f.w, y });
        y += height(f) + gap;
      }
      edge = dir === "ltr" ? edge + width + rowGap : edge - width - rowGap;
    }
    return out;
  }

  const area = frames.reduce((sum, f) => sum + (f.w + gap) * (height(f) + rowGap), 0);
  const rowWidth = Math.max(ROW_MIN, Math.sqrt(area) * 1.6);
  let used = 0;
  let y = top;
  let rowHeight = 0;
  for (const f of ordered) {
    if (used > 0 && used + f.w > rowWidth) {
      y += rowHeight + rowGap;
      used = 0;
      rowHeight = 0;
    }
    out.push({ ...f, x: dir === "ltr" ? minX + used : maxX - used - f.w, y });
    used += f.w + gap;
    rowHeight = Math.max(rowHeight, height(f));
  }
  return out;
}
