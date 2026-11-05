// What the sliding marks (TabUnderline, Segmented, Glide) share: where an item sits inside the box the mark moves in.
// Layout offsets, not screen rects, so a mark inside the zoomed canvas lands right at any zoom; and measured from the
// box's left edge in both directions, so in Arabic, where the first item is on the right, it lands right too.
import { reducedMotion } from "./motion";

export type Place = { x: number; y: number; w: number; h: number };

/** `item`'s place inside `box` (which must be positioned), however deep it sits. */
export function placeIn(item: HTMLElement, box: HTMLElement): Place {
  let x = 0;
  let y = 0;
  for (let el: HTMLElement | null = item; el && el !== box; el = el.offsetParent as HTMLElement | null) {
    x += el.offsetLeft;
    y += el.offsetTop;
  }
  return { x, y, w: item.offsetWidth, h: item.offsetHeight };
}

/** A mark shows its first place at once; from the next frame on it glides (CSS `[data-ready]`), unless motion is
 * reduced. Returns a cancel. */
export function readyNextFrame(mark: HTMLElement): () => void {
  if (mark.hasAttribute("data-ready") || reducedMotion()) return () => {};
  const frame = requestAnimationFrame(() => {
    if (!reducedMotion()) mark.setAttribute("data-ready", "");
  });
  return () => cancelAnimationFrame(frame);
}
