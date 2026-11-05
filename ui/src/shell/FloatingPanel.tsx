// One floating panel under the top bar at the inline start, for the panels that already exist (AI settings,
// Projects, Project Records, the Project Index), kept as they are. Focus goes into it when it opens; Esc closes it
// (the shell then gives focus back to the button that opened it).
import { type ReactNode, useEffect, useRef } from "react";
import { useScrollEdges } from "../ui/useScrollEdges";

export function FloatingPanel({ onClose, children }: { onClose: () => void; children: ReactNode }) {
  const box = useRef<HTMLDivElement>(null);
  const scroller = useRef<HTMLDivElement>(null);
  useScrollEdges(scroller);

  useEffect(() => {
    // a panel that moves focus itself (Projects focuses the open project) keeps it
    if (!box.current?.contains(document.activeElement)) box.current?.focus();
  }, []);

  return (
    <div
      ref={box}
      tabIndex={-1}
      onKeyDown={(event) => {
        if (event.key !== "Escape" || event.defaultPrevented) return;
        event.preventDefault();
        onClose();
      }}
      className="absolute start-4 top-2 z-30 flex max-h-[calc(100%-16px)] w-[min(420px,calc(100%-32px))] flex-col overflow-hidden rounded-[14px] border border-ink/10 bg-paper shadow-[0_2px_10px_rgb(14_15_18/0.12)] outline-none"
    >
      {/* the scrolling part fades at its edges inside the panel's frame, so the frame and its shadow stay whole */}
      <div ref={scroller} className="scroll-fade min-h-0 overflow-y-auto">
        {children}
      </div>
    </div>
  );
}
