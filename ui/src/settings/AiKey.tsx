// Add or replace the engineer's Claude key. No Save button: a pasted key is saved and checked at once, a typed one
// after a pause, once it is long enough to be whole (ui/live.tsx). The core keeps it in the system key store, and
// checks it with one tiny call (POST /settings/ai/check); the page never shows it again once the screen closes.
// `plain`: the field alone, with no title, help or frame, inside another screen (the first launch's Connect AI, whose
// choice already says what the key is).
import { useId } from "react";
import { coreLine, send } from "../core";
import { Feedback } from "../firstlaunch/parts";
import { pick, t, texts, useLanguage } from "../i18n";
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
  const { field, live } = useLiveKey(KEY_MIN.claude, async (value, signal) => {
    onChecking?.();
    const saved = await send("/settings/ai-key", "PUT", { provider: "anthropic", value }, signal);
    if (signal.aborted) return null;
    if (!saved?.ok) return coreLine(saved, texts.keyFailed);
    const checked = await send("/settings/ai/check", "POST", { via: "api_key" }, signal);
    if (signal.aborted) return null;
    onChecked?.(checked?.ok === true);
    return checked?.ok ? null : coreLine(checked, texts.claudeCodeCheckFailed);
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
      {/* the line's slot keeps its height, so nothing under the field moves when it changes */}
      <div className="min-h-7" data-key-line>
        {live.state === "short" && <p className="fl-rise text-slate">{t("keyTooShort")}</p>}
        {live.state === "busy" && <Feedback state="busy">{t("aiLinkChecking")}</Feedback>}
        {live.state === "done" && <Feedback state="done">{t("aiLinkWorks")}</Feedback>}
        {live.state === "failed" && <Feedback state="failed">{pick(live.line)}</Feedback>}
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
