// FLIP: an element that has just moved (a number into its source card's header) starts where it was and glides to
// where it is now. Positions are real screen positions, lined up on the inline-start edge, so it works the same in
// Arabic and English and inside a CSS-scaled canvas frame.
import { DUR, play } from "../ui/motion";

/** Plays `el` from the box `from` to its own box now. */
export function flipFrom(from: DOMRect, el: HTMLElement, direction: "rtl" | "ltr"): Promise<void> {
  const to = el.getBoundingClientRect();
  if (!from.width || !from.height || !to.width || !to.height) return Promise.resolve();
  const zoom = el.offsetWidth ? to.width / el.offsetWidth : 1; // a canvas frame's scale: a transform is in its pixels
  const rtl = direction === "rtl";
  const dx = (rtl ? from.right - to.right : from.left - to.left) / zoom;
  const dy = (from.top - to.top) / zoom;
  const scale = from.height / to.height;
  el.style.transformOrigin = rtl ? "top right" : "top left";
  return play(el, [{ transform: `translate(${dx}px, ${dy}px) scale(${scale})` }, { transform: "none" }], DUR.long);
}
