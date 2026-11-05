// What the engineer can see of the canvas: the pane less what floats over it (the open chat, the command bar, the
// minimap and the zoom controls). Fit all, a project's first view, Focus, Follow and new frames use this free area, so
// nothing they show sits under the chat, on whichever side the language puts it. An overlay marks itself with
// `data-canvas-cover`; the minimap is React Flow's own. A first view is also kept readable: when every frame would be
// too small to read, it shows the ones that matter most now, and the rest stay a pan or a minimap click away.

export type Rect = { x: number; y: number; w: number; h: number };

const COVERS = "[data-canvas-cover], .react-flow__minimap";
/** Below this share of the pane left free (a narrow window under the chat sheet), the whole pane is used. */
const LEAST = 0.3;

/** The pane less the covers, in the pane's own coordinates. A cover that spans most of the pane's height (the chat)
 * takes its side off; any other (the minimap, the zoom controls, a floating command bar) takes off a band at its
 * nearest edge, across or along, whichever leaves more room. */
export function freeRect(pane: Rect, covers: readonly Rect[]): Rect {
  let left = 0;
  let right = pane.w;
  let top = 0;
  let bottom = pane.h;
  const inPane = covers
    .map((c) => ({
      x0: Math.max(0, c.x - pane.x),
      x1: Math.min(pane.w, c.x + c.w - pane.x),
      y0: Math.max(0, c.y - pane.y),
      y1: Math.min(pane.h, c.y + c.h - pane.y),
    }))
    .filter((c) => c.x1 > c.x0 && c.y1 > c.y0) // over the pane
    .map((c) => ({ ...c, tall: c.y1 - c.y0 >= pane.h * 0.6 }))
    .sort((a, b) => Number(b.tall) - Number(a.tall)); // the chat first: the others are weighed in what it leaves
  for (const c of inPane) {
    if (c.x1 <= left || c.x0 >= right || c.y1 <= top || c.y0 >= bottom) continue; // already left out
    const atEnd = (c.x0 + c.x1) / 2 >= (left + right) / 2;
    const side = atEnd ? { left, right: Math.min(right, c.x0) } : { left: Math.max(left, c.x1), right };
    if (c.tall) {
      ({ left, right } = side);
      continue;
    }
    const below = (c.y0 + c.y1) / 2 >= (top + bottom) / 2;
    const band = below ? { top, bottom: Math.min(bottom, c.y0) } : { top: Math.max(top, c.y1), bottom };
    const across = (right - left) * (band.bottom - band.top);
    const along = (side.right - side.left) * (bottom - top);
    if (across >= along) ({ top, bottom } = band);
    else ({ left, right } = side);
  }
  const w = right - left;
  const h = bottom - top;
  if (w < pane.w * LEAST || h < pane.h * LEAST) return { x: 0, y: 0, w: pane.w, h: pane.h };
  return { x: left, y: top, w, h };
}

const rectOf = (el: Element): Rect => {
  const r = el.getBoundingClientRect();
  return { x: r.left, y: r.top, w: r.width, h: r.height };
};

/** The free area of the canvas pane now (pane coordinates), or the whole `size` when the pane is not laid out. */
export function freeArea(pane: Element | null | undefined, size: { width: number; height: number }): Rect {
  const whole = { x: 0, y: 0, w: size.width, h: size.height };
  if (!pane) return whole;
  const box = rectOf(pane);
  if (!box.w || !box.h) return whole;
  const covers = [...document.querySelectorAll(COVERS)].filter((el) => !el.closest("[hidden]")).map(rectOf);
  const free = freeRect(box, covers);
  // the pane may be measured a little differently from React Flow's own size: scale to it
  const sx = size.width / box.w;
  const sy = size.height / box.h;
  return { x: free.x * sx, y: free.y * sy, w: free.w * sx, h: free.h * sy };
}

/** The free area in world coordinates, under the viewport `[tx, ty, zoom]`. */
export function worldOf(free: Rect, [tx, ty, zoom]: readonly [number, number, number]): Rect {
  return { x: (free.x - tx) / zoom, y: (free.y - ty) / zoom, w: free.w / zoom, h: free.h / zoom };
}

/** Below this zoom a frame shows only its poster (lod.ts): a first view keeps to it or above. */
export const READABLE = 0.6;
/** The zoom a first view and Open prefer: 100%, the size the text is set for, whenever the frames fit there. */
export const PREFERRED = 1;
/** A first view keeps the frames that matter most together down to this zoom, rather than leave one out. */
export const TOGETHER = 0.85;
/** The room, in px, a first view or an opened frame keeps between the frames and the free area's edges. */
export const MARGIN = 32;

type Framed = { key: string; x: number; y: number; w: number; h: number };

/** The frames a view shows when all of them would not fit `area` at `zoom`: by `rank` (lower first), each that still
 * fits with those taken, so the view stays readable. The first by rank always, even alone too big. */
export function readable<T extends Framed>(frames: readonly T[], rank: (key: string) => number, area: { w: number; h: number }, zoom = READABLE, padding = 0.1): T[] {
  const fits = (set: readonly T[]) => {
    const w = Math.max(...set.map((f) => f.x + f.w)) - Math.min(...set.map((f) => f.x));
    const h = Math.max(...set.map((f) => f.y + f.h)) - Math.min(...set.map((f) => f.y));
    return w * zoom <= area.w * (1 - 2 * padding) && h * zoom <= area.h * (1 - 2 * padding);
  };
  if (!frames.length || fits(frames)) return [...frames];
  const order = [...frames].sort((a, b) => rank(a.key) - rank(b.key));
  const taken: T[] = [order[0]!];
  for (const f of order.slice(1)) if (fits([...taken, f])) taken.push(f);
  return taken;
}
