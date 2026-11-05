// Web search (Plan 5, Task 14): which search One uses now, written out, and a place for the engineer's own Brave
// Search key. The core keeps the key in the system key store and never sends it back, so the page never shows it.
// No Save button: a pasted key is saved at once, a typed one after a pause once it is long enough (ui/live.tsx).
// The core has no check of its own for this key, so the line says it is saved, and which search ONE now uses.
// Self-contained: whoever opens Settings places it.
import { useCallback, useEffect, useId, useState } from "react";
import { api } from "../api";
import { coreLine, send } from "../core";
import { Feedback } from "../firstlaunch/parts";
import { pick, t, type Text, texts, useLanguage } from "../i18n";
import { SEARCH_SETTING } from "../shell/FixAction";
import { KEY_MIN, useLiveKey } from "../ui/live";

/** GET /settings/search (core/qsone/app.py). */
type Search = { provider: "brave" | "native" | "connector" | "none"; own_key: boolean };
type Loaded = { state: "loading" | "failed" } | { state: "ready"; search: Search };

const providerText: Record<Search["provider"], Text> = {
  brave: texts.searchByBrave,
  native: texts.searchByNative,
  connector: texts.searchByConnector,
  none: texts.searchByNone,
};

export function SearchKey() {
  useLanguage();
  const title = useId();
  const field = useId();
  const [loaded, setLoaded] = useState<Loaded>({ state: "loading" });

  const load = useCallback(async () => {
    const response = await api("/settings/search").catch(() => undefined);
    const search = response?.ok ? ((await response.json().catch(() => undefined)) as Search | undefined) : undefined;
    setLoaded(search?.provider && search.provider in providerText ? { state: "ready", search } : { state: "failed" });
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const key = useLiveKey(KEY_MIN.brave, async (value, signal) => {
    const response = await send("/settings/search-key", "PUT", { value }, signal);
    if (signal.aborted) return null;
    if (!response?.ok) return coreLine(response, texts.keyFailed);
    void load(); // the search ONE uses now
    return null;
  });
  const { live } = key;

  return (
    <section id={SEARCH_SETTING} aria-labelledby={title} className="border-b border-stone px-4 py-4">
      <div className="mx-auto flex max-w-2xl flex-col gap-3">
        <h2 id={title} className="font-semibold">
          {t("searchTitle")}
        </h2>
        {loaded.state === "failed" && <p className="text-slate">{t("searchFailedToLoad")}</p>}
        {loaded.state === "ready" && (
          <p className="flex flex-wrap gap-x-1">
            <span className="text-slate">{t("searchProvider")}</span>
            <span>{pick(providerText[loaded.search.provider])}</span>
          </p>
        )}
        {loaded.state === "ready" && loaded.search.own_key && <p className="text-slate">{t("searchKeyKept")}</p>}
        <div className="flex flex-col gap-2">
          <p className="text-slate">{t("searchKeyHelp")}</p>
          <label htmlFor={field}>{t("searchKey")}</label>
          <input
            id={field}
            type="password"
            dir="ltr"
            autoComplete="off"
            spellCheck={false}
            {...key.field}
            aria-invalid={live.state === "failed" || undefined}
            className={`rounded-md border bg-paper px-3 py-2 outline-none transition-colors duration-150 ease-out focus:border-ink ${
              live.state === "failed" ? "border-copper" : "border-slate"
            }`}
          />
          <div className="min-h-7">
            {live.state === "short" && <p className="fl-rise text-slate">{t("keyTooShort")}</p>}
            {live.state === "busy" && <Feedback state="busy">{t("saving")}</Feedback>}
            {live.state === "done" && <Feedback state="done">{t("keySaved")}</Feedback>}
            {live.state === "failed" && <Feedback state="failed">{pick(live.line)}</Feedback>}
          </div>
        </div>
      </div>
    </section>
  );
}
