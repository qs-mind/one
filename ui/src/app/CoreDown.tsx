// Before the chat opens, check that the core answers, behind the start screen. If it does not, say so in both
// languages on that screen, show where its log is, and offer Retry, so the window is never just blank.
import { invoke } from "@tauri-apps/api/core";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { api, inInstalledApp } from "../api";
import { systemLanguage } from "../firstlaunch/FirstLaunch";
import { type Language, savedLanguage, t } from "../i18n";
import { SLOW_MS, StartScreen } from "./StartScreen";

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
  const [state, setState] = useState<"checking" | "slow" | "up" | "down">("checking");
  const [log, setLog] = useState(logPath ?? coreLog);
  const [shown, setShown] = useState(false);
  const [done, setDone] = useState(false);
  const [lang] = useState<Language>(() => savedLanguage() ?? systemLanguage());
  const slow = useRef<ReturnType<typeof setTimeout>>(undefined);

  const check = useCallback(async () => {
    setState("checking");
    clearTimeout(slow.current);
    // still starting after SLOW_MS: the shell still says "starting", or the core has not answered yet
    slow.current = setTimeout(() => setState((now) => (now === "checking" ? "slow" : now)), SLOW_MS);
    let up = true;
    if (inInstalledApp()) {
      if (logPath === undefined) setLog(await invoke<string>("core_log_path").catch(() => coreLog));
      up = await started();
    }
    if (up) {
      up = await api("/health")
        .then((response) => response.ok)
        .catch(() => false);
    }
    clearTimeout(slow.current);
    setState(up ? "up" : "down");
  }, [logPath]);

  useEffect(() => {
    void check();
    return () => clearTimeout(slow.current);
  }, [check]);

  const show = useCallback(() => setShown(true), []);
  const finish = useCallback(() => setDone(true), []);
  return (
    <>
      {shown && children}
      {!done && (
        <StartScreen
          state={state === "up" ? "ready" : state === "checking" ? "starting" : state}
          log={log}
          lang={lang}
          onRetry={() => void check()}
          onShow={show}
          onDone={finish}
        />
      )}
    </>
  );
}

/** The core is down: why, where its log is, and Retry, all in the start screen's language. */
export function CoreDown({ logPath, onRetry, lang }: { logPath: string; onRetry: () => void; lang: Language }) {
  return (
    <div className="start-rise mt-6 flex w-full max-w-xl flex-col gap-3">
      <p>{t("coreDown", lang)}</p>
      <code dir="ltr" className="rounded-md bg-stone px-3 py-2 text-start font-mono text-sm break-all">
        {logPath}
      </code>
      <button type="button" onClick={onRetry} className="self-start rounded-md bg-ink px-4 py-2 text-paper">
        {t("retry", lang)}
      </button>
    </div>
  );
}
