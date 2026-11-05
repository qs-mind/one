// A recovery code, shown once: in a monospace box, with Copy, then "I saved it" and its last group typed to
// confirm. The code lives only in the screen that shows it: the caller drops it when `onDone` comes, and it is
// never logged or stored. The core keeps only the last group, in memory, to check the confirmation.
import { type FormEvent, useId, useState } from "react";
import { coreLine, send } from "../core";
import { field, primary, secondary } from "../firstlaunch/parts";
import { pick, t, type Text, texts, useLanguage } from "../i18n";

export function RecoveryCode({ code, confirmPath, onDone }: { code: string; confirmPath: string; onDone: () => void }) {
  useLanguage();
  const id = useId();
  const [copied, setCopied] = useState(false);
  const [saving, setSaving] = useState(false);
  const [last, setLast] = useState("");
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState<Text>();

  async function confirm(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setFailed(undefined);
    const response = await send(confirmPath, "POST", { last_group: last.trim() });
    setBusy(false);
    if (response?.ok) onDone();
    else setFailed(await coreLine(response, texts.backupNotSaved));
  }

  return (
    <section aria-label={t("recoveryTitle")} className="flex flex-col gap-3 rounded-lg bg-stone px-4 py-4">
      <h3 className="font-semibold">{t("recoveryTitle")}</h3>
      <p className="text-slate">{t("recoveryShownOnce")}</p>
      <output
        dir="ltr"
        aria-label={t("recoveryTitle")}
        // no break-all: a long line breaks after a dash, between groups, never inside one
        className="rounded-md bg-paper px-3 py-3 text-center font-mono text-base tracking-wide select-all"
      >
        {code}
      </output>
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          className={secondary}
          onClick={() =>
            void navigator.clipboard
              ?.writeText(code)
              .then(() => setCopied(true))
              .catch(() => undefined)
          }
        >
          {t("recoveryCopy")}
        </button>
        {copied && <span className="text-sm text-slate">{t("recoveryCopied")}</span>}
        {!saving && (
          <button type="button" className={`${primary} ms-auto`} onClick={() => setSaving(true)}>
            {t("recoverySaved")}
          </button>
        )}
      </div>
      {saving && (
        <form onSubmit={confirm} className="flex flex-col gap-2">
          <label htmlFor={id}>{t("recoveryLastGroup")}</label>
          <div className="flex gap-2">
            <input
              id={id}
              dir="ltr"
              autoComplete="off"
              spellCheck={false}
              maxLength={20}
              value={last}
              onChange={(event) => setLast(event.target.value)}
              className={`${field} min-w-0 flex-1 font-mono uppercase`}
            />
            <button type="submit" disabled={busy || !last.trim()} className={primary}>
              {t("recoveryConfirm")}
            </button>
          </div>
        </form>
      )}
      {failed && (
        <p role="alert" className="text-copper">
          {pick(failed)}
        </p>
      )}
    </section>
  );
}
