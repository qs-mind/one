// Search by meaning in Project files: one quiet Slate line, and only while it gets ready or when it is not.
// Nothing to press (5 Nov 2026): the core downloads the search model by itself the first time a project has a
// file, then prepares each open project; a failure waits for the next start. The line polls GET /api/meaning
// every second while something moves; `files` changing (a file came in) asks again at once.
import { useEffect, useState } from "react";
import { api } from "../api";
import { fill, t, useLanguage } from "../i18n";

type Model = { state: "off" | "downloading" | "checking" | "failed" | "ready" | "unavailable"; done_bytes: number; total_bytes: number };
type Job = { state: "waiting" | "indexing" | "ready" | "failed"; done: number; total: number };
type Status = { model: Model; indexing: { projects: Record<string, Job | undefined> } };

/** "42%": Western digits in both languages, as in the rest of the screen. */
function percent(done: number, total: number): string {
  return `${total > 0 ? Math.min(100, Math.floor((done / total) * 100)) : 0}%`;
}

/** True while the line must keep polling: the download, its check, or this project's preparing. */
function moving({ model, indexing }: Status, projectId: string): boolean {
  if (model.state === "downloading" || model.state === "checking") return true;
  const job = indexing.projects[projectId];
  return model.state === "ready" && (job?.state === "indexing" || job?.state === "waiting");
}

/** The line, or none: nothing while off (no file yet), ready, or on a computer that cannot run it. */
function line({ model, indexing }: Status, projectId: string): string | undefined {
  if (model.state === "downloading" || model.state === "checking")
    return fill(t("meaningPreparing"), { percent: percent(model.done_bytes, model.total_bytes) });
  if (model.state === "failed") return t("meaningNotReady");
  if (model.state !== "ready") return undefined;
  const job = indexing.projects[projectId];
  if (job?.state === "failed") return t("meaningNotReady");
  if (job && job.state !== "ready" && job.total > job.done)
    return fill(t("meaningPreparing"), { percent: percent(job.done, job.total) });
  return undefined;
}

export function MeaningStatus({ projectId, files = 0 }: { projectId: string; files?: number }) {
  useLanguage();
  const [status, setStatus] = useState<Status>();

  useEffect(() => {
    let live = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let last: Status | undefined;
    let waits = 0; // polls spent waiting for the core to start on a new file (the core looks every 5 s)
    async function poll() {
      const response = await api("/meaning").catch(() => undefined);
      const body = response?.ok ? ((await response.json().catch(() => undefined)) as Status | undefined) : undefined;
      if (!live) return;
      if (body) setStatus((last = body));
      // a missed answer keeps the last line; polling goes on while that line still moves, and for a few seconds
      // while the core has not yet started on a new file (one with no text never starts it)
      const waiting = files > 0 && last?.model.state === "off" && waits++ < 10;
      if (last && (moving(last, projectId) || waiting)) timer = setTimeout(() => void poll(), 1000);
    }
    void poll();
    return () => {
      live = false;
      clearTimeout(timer);
    };
  }, [projectId, files]);

  const shown = status && line(status, projectId);
  if (!shown) return null;
  return (
    <p role="status" className="text-slate">
      {shown}
    </p>
  );
}
