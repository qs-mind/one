// A soft wipe for a change of the whole page, such as the language (docs/specs/2026-11-05-motion-design.md, 2.7):
// the new page spreads in a circle from the button that asked for it, over the old one. View Transitions where the
// webview has them (WebView2; WebKit from Safari 18's engine); elsewhere the page cross-fades. With reduced motion
// the page simply changes, and a wipe already running when it is turned on ends at once.
import { flushSync } from "react-dom";
import { DUR, EASE, play, reducedMotion } from "./motion";

export type Point = { x: number; y: number };

/** The middle of an element, in window coordinates: the same on an Arabic page, so nothing mirrors twice. */
export function centreOf(el: Element): Point {
  const rect = el.getBoundingClientRect();
  return { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 };
}

type ViewTransition = { ready: Promise<void>; finished: Promise<void>; skipTransition(): void };
type Starts = { startViewTransition?: (update: () => void) => ViewTransition };

/** Runs `update` (it changes the page at once) with the wipe from `from`, the middle of the window by default. */
export async function withTransition(update: () => void, from?: Point): Promise<void> {
  if (reducedMotion()) return update();
  const start = (document as Starts).startViewTransition;
  if (typeof start !== "function") {
    update();
    const root = document.getElementById("root");
    if (root) await play(root, [{ opacity: 0 }, { opacity: 1 }], DUR.short);
    return;
  }

  const { x, y } = from ?? { x: innerWidth / 2, y: innerHeight / 2 };
  const radius = Math.hypot(Math.max(x, innerWidth - x), Math.max(y, innerHeight - y));
  const html = document.documentElement;
  html.classList.add("lang-wipe"); // styles.css: no default cross-fade for this transition
  const transition = start.call(document, () => flushSync(update));
  const query = typeof matchMedia === "function" ? matchMedia("(prefers-reduced-motion: reduce)") : undefined;
  const skip = () => query?.matches && transition.skipTransition();
  query?.addEventListener("change", skip);
  try {
    await transition.ready;
    html.animate(
      { clipPath: [`circle(0px at ${x}px ${y}px)`, `circle(${radius}px at ${x}px ${y}px)`] },
      { duration: DUR.long, easing: EASE, pseudoElement: "::view-transition-new(root)" },
    );
    await transition.finished;
  } catch {
    // skipped: the page has already changed
  } finally {
    query?.removeEventListener("change", skip);
    html.classList.remove("lang-wipe");
  }
}
