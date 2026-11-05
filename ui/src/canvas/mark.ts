// The frame the view was sent to from elsewhere (a Deliverable card's Open in the chat) says "here": a soft Ink outline
// round it while the view glides there, fading once it has arrived. No glow, no shadow. With reduced motion the view
// jumps and the outline shows still for a moment, then goes at once.
import { DUR, play, reducedMotion } from "../ui/motion";
import type { FrameKey } from "./types";

const SOFT_INK = "rgb(14 15 18 / 0.45)";
const CLEAR_INK = "rgb(14 15 18 / 0)";
/** How long the still outline stays with reduced motion. */
export const STILL_MARK_MS = 1200;
/** Frames given to a frame scrolled into view to be drawn (the canvas draws only the frames in view). */
const FRAMES_TO_DRAW = 30;

const nextFrame = () => new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
const wait = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));
let last = 0;

/** Marks the frame `key`; `glide` is how long the view takes to get there, in ms. */
export async function markFrame(key: FrameKey, glide: number): Promise<void> {
  const mine = ++last; // a newer mark takes over
  const started = performance.now();
  const find = () => document.querySelector<HTMLElement>(`[data-frame="${CSS.escape(key)}"]`);
  let el = find();
  for (let i = 0; !el && i < FRAMES_TO_DRAW; i++) {
    await nextFrame();
    el = find();
  }
  if (!el || mine !== last) return;
  const own = String(mine);
  el.dataset.marked = own;
  el.style.outline = `2px solid ${SOFT_INK}`;
  el.style.outlineOffset = "3px";
  const still = reducedMotion();
  await wait(still ? STILL_MARK_MS : Math.max(0, glide - (performance.now() - started)));
  if (!still && el.dataset.marked === own) await play(el, [{ outlineColor: SOFT_INK }, { outlineColor: CLEAR_INK }], DUR.roll);
  if (el.dataset.marked !== own) return; // a newer mark on this frame clears it itself
  delete el.dataset.marked;
  el.style.outline = "";
  el.style.outlineOffset = "";
}
