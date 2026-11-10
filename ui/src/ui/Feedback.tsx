// A check's, a sign-in's or a save's line in the kept engines (ui/live.tsx SaveNote, a cap card's amounts). Moved here
// from the old first launch, which the new one replaced.
import { type ReactNode, useEffect, useRef } from "react";
import { InkCheck } from "./InkCheck";
import { WorkDots } from "./WorkDots";

export type Progress = "busy" | "done" | "failed";

/** How a check, a sign-in or a save is going, in the same look on every step, without a colour of its own: three
 * Slate dots fading in turn while it runs (shown after 300 ms, so a quick one never flashes); a filled Ink circle whose check
 * draws itself once it worked, the line in Ink; Copper with a ring and "!" when it did not, the line saying what to do
 * next. Each line rises into place, and scrolls into view when it lands below the window's edge. With `fade`, a done
 * line fades out after a moment, keeping its place (a quiet "Saved"). */
export function Feedback({ state, children, fade = false }: { state: Progress; children: ReactNode; fade?: boolean }) {
  const line = useRef<HTMLParagraphElement>(null);
  const shown = Boolean(children);
  useEffect(() => {
    if (!shown) return;
    const still = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    line.current?.scrollIntoView?.({ block: "nearest", behavior: still ? "auto" : "smooth" });
  }, [state, shown]);
  if (!shown) return null;
  const look = state === "done" ? "font-medium text-ink" : state === "failed" ? "text-copper" : "text-slate";
  return (
    <p
      ref={line}
      role={state === "failed" ? "alert" : "status"}
      data-feedback={state}
      // clear of the step's sticky bar and the fade above it, where the line it scrolled to was half hidden
      className={`${state === "busy" ? "fl-rise-late" : fade ? "fl-fade" : "fl-rise"} flex scroll-mb-32 items-start gap-2.5 ${look}`}
    >
      <span aria-hidden="true" className="flex h-[1lh] shrink-0 items-center">
        {state === "busy" && <WorkDots />}
        {state === "done" && <InkCheck />}
        {state === "failed" && (
          <svg viewBox="0 0 20 20" className="size-5">
            <circle cx="10" cy="10" r="9" fill="none" strokeWidth="1.5" className="stroke-copper" />
            <path d="M10 5.5v5.5" strokeWidth="2" strokeLinecap="round" className="stroke-copper" />
            <circle cx="10" cy="14.3" r="1.15" className="fill-copper" />
          </svg>
        )}
      </span>
      <span className="min-w-0">{children}</span>
    </p>
  );
}
