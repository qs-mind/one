// A card whose content changes height eases to the new height (docs/specs/2026-11-05-motion-design.md, motion 6):
// 220 ms, so what sits under it glides instead of jumping. It clips only while it moves, so focus rings at its edges
// show at rest. With reduced motion it takes the new height at once.
//
// A change in the content (a line added or taken out) is seen as it is made, before the frame is laid out, and the
// motion starts from there, so the old height holds from the first frame. Starting it from a ResizeObserver instead
// would resize the card inside the observers' turn, and a scroll area watching the card (useScrollEdges) would report
// a ResizeObserver loop. Sizes that change with no change in the content (a narrower window, a font that came) are
// only noted, by a ResizeObserver, and simply show.
import { type ReactNode, useEffect, useRef } from "react";
import { DUR, play } from "./motion";

export function AutoHeight({ children, className = "" }: { children: ReactNode; className?: string }) {
  const outer = useRef<HTMLDivElement>(null);
  const inner = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const box = outer.current;
    const content = inner.current;
    if (!box || !content) return;
    const measure = () => content.getBoundingClientRect().height;
    let last = measure();
    let moving = 0;

    const changed = () => {
      const height = measure();
      const from = moving ? box.getBoundingClientRect().height : last; // mid-move, from the height it shows now
      last = height;
      if (Math.abs(from - height) < 0.5) return;
      for (const running of box.getAnimations?.() ?? []) running.cancel();
      const mine = ++moving;
      box.style.overflow = "clip";
      void play(box, [{ height: `${from}px` }, { height: `${height}px` }], DUR.base).then(() => {
        if (mine !== moving) return;
        moving = 0;
        box.style.overflow = "";
      });
    };
    const edits = typeof MutationObserver === "undefined" ? undefined : new MutationObserver(changed);
    edits?.observe(content, { childList: true, subtree: true, characterData: true });
    const sizes = typeof ResizeObserver === "undefined" ? undefined : new ResizeObserver(() => !moving && (last = measure()));
    sizes?.observe(content);
    return () => {
      edits?.disconnect();
      sizes?.disconnect();
    };
  }, []);

  return (
    <div ref={outer}>
      <div ref={inner} className={className}>
        {children}
      </div>
    </div>
  );
}
