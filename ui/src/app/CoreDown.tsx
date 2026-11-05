// Before the chat opens, check that the core answers. If it does not, say so in both languages, show where its log
// is, and offer Retry, so the window is never just blank.
import { invoke } from "@tauri-apps/api/core";
import { useCallback, useEffect, useState, type ReactNode } from "react";
import { api, inInstalledApp } from "../api";
import { t, texts, useLanguage } from "../i18n";

// Set by the dev server (scripts/core-dev.ts); the installed app asks the shell, which started the core.
const coreLog: string = import.meta.env.VITE_CORE_LOG ?? "core.log";

/** How long the installed app's core may take to start before the screen calls it down (core.rs: STARTING). */
export const STARTING_MS = 60_000;

// The installed app only: wait while the shell says the core is starting. False if it still is after STARTING_MS.
async function started(): Promise<boolean> {
  const end = Date.now() + STARTING_MS;
  while (Date.now() < end) {
    const status = await invoke<{ state: string }>("core_status").catch(() => ({ state: "failed" }));
    if (status.state !== "starting") return true;
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  return false;
}

export function HealthGate({ children, logPath }: { children: ReactNode; logPath?: string }) {
  const [state, setState] = useState<"checking" | "up" | "down">("checking");
  const [log, setLog] = useState(logPath ?? coreLog);

  const check = useCallback(async () => {
    setState("checking");
    if (inInstalledApp()) {
      if (logPath === undefined) setLog(await invoke<string>("core_log_path").catch(() => coreLog));
      if (!(await started())) return setState("down");
    }
    const up = await api("/health")
      .then((response) => response.ok)
      .catch(() => false);
    setState(up ? "up" : "down");
  }, [logPath]);

  useEffect(() => {
    void check();
  }, [check]);

  if (state === "up") return children;
  if (state === "down") return <CoreDown logPath={log} onRetry={() => void check()} />;
  return <Checking />;
}

function Checking() {
  useLanguage();
  return <p className="p-4 text-slate">{t("checking")}</p>;
}

export function CoreDown({ logPath, onRetry }: { logPath: string; onRetry: () => void }) {
  useLanguage();
  return (
    <main className="flex h-dvh items-center justify-center px-4">
      <div className="flex w-full max-w-xl flex-col gap-3">
        <p lang="ar" dir="rtl">
          {texts.coreDown.ar}
        </p>
        <p lang="en" dir="ltr">
          {texts.coreDown.en}
        </p>
        <code dir="ltr" className="rounded-md bg-stone px-3 py-2 break-all">
          {logPath}
        </code>
        <button type="button" onClick={onRetry} className="self-start rounded-md bg-ink px-4 py-2 text-paper">
          {t("retry")}
        </button>
      </div>
    </main>
  );
}
