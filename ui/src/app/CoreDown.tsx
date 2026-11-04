// Before the chat opens, check that the core answers. If it does not, say so in both languages, show where its log
// is, and offer Retry, so the window is never just blank.
import { useCallback, useEffect, useState, type ReactNode } from "react";
import { t, texts, useLanguage } from "../i18n";

// Set by the dev server (scripts/core-dev.ts); the release build gets its own path in a later plan.
const coreLog: string = import.meta.env.VITE_CORE_LOG ?? "core.log";

export function HealthGate({ children, logPath = coreLog }: { children: ReactNode; logPath?: string }) {
  const [state, setState] = useState<"checking" | "up" | "down">("checking");

  const check = useCallback(async () => {
    setState("checking");
    const up = await fetch("/api/health")
      .then((response) => response.ok)
      .catch(() => false);
    setState(up ? "up" : "down");
  }, []);

  useEffect(() => {
    void check();
  }, [check]);

  if (state === "up") return children;
  if (state === "down") return <CoreDown logPath={logPath} onRetry={() => void check()} />;
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
