// A recovery code, shown once: in a monospace box, with Copy, then "I saved it" and its last group typed to
// confirm, checked as soon as its five characters are in (no Confirm button). The code lives only in the screen that
// shows it: the caller drops it when `onDone` comes, and it is never logged or stored. The core keeps only the last
// group, in memory, to check the confirmation.
import { useId, useRef, useState } from "react";
import { coreLine, send } from "../core";
import { Feedback, field, primary, secondary } from "../firstlaunch/parts";
import { pick, t, type Text, texts, useLanguage } from "../i18n";

export function RecoveryCode({ code, confirmPath, onDone }: { code: string; confirmPath: string; onDone: () => void }) {
  useLanguage();
  const id = useId();
  const [copied, setCopied] = useState(false);
  const [saving, setSaving] = useState(false);
  const [last, setLast] = useState("");
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState<Text>();
  const tries = useRef(0); // only the latest group's answer shows
  const sent = useRef("");

  async function type(value: string) {
    setLast(value);
    const group = value.trim();
    if (group.replace(/[^a-z0-9]/gi, "").length !== 5) return; // a whole group of five, or nothing is sent
    if (group.toUpperCase() === sent.current) return; // a space after it: the same group, already sent
    sent.current = group.toUpperCase();
    const mine = ++tries.current;
    setBusy(true);
    setFailed(undefined);
    const response = await send(confirmPath, "POST", { last_group: group });
    if (mine !== tries.current) return;
    setBusy(false);
    if (response?.ok) return onDone();
    sent.current = ""; // refused: the next change is sent again
    setFailed(await coreLine(response, texts.backupNotSaved));
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
        <div className="flex flex-col gap-2">
          <label htmlFor={id}>{t("recoveryLastGroup")}</label>
          <input
            id={id}
            dir="ltr"
            autoComplete="off"
            spellCheck={false}
            maxLength={20}
            value={last}
            aria-invalid={failed ? true : undefined}
            onChange={(event) => void type(event.target.value)}
            className={`${field} min-w-0 font-mono uppercase ${failed ? "border-copper" : ""}`}
          />
          <div className="min-h-7">
            {busy && <Feedback state="busy">{t("aiLinkChecking")}</Feedback>}
            {failed && <Feedback state="failed">{pick(failed)}</Feedback>}
          </div>
        </div>
      )}
    </section>
  );
}
