// One floating panel under the top bar at the inline start, for the panels that already exist (AI settings,
// Projects, Project Records, the Project Index), kept as they are. Focus goes into it when it opens; Esc closes it
// (the shell then gives focus back to the button that opened it). A click outside closes it too, but only one that
// both starts and ends outside: selecting text or dragging from inside out past its edge keeps it open. That close
// says "outside", so focus stays where the engineer clicked.
import { type ReactNode, useEffect, useRef } from "react";
import { useScrollEdges } from "../ui/useScrollEdges";

/** `wide`: a panel with a table (the Project Index), so its columns and titles have room. `narrow`: a short list (the
 * projects), under the button that opened it. */
export function FloatingPanel({
  onClose,
  wide = false,
  narrow = false,
  children,
}: {
  onClose: (how?: "outside") => void;
  wide?: boolean;
  narrow?: boolean;
  children: ReactNode;
}) {
  const box = useRef<HTMLDivElement>(null);
  const scroller = useRef<HTMLDivElement>(null);
  const startedInside = useRef(false);
  const close = useRef(onClose);
  close.current = onClose;
  useScrollEdges(scroller);

  useEffect(() => {
    // a panel that moves focus itself (Projects focuses the open project) keeps it
    if (!box.current?.contains(document.activeElement)) box.current?.focus();
  }, []);

  useEffect(() => {
    // The page's capture listeners run first: a press starts outside unless the panel's own handler (which also hears
    // presses in menus it opened, drawn elsewhere on the page) says it started inside. The click is judged before the
    // button under it acts, so a top bar button that opens another panel still opens it.
    const down = () => void (startedInside.current = false);
    const click = (event: MouseEvent) => {
      if (event.detail === 0) return; // Enter or Space on a button: not a click of the pointer
      if (startedInside.current || box.current?.contains(event.target as Node)) return;
      close.current("outside");
    };
    document.addEventListener("pointerdown", down, true);
    document.addEventListener("click", click, true);
    return () => {
      document.removeEventListener("pointerdown", down, true);
      document.removeEventListener("click", click, true);
    };
  }, []);

  return (
    <div
      ref={box}
      tabIndex={-1}
      onPointerDownCapture={() => void (startedInside.current = true)}
      onKeyDown={(event) => {
        if (event.key !== "Escape" || event.defaultPrevented) return;
        event.preventDefault();
        onClose();
      }}
      className={`absolute start-4 top-2 z-30 flex max-h-[calc(100%-16px)] ${wide ? "w-[min(760px,calc(100%-32px))]" : narrow ? "w-[min(320px,calc(100%-32px))]" : "w-[min(420px,calc(100%-32px))]"} flex-col overflow-hidden rounded-[14px] border border-ink/10 bg-paper shadow-[0_2px_10px_rgb(14_15_18/0.12)] outline-none`}
    >
      {/* the scrolling part fades at its edges inside the panel's frame, so the frame and its shadow stay whole */}
      <div ref={scroller} className="scroll-fade min-h-0 overflow-y-auto">
        {children}
      </div>
    </div>
  );
}
