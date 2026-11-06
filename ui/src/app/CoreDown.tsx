// Before the chat opens, check that the core answers, behind the start screen. If it does not, say so in both
// languages on that screen, show where its log is, and offer Retry, so the window is never just blank.
import { invoke } from "@tauri-apps/api/core";
import { Fragment, useCallback, useEffect, useRef, useState, useSyncExternalStore, type ReactNode } from "react";
import { api, inInstalledApp } from "../api";
import { systemLanguage } from "../firstlaunch/FirstLaunch";
import { type Language, savedLanguage, t, useLanguage } from "../i18n";
import { loadZoom } from "../ui/scale";
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

/** Once ONE is open, the core is asked how it is this often; this many misses in a row (about 5 s) and it is down. */
export const PING_MS = 2000;
export const MISSES = 2;

// One look at the core: it answers /health within PING_MS.
function answers(): Promise<boolean> {
  const late = new Promise<boolean>((resolve) => setTimeout(() => resolve(false), PING_MS));
  const health = api("/health")
    .then((response) => response.ok)
    .catch(() => false);
  return Promise.race([health, late]);
}

/** The core stopped answering while ONE is open: the screen stays (read-only: nothing is sent), with one thin line;
 * after LONG_MS it also says where the core's log is, with Retry. */
export type CoreLost = { log: string; retry(): void; at: number } | null;
let coreLost: CoreLost = null;
const lostListeners = new Set<() => void>();
function setCoreLost(next: CoreLost) {
  coreLost = next;
  for (const listener of [...lostListeners]) listener();
}
export function useCoreLost(): CoreLost {
  return useSyncExternalStore(
    (listener) => {
      lostListeners.add(listener);
      return () => void lostListeners.delete(listener);
    },
    () => coreLost,
  );
}
/** How long the core may take to come back before the line names its log. */
export const LONG_MS = 30_000;

/** While ONE is open: "down" once the core stops answering, then "back" when it answers again. */
function useCoreWatch(open: boolean, log: string): { lost: boolean; retry(): void; session: number } {
  const [lost, setLost] = useState(false);
  const [session, setSession] = useState(0);
  const misses = useRef(0);
  const lostNow = useRef(false);
  const logRef = useRef(log);
  logRef.current = log;
  const look = useCallback(async () => {
    const up = await answers();
    misses.current = up ? 0 : misses.current + 1;
    if (!up && misses.current >= MISSES && !lostNow.current) {
      lostNow.current = true;
      setLost(true);
      setCoreLost({ log: logRef.current, retry: () => void look(), at: Date.now() });
    } else if (up && lostNow.current) {
      // back: ONE starts again from what the core has (the same project and document), so no chat or stream is
      // left waiting on the old one
      lostNow.current = false;
      setLost(false);
      setCoreLost(null);
      setSession((n) => n + 1);
    }
  }, []);
  useEffect(() => {
    if (!open) return;
    let busy = false;
    const timer = setInterval(() => {
      if (busy) return;
      busy = true;
      void look().finally(() => (busy = false));
    }, PING_MS);
    return () => clearInterval(timer);
  }, [open, look]);
  return { lost, retry: () => void look(), session };
}

export function HealthGate({ children, logPath }: { children: ReactNode; logPath?: string }) {
  const [state, setState] = useState<"checking" | "slow" | "up" | "down">("checking");
  const [log, setLog] = useState(logPath ?? coreLog);
  const [shown, setShown] = useState(false);
  const [done, setDone] = useState(false);
  const [lang] = useState<Language>(() => savedLanguage() ?? systemLanguage());
  const slow = useRef<ReturnType<typeof setTimeout>>(undefined);
  const watch = useCoreWatch(done, log);

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
    // the engineer's zoom, before ONE opens: the screen comes at its size, never jumping to it
    if (up) await loadZoom();
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
      {shown && <Fragment key={watch.session}>{children}</Fragment>}
      {/* the core stopped mid-session: ONE stays on the screen, read-only, with one thin line until it is back */}
      {watch.lost && <RestartingLine />}
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

/** «محرك ONE بيعيد التشغيل…», over the top bar's middle; still down after LONG_MS, the line names the core's log and
 * offers Retry. The screen under it stays as it was: the open document readable, nothing sent. */
function RestartingLine() {
  useLanguage();
  const lost = useCoreLost();
  const [long, setLong] = useState(false);
  useEffect(() => {
    const timer = setTimeout(() => setLong(true), LONG_MS);
    return () => clearTimeout(timer);
  }, []);
  return (
    <div
      role="status"
      data-core-lost
      className="fixed inset-x-0 top-1.5 z-[100] flex justify-center px-4 pointer-events-none"
    >
      <div className="pointer-events-auto flex max-w-full flex-wrap items-center justify-center gap-x-3 gap-y-1 rounded-lg bg-ink px-3 py-1 text-sm text-paper shadow-[0_1px_2px_rgb(14_15_18/0.12)]">
        <span>{t("coreRestarting")}</span>
        {long && lost && (
          <>
            <span>{t("coreRestartingLong")}</span>
            <code dir="ltr" className="max-w-full font-mono text-xs break-all">
              {lost.log}
            </code>
            <button type="button" onClick={lost.retry} className="rounded-md px-2 underline-offset-2 hover:underline focus-visible:outline-2 focus-visible:outline-paper">
              {t("retry")}
            </button>
          </>
        )}
      </div>
    </div>
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
