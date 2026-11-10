// ONE's one size scale: the root font-size follows the window, so every rem-based size (Tailwind's text, spacing,
// radii, the top bar, the chat, the sheet's rows) grows and shrinks together. At a window of 1920×1000 or larger every
// size is what it was at 100 % (no growth on huge screens); between 1280 and 1920 wide, and 650 and 1000 tall, it
// scales linearly down to 80 %, by the smaller of the two, so a short window shrinks too; below that it stays at
// 80 %. The heights are the window's, not the screen's: a maximised window on a 1080p screen is about 1009 px tall
// (taskbar and title bar) and is 100 %; one on a 1366×768 screen (about 698 px) is at about its width's scale. Text has a floor: body text never under 12.5 px in English or 13.5 px in Arabic (its dots and marks), so
// every text size stops shrinking at that ratio (styles.css --ui-text-floor). The engineer's own zoom, 80 % to 150 % in
// 10 % steps, is the setting look.zoom (Settings → Look, or Ctrl/Cmd with = - 0): kept in the core, never in web
// storage, read before the screen opens (settings/look.ts), and in the new interface it alone sets the root size.
import { useEffect, useSyncExternalStore } from "react";
import { send } from "../core";
import { type Language, useLanguage } from "../i18n";
import { isMod, isTyping } from "../project/keys";

/** The window at which (and above which) every size is 100 %. */
export const FULL = { width: 1920, height: 1000 };
/** The window at which (and below which) every size is SMALLEST. */
export const SMALL = { width: 1280, height: 650 };
export const SMALLEST = 0.8;
/** The engineer's zoom steps: 80 % to 150 %. */
export const ZOOMS = [0.8, 0.9, 1, 1.1, 1.2, 1.3, 1.4, 1.5] as const;
/** Body text is 14 px (English) / 15 px (Arabic) at 100 %; it never goes under 12.5 / 13.5 px. */
export const TEXT_FLOOR: Record<Language, number> = { en: 12.5 / 14, ar: 13.5 / 15 };

const along = (size: number, small: number, full: number) =>
  SMALLEST + (1 - SMALLEST) * Math.min(1, Math.max(0, (size - small) / (full - small)));

/** The window's scale: 1 at 1920×1000 and up, 0.8 at 1280×650 and down, the smaller of width's and height's. */
export function fluidScale(width: number, height: number): number {
  return Math.min(along(width, SMALL.width, FULL.width), along(height, SMALL.height, FULL.height));
}

/** The scale text is drawn at: the screen's, but never under the language's floor. */
export function textScale(scale: number, lang: Language): number {
  return Math.max(scale, TEXT_FLOOR[lang]);
}

/** The zoom step `by` steps from `zoom` (−1 smaller, +1 larger), kept within the steps. */
export function stepZoom(zoom: number, by: -1 | 1): number {
  const at = nearest(zoom);
  return ZOOMS[Math.min(ZOOMS.length - 1, Math.max(0, ZOOMS.indexOf(at) + by))]!;
}

function nearest(zoom: number): (typeof ZOOMS)[number] {
  return ZOOMS.reduce((best, z) => (Math.abs(z - zoom) < Math.abs(best - zoom) ? z : best), 1 as (typeof ZOOMS)[number]);
}

let zoom = 1;
let scale = 1; // the root's: the window's times the zoom
const listeners = new Set<() => void>();

/** The screen's scale now (the root font-size over 16 px). */
export function currentScale(): number {
  return scale;
}

/** `px` at 100 %, as drawn now: for sizes kept in code (a card's tallest, a popover's width). */
export function scaled(px: number): number {
  return px * scale;
}

export function currentZoom(): number {
  return zoom;
}

/** Sets the root font-size for this window and zoom; the screen re-measures what it sized in code. */
export function applyScale(width = window.innerWidth, height = window.innerHeight) {
  const next = Math.round(fluidScale(width, height) * zoom * 10_000) / 10_000;
  document.documentElement.style.fontSize = `${16 * next}px`;
  if (next === scale) return;
  scale = next;
  for (const listener of [...listeners]) listener();
}

/** At start, before the first paint: the window's scale now, and again whenever the window changes size. */
export function installScale(): () => void {
  applyScale();
  let frame = 0;
  const onResize = () => {
    cancelAnimationFrame(frame);
    frame = requestAnimationFrame(() => applyScale());
  };
  window.addEventListener("resize", onResize);
  return () => {
    cancelAnimationFrame(frame);
    window.removeEventListener("resize", onResize);
  };
}

/** The zoom as the look.zoom setting has it (settings/look.ts): the root size, and the sizes kept in code, follow. */
export function followZoom(next: number) {
  const step = nearest(next);
  document.documentElement.style.fontSize = `${Math.round(step * 100)}%`; // 1.1 is 110%, not 110.00000000000001%
  if (step === zoom && step === scale) return;
  zoom = step;
  scale = step;
  for (const listener of [...listeners]) listener();
}

let saving = false; // a save in flight
let unsaved: number | undefined; // the newest zoom not sent yet

/** Saves the zoom in order: one save in flight, then only the newest, so fast presses never leave an older one. */
async function save(step: number) {
  unsaved = step;
  if (saving) return;
  saving = true;
  while (unsaved !== undefined) {
    const next = unsaved;
    unsaved = undefined;
    await send("/settings/look.zoom", "PATCH", { value: next.toFixed(1) });
  }
  saving = false;
}

/** The engineer's zoom: shown at once and kept in the core as look.zoom (a failed save keeps it for this session). */
export function setZoom(next: number) {
  const step = nearest(next);
  if (step === zoom) return;
  followZoom(step);
  void save(step);
}

export const zoomIn = () => setZoom(stepZoom(zoom, 1));
export const zoomOut = () => setZoom(stepZoom(zoom, -1));
export const resetZoom = () => setZoom(1);

// by KeyboardEvent.code, so the Arabic layout zooms too: = (and +, Shift with it), -, 0, and the keypad's
const ZOOM_KEYS: Record<string, () => void> = {
  Equal: zoomIn,
  NumpadAdd: zoomIn,
  Minus: zoomOut,
  NumpadSubtract: zoomOut,
  Digit0: resetZoom,
  Numpad0: resetZoom,
};

/** Ctrl (Cmd on a Mac) with = or + zooms in, with - out, with 0 back to 100 %; never while typing in a field. */
export function onZoomKey(event: KeyboardEvent) {
  const act = ZOOM_KEYS[event.code];
  if (!act || !isMod(event) || event.altKey || event.defaultPrevented || isTyping(event.target)) return;
  event.preventDefault(); // not the webview's own zoom
  act();
}

/** The zoom keys, while the screen is open. */
export function useZoomKeys() {
  useEffect(() => {
    document.addEventListener("keydown", onZoomKey);
    return () => document.removeEventListener("keydown", onZoomKey);
  }, []);
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => void listeners.delete(listener);
}

/** The screen's scale, re-rendering when it changes. */
export function useScale(): number {
  return useSyncExternalStore(subscribe, currentScale);
}

export function useZoom(): number {
  return useSyncExternalStore(subscribe, currentZoom);
}

/** The two scales a size kept in code needs: `space` for room (padding, row padding, widths), `text` for type. */
export function useSizes(): { space: number; text: number } {
  const space = useScale();
  const lang = useLanguage();
  return { space, text: textScale(space, lang) };
}

/** For the tests: 100 %, no zoom. */
export function resetScale() {
  zoom = 1;
  scale = 1;
  saving = false;
  unsaved = undefined;
  document.documentElement.style.fontSize = "";
  for (const listener of [...listeners]) listener();
}
