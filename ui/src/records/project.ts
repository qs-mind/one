// The project the engineer works in. Built like i18n.ts: one value for the page, remembered by its id only.
import { useSyncExternalStore } from "react";

export type Project = { id: string; name: string; created_at: string };

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

/** Makes `next` current and closes the one before it in the core, so one project stays open at a time. */
export function switchProject(next: Project) {
  const before = current;
  setCurrentProject(next);
  if (before && before.id !== next.id) {
    void fetch(`/api/projects/${before.id}/close`, { method: "POST" }).catch(() => undefined);
  }
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
  const response = await fetch(`/api/projects/${encodeURIComponent(id)}/open`, { method: "POST" }).catch(
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
