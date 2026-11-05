// Add or replace the engineer's Claude key. No Save button: a pasted key is saved and checked at once, a typed one
// after a pause, once it is long enough to be whole (ui/live.tsx). The core keeps it in the system key store, and
// checks it with one tiny call (POST /settings/ai/check). A key that works leaves the field: the page never shows it
// again. One that fails stays, to be fixed.
// `plain`: the field alone, with no title, help or frame, inside another screen (the first launch's Connect AI, whose
// choice already says what the key is).
// A failed line never sends the engineer elsewhere: this field is where the key is fixed. After no internet or a busy
// provider (fix "retry") a Try again checks the same key once more; before the consent (fix "consent"), Connect AI.
import { useId, useRef } from "react";
import { coreAnswer, type Fix, send } from "../core";
import { Feedback, secondary } from "../firstlaunch/parts";
import { pick, t, texts, useLanguage } from "../i18n";
import { FixAction } from "../shell/FixAction";
import { KEY_MIN, useLiveKey } from "../ui/live";

export function AiKey({
  onChecking,
  onChecked,
  onClose,
  plain = false,
}: {
  /** A new key is being saved and checked. */
  onChecking?: () => void;
  /** The key was saved and checked: whether it works. */
  onChecked?: (works: boolean) => void;
  onClose?: () => void;
  plain?: boolean;
}) {
  useLanguage();
  const id = useId();
  const fix = useRef<Fix>(undefined); // what fixes the line shown, as the core says
  const { field, live, again } = useLiveKey(KEY_MIN.claude, async (value, signal) => {
    onChecking?.();
    fix.current = undefined;
    const saved = await send("/settings/ai-key", "PUT", { provider: "anthropic", value }, signal);
    if (signal.aborted) return null;
    if (!saved?.ok) {
      const answer = await coreAnswer(saved, texts.keyFailed);
      fix.current = answer.fix;
      return answer.line;
    }
    const checked = await send("/settings/ai/check", "POST", { via: "api_key" }, signal);
    if (signal.aborted) return null;
    onChecked?.(checked?.ok === true);
    if (checked?.ok) return null;
    const answer = await coreAnswer(checked, texts.claudeCodeCheckFailed);
    fix.current = answer.fix;
    return answer.line;
  });

  const body = (
    <div className="flex flex-col gap-2">
      {!plain && <p className="text-slate">{t("aiKeyHelp")}</p>}
      <label htmlFor={id}>{t("aiKeyLabel")}</label>
      <input
        id={id}
        type="password"
        dir="ltr"
        autoComplete="off"
        spellCheck={false}
        {...field}
        aria-invalid={live.state === "failed" || undefined}
        className={`rounded-md border bg-paper px-3 py-2 outline-none transition-colors duration-150 ease-out focus:border-ink ${
          live.state === "failed" ? "border-copper" : "border-slate"
        }`}
      />
      {/* the line's slot keeps two lines' height, so nothing under the field moves when it changes */}
      <div className="min-h-16" data-key-line>
        {live.state === "short" && <p className="fl-rise text-slate">{t("keyTooShort")}</p>}
        {live.state === "busy" && <Feedback state="busy">{t("aiLinkChecking")}</Feedback>}
        {live.state === "done" && <Feedback state="done">{t("aiLinkWorks")}</Feedback>}
        {live.state === "failed" && (
          <div className="flex flex-col gap-2">
            <Feedback state="failed">{pick(live.line)}</Feedback>
            {fix.current === "retry" && (
              <button type="button" onClick={again} className={`${secondary} self-start`}>
                {t("tryAgain")}
              </button>
            )}
            {fix.current === "consent" && <FixAction fix="consent" />}
          </div>
        )}
      </div>
    </div>
  );
  if (plain) return body;

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
        {body}
      </div>
    </section>
  );
}
