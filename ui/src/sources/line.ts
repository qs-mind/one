// The source line: hovering or focusing a number that has a source draws one thin Ink line, once, from the number to
// where its source shows (a row in a sheet frame, a PDF page or drawing on the canvas, a source chip). Only when both
// are on screen: otherwise nothing is drawn. It follows scrolling and resizing, and fades when the pointer or focus
// leaves. With reduced motion the line shows whole at once and goes at once.
import type { FocusEvent, PointerEvent } from "react";
import { DUR, play, reducedMotion } from "../ui/motion";
import { linePath, visibleRect } from "./geometry";
import { stroke } from "./overlay";
import { trackRects } from "./rects";
import { findTarget } from "./targets";

const INK = "var(--color-ink, #0e0f12)";

type Shown = { from: Element; path: SVGPathElement; stop: () => void };
let shown: Shown | null = null;

/** Draws the line from `from` to the first on-screen element for `keys`. False when nothing was drawn. */
export function showSourceLine(from: Element, keys: string[]): boolean {
  hideSourceLine();
  if (!keys.length) return false;
  const a = visibleRect(from);
  const target = a && findTarget(keys, from, (el) => visibleRect(el) !== null);
  const b = target && visibleRect(target);
  if (!a || !target || !b) return false;
  const path = stroke(linePath(a, b), INK, 1, "line");
  if (!reducedMotion()) void play(path, [{ strokeDashoffset: 1 }, { strokeDashoffset: 0 }], DUR.long);
  const stop = trackRects([from, target], () => {
    const [x, y] = [visibleRect(from), visibleRect(target)];
    path.style.visibility = x && y ? "" : "hidden"; // scrolled away: nothing shows until it is back
    if (x && y) path.setAttribute("d", linePath(x, y));
  });
  shown = { from, path, stop };
  return true;
}

/** Takes the line away (only `from`'s, when given). */
export function hideSourceLine(from?: Element): void {
  if (!shown || (from && shown.from !== from)) return;
  const { path, stop } = shown;
  shown = null;
  stop();
  if (reducedMotion()) return path.remove();
  path.style.opacity = "0";
  void play(path, [{ opacity: 1 }, { opacity: 0 }], DUR.short).then(() => path.remove());
}

/** The handlers a number with a source spreads onto its element; none for a number with no source. */
export function sourceLineHandlers(keys: string[]) {
  if (!keys.length) return {};
  return {
    onPointerEnter: (event: PointerEvent<Element>) => void showSourceLine(event.currentTarget, keys),
    onPointerLeave: (event: PointerEvent<Element>) => hideSourceLine(event.currentTarget),
    onFocus: (event: FocusEvent<Element>) => void showSourceLine(event.currentTarget, keys),
    onBlur: (event: FocusEvent<Element>) => hideSourceLine(event.currentTarget),
  };
}
