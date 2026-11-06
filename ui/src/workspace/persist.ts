// The open document is saved 500 ms after the last change (decision 4); `flush` sends it at once (project switch,
// pagehide with keepalive) and resolves once every save sent so far is answered, so the project is closed only after
// them. Nothing goes to web storage: it lives in the project's encrypted file.
import type { Opened, ProjectSources } from "../project/types";

export function createWorkspaceSaver(sources: Pick<ProjectSources, "saveWorkspace">, waitMs = 500) {
  let waiting: Opened | null = null;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let sent: Promise<void> = Promise.resolve(); // every save sent so far, answered or not

  function flush(keepalive = false): Promise<void> {
    clearTimeout(timer);
    timer = undefined;
    if (!waiting) return sent;
    const opened = { ...waiting }; // as it is now: the anchor may move on after
    waiting = null;
    const saving = sources.saveWorkspace(opened, keepalive).catch(() => {
      waiting ??= opened; // the core did not take it: sent again with the next save, unless something newer came
    });
    sent = Promise.all([sent, saving]).then(() => undefined);
    return sent;
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
