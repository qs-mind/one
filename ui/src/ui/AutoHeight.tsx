// A card whose content changes height eases to the new height (docs/specs/2026-11-05-motion-design.md, motion 6):
// 220 ms, so what sits under it glides instead of jumping. The content is measured as it is laid out, before the
// frame is drawn, so the old height holds from the first frame. It clips only while it moves, so focus rings at its
// edges show at rest. With reduced motion it takes the new height at once.
import { type ReactNode, useEffect, useRef } from "react";
import { DUR, play } from "./motion";

export function AutoHeight({ children, className = "" }: { children: ReactNode; className?: string }) {
  const outer = useRef<HTMLDivElement>(null);
  const inner = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const box = outer.current;
    const content = inner.current;
    if (!box || !content || typeof ResizeObserver === "undefined") return;
    let last: number | undefined;
    let moving = 0;
    const observer = new ResizeObserver(([entry]) => {
      const height = entry?.borderBoxSize?.[0]?.blockSize ?? entry?.contentRect.height ?? content.offsetHeight;
      // mid-move, from the height it shows now
      const from = moving ? box.getBoundingClientRect().height : last;
      last = height;
      if (from === undefined || Math.abs(from - height) < 0.5) return;
      for (const running of box.getAnimations?.() ?? []) running.cancel();
      const mine = ++moving;
      box.style.overflow = "clip";
      void play(box, [{ height: `${from}px` }, { height: `${height}px` }], DUR.base).then(() => {
        if (mine !== moving) return;
        moving = 0;
        box.style.overflow = "";
      });
    });
    observer.observe(content);
    return () => observer.disconnect();
  }, []);

  return (
    <div ref={outer}>
      <div ref={inner} className={className}>
        {children}
      </div>
    </div>
  );
}
