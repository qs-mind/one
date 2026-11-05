// What the engineer has selected on the canvas: frames, or a range inside a frame's viewer. Built like i18n.ts:
// one value for the page; the command bar reads it and sends it with the message to the Lead QS.
import { useSyncExternalStore } from "react";
import type { SelectionItem } from "./types";

const listeners = new Set<() => void>();
const none: readonly SelectionItem[] = [];
let current: readonly SelectionItem[] = none;

export function currentSelection(): readonly SelectionItem[] {
  return current;
}

/** Replaces the selection; an empty list clears it. */
export function select(items: readonly SelectionItem[]) {
  current = items.length ? [...items] : none;
  for (const listener of listeners) listener();
}

export function subscribeSelection(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** Re-renders the component when the selection changes. */
export function useSelection(): readonly SelectionItem[] {
  return useSyncExternalStore(subscribeSelection, currentSelection);
}
