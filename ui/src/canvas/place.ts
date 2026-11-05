// Where a new frame goes: the first free slot, scanning rows in reading order from the top-left (English) or the
// top-right (Arabic) of the occupied area. A frame already placed never moves, and frames never overlap.
import type { DeliverableInfo, FrameKey, Placed } from "./types";

/** The height of a frame's name strip, and of a folded frame. */
export const STRIP_H = 40;
export const MIN_W = 240;
export const MIN_H = 160;
/** Rows are at least this wide before they wrap. */
const ROW_MIN = 2400;

export type Incoming = { key: FrameKey; w: number; h: number; collapsed?: boolean };
export type PlaceOptions = { dir: "rtl" | "ltr"; gap: number; rowGap: number };

/** A frame's size when it first appears. */
export function sizeFor(key: FrameKey, info: { kind?: DeliverableInfo["kind"]; agents?: number } = {}) {
  const kind = key.slice(0, key.indexOf(":"));
  switch (kind) {
    case "files":
      return { w: 360, h: 520 };
    case "file":
      return { w: 480, h: 640 };
    case "deliverable":
      if (info.kind === "sheet") return { w: 960, h: 640 };
      if (info.kind === "document") return { w: 720, h: 900 };
      return { w: 720, h: 560 };
    case "clientboq":
      return { w: 960, h: 640 };
    case "desk":
      return { w: 320, h: Math.max(MIN_H, 64 + 48 * (info.agents ?? 0)) };
    default:
      return { w: 320, h: 240 };
  }
}

type Box = { x: number; y: number; w: number; h: number };

export function place(existing: readonly Placed[], incoming: readonly Incoming[], opts: PlaceOptions): Placed[] {
  const { dir, gap, rowGap } = opts;
  const out = [...existing];
  const taken = new Set(existing.map((f) => f.key));
  const boxes: Box[] = existing.map(({ x, y, w, h }) => ({ x, y, w, h }));
  const fresh = incoming.filter((f) => !taken.has(f.key));
  if (fresh.length === 0) return out;

  // Rows grow with the canvas, so a big project stays roughly as wide as it is tall.
  const area = [...boxes, ...fresh].reduce((sum, b) => sum + (b.w + gap) * (b.h + rowGap), 0);
  let bounds = boxes.length ? boundsOf(boxes) : null;
  const rowWidth = Math.max(ROW_MIN, Math.sqrt(area) * 1.6, bounds ? bounds.maxX - bounds.minX : 0);

  const clear = (c: Box, near: readonly Box[]) =>
    near.every((b) => c.x + c.w + gap <= b.x || b.x + b.w + gap <= c.x || c.y + c.h + gap <= b.y || b.y + b.h + gap <= c.y);
  let last: Box | null = null;

  for (const item of fresh) {
    const { w, h } = item;
    let spot: Box | null = null;
    if (!bounds) {
      spot = { x: dir === "ltr" ? 0 : -w, y: 0, w, h };
    } else {
      const lo = dir === "ltr" ? bounds.minX : bounds.maxX - rowWidth;
      const hi = dir === "ltr" ? bounds.minX + rowWidth : bounds.maxX;
      const inside = (c: Box) => c.x >= lo && c.x + c.w <= hi;
      // the next slot after the frame just placed, then a scan from the top
      if (last) {
        const c: Box = { x: dir === "ltr" ? last.x + last.w + gap : last.x - gap - w, y: last.y, w, h };
        if (inside(c) && clear(c, band(boxes, c.y, h, gap))) spot = c;
      }
      if (!spot) spot = scan(boxes, { w, h }, bounds, lo, hi, opts, inside, clear);
      if (!spot) spot = { x: dir === "ltr" ? bounds.minX : bounds.maxX - w, y: bounds.maxY + rowGap, w, h };
    }
    boxes.push(spot);
    last = spot;
    bounds = boundsOf([spot], bounds);
    out.push({ key: item.key, x: spot.x, y: spot.y, w, h, z: 0, collapsed: item.collapsed ?? false });
  }
  return out;
}

function band(boxes: readonly Box[], y: number, h: number, gap: number): Box[] {
  return boxes.filter((b) => b.y < y + h + gap && b.y + b.h + gap > y);
}

function scan(
  boxes: readonly Box[],
  size: { w: number; h: number },
  bounds: Bounds,
  lo: number,
  hi: number,
  { dir, gap, rowGap }: PlaceOptions,
  inside: (c: Box) => boolean,
  clear: (c: Box, near: readonly Box[]) => boolean,
): Box | null {
  const { w, h } = size;
  const ys = [...new Set([bounds.minY, ...boxes.map((b) => b.y + b.h + rowGap)])]
    .filter((y) => y <= bounds.maxY)
    .sort((a, b) => a - b);
  for (const y of ys) {
    const near = band(boxes, y, h, gap);
    const xs =
      dir === "ltr"
        ? [lo, ...near.map((b) => b.x + b.w + gap)].sort((a, b) => a - b)
        : [hi - w, ...near.map((b) => b.x - gap - w)].sort((a, b) => b - a);
    for (const x of xs) {
      const c = { x, y, w, h };
      if (inside(c) && clear(c, near)) return c;
    }
  }
  return null;
}

type Bounds = { minX: number; minY: number; maxX: number; maxY: number };

function boundsOf(boxes: readonly Box[], start: Bounds | null = null): Bounds {
  let b = start ?? { minX: Infinity, minY: Infinity, maxX: -Infinity, maxY: -Infinity };
  for (const x of boxes) {
    b = {
      minX: Math.min(b.minX, x.x),
      minY: Math.min(b.minY, x.y),
      maxX: Math.max(b.maxX, x.x + x.w),
      maxY: Math.max(b.maxY, x.y + x.h),
    };
  }
  return b;
}
