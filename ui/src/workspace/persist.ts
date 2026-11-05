// The open document is saved 500 ms after the last change (decision 4); `flush` sends it at once (project switch,
// pagehide with keepalive). Nothing goes to web storage: it lives in the project's encrypted file.
import type { Opened, ProjectSources } from "../project/types";

export function createWorkspaceSaver(sources: Pick<ProjectSources, "saveWorkspace">, waitMs = 500) {
  let waiting: Opened | null = null;
  let timer: ReturnType<typeof setTimeout> | undefined;

  function flush(keepalive = false) {
    clearTimeout(timer);
    timer = undefined;
    if (!waiting) return;
    const opened = waiting;
    waiting = null;
    sources.saveWorkspace(opened, keepalive).catch(() => {
      waiting ??= opened; // the core did not take it: sent again with the next save, unless something newer came
    });
  }

  return {
    save(opened: Opened) {
      waiting = opened;
      clearTimeout(timer);
      timer = setTimeout(() => flush(), waitMs);
    },
    flush,
  };
}
