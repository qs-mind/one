// The open document of the project: one value for the page (like project/selection.ts), with Back. The screen reads it
// with useOpened(); the saver in persist.ts keeps it in the project.
import { useSyncExternalStore } from "react";
import type { Anchor, DocKey, Opened } from "../project/types";
import { createHistory } from "./history";

const listeners = new Set<() => void>();
const history = createHistory();
const home: DocKey = "files:all";
let current: Opened | null = null;
let exists: (key: DocKey) => boolean = () => true;

function set(next: Opened) {
  current = next;
  for (const listener of listeners) listener();
}

export const workspaceApi = {
  /** The current document goes onto the history first. */
  open(key: DocKey, anchor: Anchor | null = null) {
    if (current) history.push(current);
    set({ key, anchor });
  },
  /** False when there is nothing to go back to. */
  back(): boolean {
    const previous = history.pop(exists);
    if (!previous) return false;
    set(previous);
    return true;
  },
  current(): Opened | null {
    return current;
  },
  /** On project open: the saved document, or Project files when there is none or it is gone. Clears the history. */
  reset(opened: Opened | null, check: (key: DocKey) => boolean) {
    exists = check;
    history.clear();
    set(opened && check(opened.key) ? opened : { key: home, anchor: null });
  },
  /** A document was removed: out of the history; if it is open, Project files opens. */
  forget(key: DocKey) {
    history.drop(key);
    if (current?.key === key) set({ key: home, anchor: null });
  },
};

export function subscribeOpened(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** Re-renders the component when the open document changes. */
export function useOpened(): Opened | null {
  return useSyncExternalStore(subscribeOpened, workspaceApi.current);
}
