// Web search (Plan 5, Task 14): which search One uses now, written out, and a place for the engineer's own Brave
// Search key. The core keeps the key in the system key store and never sends it back, so the page never shows it.
// Self-contained: whoever opens Settings places it.
import { useCallback, useEffect, useId, useState, type FormEvent } from "react";
import { api } from "../api";
import { coreLine, send } from "../core";
import { pick, t, type Text, texts, useLanguage } from "../i18n";

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
  const [loaded, setLoaded] = useState<Loaded>({ state: "loading" });
  const [value, setValue] = useState("");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [failed, setFailed] = useState<Text>();

  const load = useCallback(async () => {
    const response = await api("/settings/search").catch(() => undefined);
    const search = response?.ok ? ((await response.json().catch(() => undefined)) as Search | undefined) : undefined;
    setLoaded(search?.provider && search.provider in providerText ? { state: "ready", search } : { state: "failed" });
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function save(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setSaved(false);
    setFailed(undefined);
    const response = await send("/settings/search-key", "PUT", { value: value.trim() });
    setSaving(false);
    if (response?.ok) {
      setValue("");
      setSaved(true);
      void load();
    } else {
      setFailed(await coreLine(response, texts.keyFailed));
    }
  }

  return (
    <section aria-labelledby={title} className="border-b border-stone px-4 py-4">
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
        <form onSubmit={save} className="flex flex-col gap-3">
          <p className="text-slate">{t("searchKeyHelp")}</p>
          <label className="flex flex-col gap-1">
            <span>{t("searchKey")}</span>
            <input
              type="password"
              dir="ltr"
              autoComplete="off"
              spellCheck={false}
              value={value}
              onChange={(event) => setValue(event.target.value)}
              className="rounded-md border border-slate bg-paper px-3 py-2 outline-none focus:border-ink"
            />
          </label>
          <div className="flex items-center gap-3">
            <button
              type="submit"
              disabled={!value.trim() || saving}
              className="rounded-md bg-ink px-4 py-2 text-paper disabled:opacity-40"
            >
              {t("save")}
            </button>
            {saved && <p role="status">{t("keyAdded")}</p>}
            {failed && (
              <p role="alert" className="text-copper">
                {pick(failed)}
              </p>
            )}
          </div>
        </form>
      </div>
    </section>
  );
}
