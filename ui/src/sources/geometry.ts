// Where a number and its source are on screen, and the lines drawn between and round them. Everything here works
// in real screen positions (getBoundingClientRect), so a line or a mark faces the right way in Arabic and English
// alike, inside a scaled canvas frame too.

/** The part of `el` the engineer can see: inside the window and inside every box round it that clips (a scroll
 * area, the canvas pane). Null when none of it shows. */
export function visibleRect(el: Element): DOMRect | null {
  if (!el.isConnected) return null;
  const r = el.getBoundingClientRect();
  let left = Math.max(r.left, 0);
  let top = Math.max(r.top, 0);
  let right = Math.min(r.right, innerWidth);
  let bottom = Math.min(r.bottom, innerHeight);
  for (let up = el.parentElement; up && up !== document.body && up !== document.documentElement; up = up.parentElement) {
    const style = getComputedStyle(up);
    if (![style.overflow, style.overflowX, style.overflowY].some((v) => v && v !== "visible")) continue;
    const clip = up.getBoundingClientRect();
    left = Math.max(left, clip.left);
    top = Math.max(top, clip.top);
    right = Math.min(right, clip.right);
    bottom = Math.min(bottom, clip.bottom);
  }
  if (right - left <= 0 || bottom - top <= 0) return null;
  return new DOMRect(left, top, right - left, bottom - top);
}

const n = (v: number) => String(Math.round(v * 10) / 10);

/** One line from the number (`a`) to its source (`b`), from the side of each that faces the other; a gentle S
 * curve, never a loop. */
export function linePath(a: DOMRect, b: DOMRect): string {
  const midY = (r: DOMRect) => r.top + r.height / 2;
  const midX = (r: DOMRect) => r.left + r.width / 2;
  if (b.left >= a.right || b.right <= a.left) {
    const rightwards = b.left >= a.right;
    const [x1, y1] = [rightwards ? a.right : a.left, midY(a)];
    const [x2, y2] = [rightwards ? b.left : b.right, midY(b)];
    const mx = (x1 + x2) / 2;
    return `M ${n(x1)} ${n(y1)} C ${n(mx)} ${n(y1)}, ${n(mx)} ${n(y2)}, ${n(x2)} ${n(y2)}`;
  }
  const down = b.top >= a.bottom;
  const [x1, y1] = [midX(a), down ? a.bottom : a.top];
  const [x2, y2] = [midX(b), down ? b.top : b.bottom];
  const my = (y1 + y2) / 2;
  return `M ${n(x1)} ${n(y1)} C ${n(x1)} ${n(my)}, ${n(x2)} ${n(my)}, ${n(x2)} ${n(y2)}`;
}

/** Room left between a figure and the box drawn round it, in px. */
const PAD = 3;

/** A box round the figure, or a line under it, drawn from the inline-start side: the left in English, the right
 * in Arabic, so the pen moves the way the engineer reads. */
export function markPath(r: DOMRect, shape: "box" | "underline", direction: "ltr" | "rtl"): string {
  const rtl = direction === "rtl";
  if (shape === "underline") {
    const y = r.bottom + 2;
    return `M ${n(rtl ? r.right : r.left)} ${n(y)} H ${n(rtl ? r.left : r.right)}`;
  }
  const [start, end] = rtl ? [r.right + PAD, r.left - PAD] : [r.left - PAD, r.right + PAD];
  return `M ${n(start)} ${n(r.top - PAD)} H ${n(end)} V ${n(r.bottom + PAD)} H ${n(start)} Z`;
}
