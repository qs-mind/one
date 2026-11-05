// What the engineer can see of the canvas: the pane less what floats over it (the open chat, the command bar, the
// minimap and the zoom controls). Fit all, a project's first view, Focus, Follow and new frames use this free area, so
// nothing they show sits under the chat, on whichever side the language puts it. An overlay marks itself with
// `data-canvas-cover`; the minimap is React Flow's own.

export type Rect = { x: number; y: number; w: number; h: number };

const COVERS = "[data-canvas-cover], .react-flow__minimap";
/** Below this share of the pane left free (a narrow window under the chat sheet), the whole pane is used. */
const LEAST = 0.3;

/** The pane less the covers, in the pane's own coordinates. A cover that spans most of the pane's height (the chat)
 * takes its side off; any other takes a band off the bottom (or top) up to its far edge. */
export function freeRect(pane: Rect, covers: readonly Rect[]): Rect {
  let left = 0;
  let right = pane.w;
  let top = 0;
  let bottom = pane.h;
  for (const c of covers) {
    const x0 = Math.max(0, c.x - pane.x);
    const x1 = Math.min(pane.w, c.x + c.w - pane.x);
    const y0 = Math.max(0, c.y - pane.y);
    const y1 = Math.min(pane.h, c.y + c.h - pane.y);
    if (x1 <= x0 || y1 <= y0) continue; // not over the pane
    if (y1 - y0 >= pane.h * 0.6) {
      if ((x0 + x1) / 2 >= pane.w / 2) right = Math.min(right, x0);
      else left = Math.max(left, x1);
    } else if ((y0 + y1) / 2 >= pane.h / 2) {
      bottom = Math.min(bottom, y0);
    } else {
      top = Math.max(top, y1);
    }
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
