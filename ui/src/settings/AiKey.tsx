// Add or replace the engineer's Claude key. The core keeps it in the system key store; the page never shows it again.
import { useState, type FormEvent } from "react";
import { t, useLanguage } from "../i18n";

export function AiKey({ onSaved, onClose }: { onSaved: () => void; onClose?: () => void }) {
  useLanguage();
  const [value, setValue] = useState("");
  const [state, setState] = useState<"idle" | "saving" | "saved" | "failed">("idle");

  async function save(event: FormEvent) {
    event.preventDefault();
    setState("saving");
    const response = await fetch("/api/settings/ai-key", {
      method: "PUT",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ provider: "anthropic", value: value.trim() }),
    }).catch(() => undefined);
    if (response?.ok) {
      setValue("");
      setState("saved");
      onSaved();
    } else {
      setState("failed");
    }
  }

  return (
    <section className="border-b border-stone px-4 py-4">
      <div className="mx-auto flex max-w-2xl flex-col gap-3">
        <div className="flex items-center justify-between gap-4">
          <h2 className="font-semibold">{t("aiKeyTitle")}</h2>
          {onClose && (
            <button type="button" onClick={onClose} className="text-slate hover:text-ink">
              {t("close")}
            </button>
          )}
        </div>
        {state === "saved" ? (
          <p role="status">{t("keyAdded")}</p>
        ) : (
          <form onSubmit={save} className="flex flex-col gap-3">
            <p className="text-slate">{t("aiKeyHelp")}</p>
            <label className="flex flex-col gap-1">
              <span>{t("aiKeyLabel")}</span>
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
                disabled={!value.trim() || state === "saving"}
                className="rounded-md bg-ink px-4 py-2 text-paper disabled:opacity-40"
              >
                {t("save")}
              </button>
              {state === "failed" && (
                <p role="alert" className="text-copper">
                  {t("keyFailed")}
                </p>
              )}
            </div>
          </form>
        )}
      </div>
    </section>
  );
}
