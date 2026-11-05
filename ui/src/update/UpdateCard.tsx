// "One <version> is ready": a small card under the top bar's far end, in the installed app only. The shell asks for a
// signed update at start and every 24 hours (desktop/src/update.rs) and never installs by itself. "What changed" shows
// the notes in the page's language; "Later" hides the card until the next check; "Update now" downloads (the shell
// checks the signature), pauses Briefs, backs up and closes the projects, installs and starts One again.
//
// If the install fails, the shell starts the core again; once the core has closed the projects, the page reloads so
// they open as before, and the card then says the update did not install.
import { Channel, invoke } from "@tauri-apps/api/core";
import { type ReactNode, useCallback, useEffect, useState } from "react";
import { inInstalledApp } from "../api";
import { fill, language, t, useLanguage } from "../i18n";

/** What the shell found (update.rs `info`). */
export type UpdateInfo = { version: string; notes_en: string; notes_ar: string };

/** How an install goes, step by step (update.rs `update_install`). */
type Progress = { step: "download"; percent: number } | { step: "prepare" } | { step: "install" };

export const EVERY_MS = 24 * 60 * 60 * 1000;
const FAILED = "qsone.updateFailed"; // kept across the reload after a failed install

function failedBefore(): boolean {
  try {
    const failed = sessionStorage.getItem(FAILED) === "1";
    sessionStorage.removeItem(FAILED);
    return failed;
  } catch {
    return false;
  }
}

function remember() {
  try {
    sessionStorage.setItem(FAILED, "1");
  } catch {
    // the card then says nothing after the reload; One is still as it was
  }
}

type State = { kind: "idle" } | { kind: "working"; progress: Progress | null } | { kind: "failed" };

export function UpdateCard({ reload = () => window.location.reload() }: { reload?: () => void }) {
  useLanguage();
  const [found, setFound] = useState<UpdateInfo | null>(null);
  const [shown, setShown] = useState(false);
  const [state, setState] = useState<State>(() => (failedBefore() ? { kind: "failed" } : { kind: "idle" }));

  const check = useCallback(async () => {
    const update = await invoke<UpdateInfo | null>("update_check").catch(() => null); // offline: nothing to show
    setFound(update);
    setShown(update !== null);
  }, []);

  useEffect(() => {
    if (!inInstalledApp()) return;
    void check();
    const timer = setInterval(() => void check(), EVERY_MS);
    return () => clearInterval(timer);
  }, [check]);

  async function install() {
    const reached: { step: Progress["step"] | null } = { step: null };
    setState({ kind: "working", progress: null });
    const onProgress = new Channel<Progress>((progress) => {
      reached.step = progress.step;
      setState({ kind: "working", progress });
    });
    try {
      await invoke("update_install", { onProgress }); // on success One starts again before this returns
    } catch {
      if (reached.step === "prepare" || reached.step === "install") {
        remember(); // the projects were closed: open them again
        reload();
        return;
      }
      setState({ kind: "failed" });
    }
  }

  if (state.kind === "failed") {
    return (
      <Card label={t("updateFailed")}>
        <p role="alert">{t("updateFailed")}</p>
        <div className="flex gap-2">
          <button type="button" className={plain} onClick={() => setState({ kind: "idle" })}>
            {t("close")}
          </button>
        </div>
      </Card>
    );
  }
  if (!found || (!shown && state.kind === "idle")) return null;

  const notes = language() === "ar" ? found.notes_ar : found.notes_en;
  const ready = fill(t("updateReady"), { version: found.version });
  return (
    <Card label={ready}>
      <p className="font-semibold text-ink">{ready}</p>
      {notes && (
        <details className="text-sm">
          <summary className="cursor-pointer text-slate">{t("updateNotes")}</summary>
          <p dir="auto" className="mt-2 max-h-48 overflow-y-auto whitespace-pre-line">
            {notes}
          </p>
        </details>
      )}
      {state.kind === "working" ? (
        <p role="status" className="text-sm text-slate">
          {say(state.progress)}
        </p>
      ) : (
        <div className="flex gap-2">
          <button type="button" className="rounded-lg bg-ink px-4 py-2 text-paper" onClick={() => void install()}>
            {t("updateNow")}
          </button>
          <button type="button" className={plain} onClick={() => setShown(false)}>
            {t("updateLater")}
          </button>
        </div>
      )}
    </Card>
  );
}

const plain = "rounded-lg px-4 py-2 hover:bg-stone focus-visible:outline-2 focus-visible:outline-ink";

function say(progress: Progress | null): string {
  if (progress?.step === "install") return t("updateInstalling");
  if (progress?.step === "prepare") return t("updatePreparing");
  return fill(t("updateDownloading"), { percent: progress?.percent ?? 0 });
}

function Card({ label, children }: { label: string; children: ReactNode }) {
  return (
    <aside
      aria-label={label}
      className="fixed end-4 top-16 z-50 flex w-80 max-w-[calc(100vw-2rem)] flex-col gap-3 rounded-[14px] border border-ink/[0.08] bg-paper px-5 py-4"
    >
      {children}
    </aside>
  );
}
