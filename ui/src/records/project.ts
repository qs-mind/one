// The project the engineer works in. Built like i18n.ts: one value for the page, remembered by its id only.
import { useSyncExternalStore } from "react";
import { api } from "../api";

export type Project = {
  id: string;
  name: string;
  created_at: string;
  /** Archived: read-only until unarchived (Plan 8). */
  archived_at?: string | null;
  /** A Confidential Project: nothing in it is used outside it. */
  confidential?: boolean;
};

const storageKey = "qsone.project";
const listeners = new Set<() => void>();
let current: Project | undefined;

function remember(id: string | undefined) {
  try {
    if (id) localStorage.setItem(storageKey, id);
    else localStorage.removeItem(storageKey);
  } catch {
    // private window or blocked storage: the project stays open for this session only
  }
}

export function currentProject(): Project | undefined {
  return current;
}

export function setCurrentProject(project: Project | undefined) {
  current = project;
  remember(project?.id);
  for (const listener of listeners) listener();
}

// What the open project still has to send before the core closes it (its open document, workspace/documents.tsx):
// a save that came after the close would be refused, and the last document opened lost.
const unsent = new Set<() => Promise<unknown> | void>();

/** `send` runs as the engineer leaves the project; the project is closed in the core once it is done. */
export function beforeClose(send: () => Promise<unknown> | void): () => void {
  unsent.add(send);
  return () => void unsent.delete(send);
}

/** Starts what is still to send, now (before the screen moves on), and resolves once it is sent or refused. */
export function whenSent(): Promise<void> {
  const sending = [...unsent].map((send) => {
    try {
      return Promise.resolve(send()).catch(() => undefined);
    } catch {
      return undefined;
    }
  });
  return Promise.all(sending).then(() => undefined);
}

/** Closes the project in the core once `sent` is done, unless the engineer is back in it by then (left and
 * reopened before the save was answered): a close then would shut the project now open. */
export function closeAfter(projectId: string, sent: Promise<void>) {
  void sent
    .then(() => (current?.id === projectId ? undefined : api(`/projects/${projectId}/close`, { method: "POST" })))
    .catch(() => undefined);
}

/** Makes `next` current and closes the one before it in the core, so one project stays open at a time; what the one
 * before still had to save goes first. */
export function switchProject(next: Project) {
  const before = current;
  const leaving = before && before.id !== next.id ? whenSent() : null;
  setCurrentProject(next);
  if (before && leaving) closeAfter(before.id, leaving);
}

/** Opens the remembered project in the core. One that no longer opens is forgotten, and the answer is "failed". */
export async function restoreProject(): Promise<"none" | "opened" | "failed"> {
  let id: string | null = null;
  try {
    id = localStorage.getItem(storageKey);
  } catch {
    return "none";
  }
  if (!id) return "none";
  const response = await api(`/projects/${encodeURIComponent(id)}/open`, { method: "POST" }).catch(
    () => undefined,
  );
  if (response?.ok) {
    setCurrentProject((await response.json()) as Project);
    return "opened";
  }
  remember(undefined);
  return "failed";
}

/** Re-renders the component when the current project changes. */
export function useProject(): Project | undefined {
  return useSyncExternalStore((listener) => {
    listeners.add(listener);
    return () => listeners.delete(listener);
  }, currentProject);
}
