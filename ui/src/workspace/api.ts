// The open document of the project: one value for the page (like project/selection.ts), with Back. The screen reads it
// with useOpened(); the saver in persist.ts keeps it in the project.
import { useSyncExternalStore } from "react";
import type { Anchor, DocKey, Opened } from "../project/types";
import { createHistory } from "./history";

const listeners = new Set<() => void>();
const moves = new Set<() => void>(); // the place in the open document moved: saved, nothing re-renders
let history = createHistory();
const histories = new Map<string, ReturnType<typeof createHistory>>();
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
  /** The place in the open document moved (the engineer selected there, paged a file): Back comes back to it, and
   * the project keeps it. Not a step of its own, and nothing re-renders or scrolls for it. */
  at(anchor: Anchor) {
    if (!current) return;
    current.anchor = anchor;
    for (const listener of [...moves]) listener();
  },
  /** On project open: restore its session history; reset without a project starts a fresh session (tests). */
  reset(opened: Opened | null, check: (key: DocKey) => boolean, projectId?: string) {
    exists = check;
    if (projectId) {
      history = histories.get(projectId) ?? createHistory();
      histories.set(projectId, history);
    } else {
      histories.clear();
      history = createHistory();
    }
    set(opened && check(opened.key) ? opened : { key: home, anchor: null });
  },
  /** A document was replaced by a new version (a file uploaded again): the new one takes its place, open or in the
   * history, at the same place. Not a step of its own. */
  replace(from: DocKey, to: DocKey) {
    history.rename(from, to);
    if (current?.key === from) set({ key: to, anchor: current.anchor });
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

/** Told when the place in the open document moves (`at`), for the saver. */
export function subscribeMoved(listener: () => void): () => void {
  moves.add(listener);
  return () => moves.delete(listener);
}

/** Whether Back has a document to go to: the top bar's Back arrow is off without one. */
export function useCanGoBack(): boolean {
  return useSyncExternalStore(subscribeOpened, () => history.has(exists));
}

/** Re-renders the component when the open document changes. */
export function useOpened(): Opened | null {
  return useSyncExternalStore(subscribeOpened, workspaceApi.current);
}
