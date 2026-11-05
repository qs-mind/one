// Warm tooltips for icon buttons: the first one waits about half a second, so passing over a toolbar shows nothing;
// once one has shown, the next opens at once, until 300 ms after the pointer left the last one. A tip opens at once on
// keyboard focus, closes on a press, on Escape and on leaving. It is for the eye: the button keeps its own aria-label,
// so the tip is hidden from screen readers rather than read twice. Ink on Paper, a 150 ms fade (none with reduced
// motion), drawn at the page's end so a frame's edge never cuts it.
import { type ReactElement, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { dir } from "../i18n";
import { useReducedMotion } from "./motion";

export const TIP_DELAY = 500;
export const TIP_WARM = 300;

// One warmth for the whole window: neighbouring buttons sit a few pixels apart, so leaving one toolbar is leaving the
// group, and 300 ms later the wait comes back.
let warm = false;
let cooling: ReturnType<typeof setTimeout> | undefined;

type Shown = { left: number; top: number; above: boolean };

export function Tip({ label, side = "bottom", children }: { label: string; side?: "top" | "bottom"; children: ReactElement }) {
  const wrap = useRef<HTMLSpanElement>(null);
  const wait = useRef<ReturnType<typeof setTimeout>>(undefined);
  const [shown, setShown] = useState<Shown | null>(null);
  const reduced = useReducedMotion();

  useEffect(() => () => clearTimeout(wait.current), []);

  function open() {
    const trigger = wrap.current?.firstElementChild;
    if (!trigger) return;
    const rect = trigger.getBoundingClientRect();
    const above = side === "top" || rect.bottom + 40 > innerHeight;
    const left = Math.min(Math.max(rect.left + rect.width / 2, 8), innerWidth - 8);
    setShown({ left, top: above ? rect.top - 6 : rect.bottom + 6, above });
    warm = true;
    clearTimeout(cooling);
  }

  function enter() {
    clearTimeout(cooling);
    clearTimeout(wait.current);
    if (warm) open();
    else wait.current = setTimeout(open, TIP_DELAY);
  }

  function leave() {
    clearTimeout(wait.current);
    setShown(null);
    if (!warm) return;
    clearTimeout(cooling);
    cooling = setTimeout(() => (warm = false), TIP_WARM);
  }

  function close() {
    clearTimeout(wait.current);
    setShown(null);
  }

  const keyboard = (el: Element) => {
    try {
      return el.matches(":focus-visible");
    } catch {
      return false;
    }
  };

  return (
    <span
      ref={wrap}
      className="contents"
      onPointerEnter={enter}
      onPointerLeave={leave}
      onPointerDown={close}
      onFocus={(event) => keyboard(event.target) && open()}
      onBlur={leave}
      onKeyDown={(event) => event.key === "Escape" && shown && close()}
    >
      {children}
      {shown &&
        createPortal(
          <div
            role="tooltip"
            aria-hidden="true"
            dir={dir()}
            style={{ left: shown.left, top: shown.top, transform: `translate(-50%, ${shown.above ? "-100%" : "0"})` }}
            className={`${reduced ? "" : "tip-in"} pointer-events-none fixed z-50 whitespace-nowrap rounded-md bg-ink px-2 py-1 text-xs text-paper`}
          >
            {label}
          </div>,
          document.body,
        )}
    </span>
  );
}
