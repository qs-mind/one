// The source mark: when a source opens, a Copper ink box (or underline) draws round the exact figure, from the
// inline-start side (the right in Arabic), and fades after about 1.5 s; the row it stands in flashes Stone. With
// reduced motion the mark and the flash show whole at once and go at once.
import { DUR, play, reducedMotion } from "../ui/motion";
import { markPath, visibleRect } from "./geometry";
import { rectShape, stroke } from "./overlay";
import { trackRects } from "./rects";
import { elementsFor } from "./targets";

const COPPER = "var(--color-copper, #a6491b)";
const STONE = "var(--color-stone, #f2eee7)";
/** How long the mark stays before it fades. */
export const MARK_HOLD_MS = 1500;
/** How long a source that is opening (a canvas frame gliding there, a file's text loading) is waited for. */
export const REVEAL_WAIT_MS = 2000;

const wait = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));
const nextFrame = () =>
  new Promise<void>((resolve) => (typeof requestAnimationFrame === "function" ? requestAnimationFrame(() => resolve()) : setTimeout(resolve, 16)));

/** The direction the words round `el` are read in: a number isolated left to right (`<bdi dir="ltr">`) inside an
 * Arabic row is read in the row's direction. */
export function readingDirection(el: Element): "rtl" | "ltr" {
  for (let up: Element | null = el; up; up = up.parentElement) {
    const d = up.getAttribute("dir");
    if (up.tagName !== "BDI" && (d === "rtl" || d === "ltr")) return d;
  }
  return document.documentElement.dir === "rtl" ? "rtl" : "ltr";
}

/** Where `figure` is written inside `el` (the first time), or null: the box goes round the figure, not its row. */
function figureRect(el: Element, figures: string[]): DOMRect | null {
  if (!figures.length || typeof document.createRange !== "function") return null;
  const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    const text = node.textContent ?? "";
    for (const figure of figures) {
      const at = figure ? text.indexOf(figure) : -1;
      if (at < 0) continue;
      const range = document.createRange();
      range.setStart(node, at);
      range.setEnd(node, at + figure.length);
      const r = typeof range.getBoundingClientRect === "function" ? range.getBoundingClientRect() : null;
      if (r && r.width > 0 && r.height > 0) return r;
    }
  }
  return null;
}

let last: (() => void) | null = null; // a newer mark takes over at once

export type MarkOptions = {
  shape?: "box" | "underline";
  /** The figure as it may be written inside `el` (e.g. "39,850.50", "39850.50"): the box goes round it alone. */
  figures?: string[];
  /** The row to flash Stone. */
  row?: Element | null;
};

/** Marks `el`; resolves once the mark has gone. Nothing is drawn for an element off screen. */
export async function markSource(el: Element, { shape = "box", figures = [], row = null }: MarkOptions = {}): Promise<void> {
  last?.();
  const visible = visibleRect(el);
  if (!visible) return;
  const direction = readingDirection(el);
  const box = () => {
    const shown = visibleRect(el);
    const exact = shown && figureRect(el, figures);
    return exact ?? shown;
  };
  const first = box() ?? visible;
  const pen = stroke(markPath(first, shape, direction), COPPER, 1.5, "mark");
  const shownRow = row && visibleRect(row);
  const flash = shownRow ? rectShape(shownRow, STONE, "flash") : null;
  const stop = trackRects([el, ...(row ? [row] : [])], () => {
    const now = box();
    pen.style.visibility = now ? "" : "hidden";
    if (now) pen.setAttribute("d", markPath(now, shape, direction));
    const r = row && visibleRect(row);
    if (flash && r) for (const [k, v] of Object.entries({ x: r.left, y: r.top, width: r.width, height: r.height })) flash.setAttribute(k, String(v));
  });
  let gone = false;
  const remove = () => {
    if (gone) return;
    gone = true;
    stop();
    pen.remove();
    flash?.remove();
    if (last === remove) last = null;
  };
  last = remove;

  if (reducedMotion()) {
    await wait(MARK_HOLD_MS);
    return remove();
  }
  void play(pen, [{ strokeDashoffset: 1 }, { strokeDashoffset: 0 }], DUR.roll);
  if (flash) void play(flash, [{ opacity: 0 }, { opacity: 1 }], DUR.base);
  await wait(MARK_HOLD_MS);
  if (gone) return;
  for (const shape of [pen, flash]) if (shape) shape.style.opacity = "0";
  await Promise.all([pen, flash].map((shape) => shape && play(shape, [{ opacity: 1 }, { opacity: 0 }], DUR.long)));
  remove();
}

/** Keys a mark can go round: a cell, a file's sheet row or line, a chip. Not a whole frame (the canvas marks that
 * itself), nor a PDF page: no place on a page is known yet. */
const markable = (key: string) => !/^file:[^#]+$/.test(key) && !/^file:[^#]+#page=[^&]+$/.test(key);

/** After a source is opened: waits for it to show (the canvas gliding to its frame, its text loading), then marks
 * it and flashes its row. Resolves false when there was nothing to mark. */
export async function revealSource(keys: string[], figures: string[] = []): Promise<boolean> {
  const wanted = keys.filter(markable);
  if (!wanted.length) return false;
  const started = Date.now();
  let el: HTMLElement | undefined;
  while (!el) {
    el = wanted.map((k) => elementsFor(k)[0]).find(Boolean);
    if (el || Date.now() - started > REVEAL_WAIT_MS) break;
    await nextFrame();
  }
  if (!el) return false;
  if (!el.closest(".react-flow")) el.scrollIntoView?.({ block: "nearest", inline: "nearest" }); // the canvas moves itself
  // still moving (the canvas's view gliding): marked once it has stopped
  let before = el.getBoundingClientRect();
  for (let i = 0; i < 60; i++) {
    await nextFrame();
    const now = el.getBoundingClientRect();
    if (now.left === before.left && now.top === before.top && now.width === before.width) break;
    before = now;
  }
  const row = el.closest('[role="row"]') ?? (el.tagName === "LI" ? el : null);
  void markSource(el, { figures, row });
  return true;
}
