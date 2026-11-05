// Search by meaning in Project Records: one line for the search model's state and at most one button.
// The core holds the state; the line polls GET /api/meaning every second while something moves.
import { useEffect, useState } from "react";
import { api } from "../api";
import { fill, pick, t, type Text, texts, useLanguage } from "../i18n";

type Model = {
  state: "off" | "downloading" | "checking" | "stopped" | "failed" | "ready" | "unavailable";
  done_bytes: number;
  total_bytes: number;
  reason: Text | null;
};
type Job = { state: "waiting" | "indexing" | "ready" | "failed"; done: number; total: number; reason: Text | null };
type Status = { model: Model; indexing: { paused: boolean; projects: Record<string, Job | undefined> } };

/** "420 MB" or "1.2 GB": Latin units and Western digits in both languages, as in the rest of the screen. */
export function formatBytes(n: number): string {
  return n < 1e9 ? `${Math.round(n / 1e6)} MB` : `${(n / 1e9).toFixed(1)} GB`;
}

/** True while the line must keep polling: a download, its check, or this project's preparing. */
function moving({ model, indexing }: Status, projectId: string): boolean {
  if (model.state === "downloading" || model.state === "checking") return true;
  const job = indexing.projects[projectId];
  return model.state === "ready" && !indexing.paused && (job?.state === "indexing" || job?.state === "waiting");
}

type Shown = { line: string; tone: "ink" | "slate" | "copper"; button?: { label: Text; post: string }; share?: number };

function shown({ model, indexing }: Status, projectId: string): Shown {
  const bytes = { done: formatBytes(model.done_bytes), total: formatBytes(model.total_bytes) };
  switch (model.state) {
    case "off":
      return {
        line: fill(t("meaningOff"), { size: formatBytes(model.total_bytes) }),
        tone: "ink",
        button: { label: texts.meaningDownload, post: "download" },
      };
    case "downloading":
      return {
        line: fill(t("meaningDownloading"), bytes),
        tone: "ink",
        button: { label: texts.meaningStop, post: "stop" },
        share: model.done_bytes / model.total_bytes,
      };
    case "stopped":
      return {
        line: fill(t("meaningStopped"), bytes),
        tone: "ink",
        button: { label: texts.meaningResume, post: "download" },
      };
    case "checking":
      return { line: t("meaningChecking"), tone: "ink" };
    case "failed":
      return {
        line: model.reason ? pick(model.reason) : "",
        tone: "copper",
        button: { label: texts.meaningRetry, post: "download" },
      };
    case "unavailable":
      return { line: model.reason ? pick(model.reason) : "", tone: "slate" };
  }
  const job = indexing.projects[projectId];
  if (job?.state === "failed")
    return {
      line: job.reason ? pick(job.reason) : "",
      tone: "copper",
      button: { label: texts.meaningRetry, post: "resume" },
    };
  if (job && job.state !== "ready") {
    if (indexing.paused)
      return {
        line: fill(t("meaningPaused"), { done: job.done, total: job.total }),
        tone: "ink",
        button: { label: texts.meaningResume, post: "resume" },
      };
    return {
      line: fill(t("meaningIndexing"), { done: job.done, total: job.total }),
      tone: "ink",
      button: { label: texts.meaningPause, post: "pause" },
      share: job.total ? job.done / job.total : 0,
    };
  }
  return { line: t("meaningReady"), tone: "slate" };
}

const toneClass = { ink: "", slate: "text-slate", copper: "text-copper" } as const;

export function MeaningStatus({ projectId }: { projectId: string }) {
  useLanguage();
  const [status, setStatus] = useState<Status>();
  const [pressing, setPressing] = useState(false);
  const [asked, setAsked] = useState(0); // a button press polls again at once

  useEffect(() => {
    let live = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let last: Status | undefined;
    async function poll() {
      const response = await api("/meaning").catch(() => undefined);
      const body = response?.ok ? ((await response.json().catch(() => undefined)) as Status | undefined) : undefined;
      if (!live) return;
      if (body) setStatus((last = body));
      // a missed answer keeps the last line; polling goes on while that line still moves
      if (last && moving(last, projectId)) timer = setTimeout(() => void poll(), 1000);
    }
    void poll();
    return () => {
      live = false;
      clearTimeout(timer);
    };
  }, [projectId, asked]);

  if (!status) return null;
  const { line, tone, button, share } = shown(status, projectId);

  async function press(post: string) {
    setPressing(true);
    await api(`/meaning/${post}`, { method: "POST" }).catch(() => undefined);
    setPressing(false);
    setAsked((n) => n + 1);
  }

  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center justify-between gap-4">
        <p role="status" className={toneClass[tone]}>
          {line}
        </p>
        {button && (
          <button
            type="button"
            disabled={pressing}
            onClick={() => void press(button.post)}
            className="shrink-0 rounded-md border border-ink px-4 py-2 disabled:opacity-40"
          >
            {pick(button.label)}
          </button>
        )}
      </div>
      {share !== undefined && (
        <div aria-hidden="true" className="h-0.5 w-full bg-stone">
          <div className="h-full bg-ink" style={{ width: `${Math.min(100, Math.max(0, share * 100))}%` }} />
        </div>
      )}
    </div>
  );
}
