// The source mark: when a source opens, a Copper ink box (or underline) draws round the exact figure, from the
// inline-start side (the right in Arabic), and fades after 3 s; the row it stands in flashes Stone. With
// reduced motion the mark and the flash show whole at once and go at once.
import { DUR, play, reducedMotion } from "../ui/motion";
import { markPath, visibleRect } from "./geometry";
import { rectShape, stroke } from "./overlay";
import { trackRects } from "./rects";
import { elementsFor } from "./targets";

const COPPER = "var(--color-copper, #a6491b)";
const STONE = "var(--color-stone, #f2eee7)";
/** How long the mark stays before it fades. */
export const MARK_HOLD_MS = 3000;
/** How long a source that is opening (the document switching, a file's text loading) is waited for. */
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

/** Compare numeric spelling without arithmetic: grouped figures and zero decimal places name the same value. */
function numericText(text: string): string | null {
  const plain = text.replace(/[٠-٩]/g, (digit) => String(digit.charCodeAt(0) - 0x660))
    .replace(/[۰-۹]/g, (digit) => String(digit.charCodeAt(0) - 0x6f0))
    .replace(/[,٬]/g, "").replace(/٫/g, ".");
  if (!/^-?\d+(?:\.\d+)?$/.test(plain)) return null;
  return plain.replace(/(\.\d*?)0+$/, "$1").replace(/\.$/, "");
}

/** Match a whole numeric token, so 15 does not mark the 15 inside 115. */
function figureRange(el: Element, figures: string[]): Range | null {
  if (!figures.length || typeof document.createRange !== "function") return null;
  const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    const text = node.textContent ?? "";
    for (const figure of figures) {
      const numeric = numericText(figure);
      const match = numeric === null ? null : [...text.matchAll(/-?[0-9٠-٩۰-۹]+(?:[,٬.٫][0-9٠-٩۰-۹]+)*/g)]
        .find((part) => numericText(part[0]) === numeric);
      const at = match?.index ?? (numeric === null && figure ? text.indexOf(figure) : -1);
      if (at < 0) continue;
      const range = document.createRange();
      range.setStart(node, at);
      range.setEnd(node, at + (match?.[0].length ?? figure.length));
      return range;
    }
  }
  return null;
}

/** The figure's own box, retaining the original text's offsets and punctuation. */
function figureRect(el: Element, figures: string[]): DOMRect | null {
  const range = figureRange(el, figures);
  const rect = range && typeof range.getBoundingClientRect === "function" ? range.getBoundingClientRect() : null;
  return rect && rect.width > 0 && rect.height > 0 ? rect : null;
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
  const pen = stroke(markPath(first, shape, direction), COPPER, 2, "mark");
  // Use a solid stroke so visibility does not depend on normalized SVG dash animation in WebKitGTK.
  pen.style.strokeDasharray = "none";
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
  if (flash) void play(flash, [{ opacity: 0 }, { opacity: 1 }], DUR.base);
  await wait(MARK_HOLD_MS);
  if (gone) return;
  for (const shape of [pen, flash]) if (shape) shape.style.opacity = "0";
  await Promise.all([pen, flash].map((shape) => shape && play(shape, [{ opacity: 1 }, { opacity: 0 }], DUR.long)));
  remove();
}

/** Keys a mark can go round: a cell, a file's sheet row or line, a chip. Not a whole file, nor a PDF page: no place on a page is known yet. */
const markable = (key: string) => !/^file:[^#]+$/.test(key) && !isPage(key);
/** A PDF page's key: the page shown is the source found, though nothing on it can be marked. */
const isPage = (key: string) => /^file:[^#]+#page=[^&]+$/.test(key);
const shown = (keys: string[]) => keys.map((k) => elementsFor(k)[0]).find(Boolean);

/** After a source is opened: waits for it to show (the document switching, its text loading), then marks
 * it and flashes its row. Resolves false when it was not found: a page-level source counts as found once its page
 * shows (nothing is marked on it). */
export async function revealSource(keys: string[], figures: string[] = []): Promise<boolean> {
  const wanted = keys.filter(markable);
  const pages = keys.filter(isPage);
  if (!wanted.length && !pages.length) return false;
  const started = Date.now();
  let el: HTMLElement | undefined;
  while (!el) {
    el = shown(wanted);
    if (el || Date.now() - started > REVEAL_WAIT_MS) break;
    if (!wanted.length && shown(pages)) return true; // only its page is known: there it is
    await nextFrame();
  }
  if (!el) return !!shown(pages);
  // A raw file registers its row on the first cell. Search the row for the cited figure
  // before scrolling, otherwise the mark can land on A while the source is in H.
  const inRow = el.closest('[role="row"]') ?? el;
  const figure = figureRange(inRow, figures);
  const figureElement = figure?.startContainer.parentElement;
  if (figureElement) el = figureElement;
  el.scrollIntoView?.({ block: "center", inline: "center" });
  // still moving (scrolling into view): marked once it has stopped
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
