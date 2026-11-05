// ONE's motion, in one place (docs/specs/2026-11-05-motion-design.md): calm, ease-out, 150 to 400 ms, transform
// and opacity; no bounce, glow, shadow or rotation. With reduced motion everything shows in its end state at once,
// and motion already playing when it is turned on finishes at once too.
import { useSyncExternalStore } from "react";

/** The ease the first launch and the message box already use. */
export const EASE = "cubic-bezier(0.2, 0.8, 0.2, 1)";

/** EASE as a function of progress (0 to 1), for motion run in script, such as the canvas's view gliding. */
export function ease(progress: number): number {
  if (progress <= 0) return 0;
  if (progress >= 1) return 1;
  // cubic-bezier(0.2, 0.8, 0.2, 1): find the curve's parameter whose x is `progress`, then give its y
  const curve = (s: number, a: number, b: number) => 3 * a * s * (1 - s) ** 2 + 3 * b * s * s * (1 - s) + s ** 3;
  let low = 0;
  let high = 1;
  for (let i = 0; i < 30; i++) {
    const mid = (low + high) / 2;
    if (curve(mid, 0.2, 0.2) < progress) low = mid;
    else high = mid;
  }
  return curve((low + high) / 2, 0.8, 1);
}

/** Milliseconds: a quick change, most changes, a panel or screen, a number rolling. */
export const DUR = { short: 150, base: 220, long: 300, roll: 400 } as const;

const QUERY = "(prefers-reduced-motion: reduce)";

function query(): MediaQueryList | undefined {
  return typeof matchMedia === "function" ? matchMedia(QUERY) : undefined;
}

/** Whether the system asks for reduced motion now; false where the query is missing. */
export function reducedMotion(): boolean {
  return query()?.matches ?? false;
}

function subscribe(onChange: () => void): () => void {
  const list = query();
  list?.addEventListener("change", onChange);
  return () => list?.removeEventListener("change", onChange);
}

/** Reduced motion, re-rendering when the system setting changes. */
export function useReducedMotion(): boolean {
  return useSyncExternalStore(subscribe, reducedMotion, () => false);
}

// Animations still playing, so reduced motion turned on mid-run can finish them. The system setting is watched
// only while something plays.
const playing = new Set<Animation>();
let unwatch: (() => void) | undefined;

function track(animation: Animation) {
  playing.add(animation);
  unwatch ??= subscribe(() => {
    if (!reducedMotion()) return;
    for (const running of [...playing]) running.finish();
  });
}

function untrack(animation: Animation) {
  playing.delete(animation);
  if (playing.size) return;
  unwatch?.();
  unwatch = undefined;
}

/** Plays `keyframes` on `el` with the calm ease. Resolves when done; at once with reduced motion or where the
 * browser cannot animate. Sideways keyframes are the caller's: flip them for RTL before passing them. */
export async function play(el: Element, keyframes: Keyframe[], ms: number): Promise<void> {
  if (reducedMotion() || typeof el.animate !== "function") return;
  const animation = el.animate(keyframes, { duration: ms, easing: EASE });
  track(animation);
  try {
    await animation.finished;
  } catch {
    // cancelled: the element left, or a newer motion replaced this one
  } finally {
    untrack(animation);
  }
}
