// Usage Stats: what is sent and what never is, then "Share" or "Don't share", two buttons of the same weight, so
// neither answer is the easy one. Skip means don't share (the core saves "off" when it was never asked).
import { useEffect, useState } from "react";
import { api } from "../api";
import { send } from "../core";
import { t, useLanguage } from "../i18n";
import { type Nav, option, StepScreen } from "./parts";

export function UsageStats({ nav }: { nav: Nav }) {
  useLanguage();
  const [on, setOn] = useState<boolean | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let live = true;
    void api("/settings/usage-stats")
      .then((r) => (r.ok ? (r.json() as Promise<{ on: boolean | null }>) : undefined))
      .then((body) => live && body && setOn(body.on))
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, []);

  async function answer(share: boolean) {
    setFailed(false);
    const response = await send("/settings/usage-stats", "PUT", { on: share });
    if (!response?.ok) return setFailed(true);
    setOn(share);
    await nav.pass("done");
  }

  return (
    <StepScreen
      title={t("usageTitle")}
      help={t("usageHelp")}
      nav={nav}
      failed={failed && t("consentNotSaved")}
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="flex flex-col gap-2 rounded-lg bg-stone px-5 py-4">
          <h2 className="font-semibold">{t("usageSentTitle")}</h2>
          <p>{t("usageSent")}</p>
        </div>
        <div className="flex flex-col gap-2 rounded-lg bg-stone px-5 py-4">
          <h2 className="font-semibold">{t("usageNeverTitle")}</h2>
          <p>{t("usageNever")}</p>
        </div>
      </div>
      <div className="flex flex-col gap-2">
      <div className="grid grid-cols-2 gap-3">
        <button type="button" aria-pressed={on === true} onClick={() => void answer(true)} className={`${option(on === true)} text-center`}>
          {t("usageShare")}
        </button>
        <button type="button" aria-pressed={on === false} onClick={() => void answer(false)} className={`${option(on === false)} text-center`}>
          {t("usageDontShare")}
        </button>
      </div>
      <p className="text-xs text-slate">{t("usageSkipMeans")}</p>
      </div>
    </StepScreen>
  );
}
