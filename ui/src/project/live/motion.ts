// prefers-reduced-motion: cursors jump instead of gliding, and a followed view moves at once.
import { useSyncExternalStore } from "react";

const QUERY = "(prefers-reduced-motion: reduce)";
const media = () => globalThis.matchMedia?.(QUERY);

export const reducedMotion = () => media()?.matches ?? false;

/** How long a cursor or a followed view glides, in ms. */
export const glide = () => (reducedMotion() ? 0 : 300);

export function useReducedMotion(): boolean {
  return useSyncExternalStore((listener) => {
    const list = media();
    list?.addEventListener?.("change", listener);
    return () => list?.removeEventListener?.("change", listener);
  }, reducedMotion);
}
