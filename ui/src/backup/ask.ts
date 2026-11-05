// After the first project is made, One asks once where to keep backups. "Once" needs nothing saved: it asks only
// when the project just made is the only one and no backup folder is picked, which is true one time.
import { useSyncExternalStore } from "react";
import { api } from "../api";

let asking = false;
const listeners = new Set<() => void>();

function set(next: boolean) {
  asking = next;
  for (const listener of listeners) listener();
}

/** Called after a project is made. */
export async function askForBackupFolder() {
  const [listed, backup] = await Promise.all([
    api("/projects").then((r) => (r.ok ? (r.json() as Promise<{ projects: { id: string; name?: string }[] }>) : undefined)),
    api("/backup").then((r) => (r.ok ? (r.json() as Promise<{ folder: string | null }>) : undefined)),
  ]).catch(() => [undefined, undefined]);
  if (!listed || !backup) return;
  if (backup.folder === null && listed.projects.filter((p) => "name" in p).length === 1) set(true);
}

export function stopAsking() {
  set(false);
}

export function useBackupAsk(): boolean {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    () => asking,
  );
}
