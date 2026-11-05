// A scroll area fades at its top or bottom only while there is more to see that way (docs/specs/2026-11-05-motion-design.md,
// motion 1). The hook marks the area with data-more-top / data-more-bottom from its scroll position and sizes; the
// `.scroll-fade` class in styles.css draws the fade. Read on scroll and when the area or its content changes size,
// so nothing runs while the area sits still.
import { type RefObject, useEffect, useRef } from "react";

/** Under this height an area keeps no fade: two 24 px fades would hide its only line. */
const SHORTEST = 72;

function watch(el: HTMLElement): () => void {
  const update = () => {
    const fades = el.clientHeight >= SHORTEST;
    el.toggleAttribute("data-more-top", fades && el.scrollTop > 1);
    el.toggleAttribute("data-more-bottom", fades && el.scrollHeight - el.clientHeight - el.scrollTop > 1);
  };
  update();
  el.addEventListener("scroll", update, { passive: true });

  // the area's own size, and its content's: each child, including those added later
  const sizes = typeof ResizeObserver === "undefined" ? undefined : new ResizeObserver(update);
  const observe = () => {
    sizes?.observe(el);
    for (const child of el.children) sizes?.observe(child);
  };
  observe();
  const children = typeof MutationObserver === "undefined" ? undefined : new MutationObserver(() => (observe(), update()));
  children?.observe(el, { childList: true });

  return () => {
    el.removeEventListener("scroll", update);
    sizes?.disconnect();
    children?.disconnect();
  };
}

/** Marks `ref`'s scroll area with the edges that have more beyond them. The area may appear, change or leave after
 * the first render (a list shown once it has loaded): each render checks it is still the one watched. */
export function useScrollEdges(ref: RefObject<HTMLElement | null>): void {
  const watched = useRef<{ el: HTMLElement; stop: () => void } | undefined>(undefined);
  useEffect(() => {
    const el = ref.current;
    if (watched.current?.el === el) return;
    watched.current?.stop();
    watched.current = el ? { el, stop: watch(el) } : undefined;
  });
  useEffect(
    () => () => {
      watched.current?.stop();
      watched.current = undefined;
    },
    [],
  );
}
