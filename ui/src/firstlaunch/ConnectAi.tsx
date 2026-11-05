// Connect AI: first the consent (where the engineer's text goes, with the terms and the privacy policy), then how One
// reaches AI: the engineer's own Claude Code, or an API key (the key field AI settings use). Neither choice can be
// made before "I understand"; the core refuses every AI call until then as well (AI_CONSENT_NEEDED). The same step
// opens alone from the chat's "Connect AI" when the consent is missing.
import { useEffect, useState, useSyncExternalStore } from "react";
import { api } from "../api";
import { coreLine, send } from "../core";
import { fill, language, pick, t, type Text, texts, useLanguage } from "../i18n";
import { AiKey } from "../settings/AiKey";
import { Alert, type Nav, openSetup, option, primary, quiet, secondary, StepScreen } from "./parts";

// The consent, as GET /settings/ai-consent says: `at` is null until the engineer said yes to `text_version`.
type Consent = { at: string | null; text_version: number };
let consent: Consent | undefined;
let asked: Promise<void> | undefined;
const listeners = new Set<() => void>();
const changed = (next: Consent | undefined) => {
  consent = next;
  for (const listener of listeners) listener();
};

function loadConsent(): Promise<void> {
  asked ??= api("/settings/ai-consent")
    .then((r) => (r.ok ? (r.json() as Promise<Consent>) : undefined))
    .then((body) => changed(body && typeof body.text_version === "number" ? body : undefined))
    .catch(() => undefined)
    .finally(() => (asked = undefined));
  return asked;
}

/** The consent; undefined while it loads, or when the core could not say. */
export function useConsent(): Consent | undefined {
  const now = useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    () => consent,
  );
  useEffect(() => {
    if (consent === undefined) void loadConsent();
  }, []);
  return now;
}

/** For tests: forget the consent read from the core. */
export function resetConsent() {
  consent = undefined;
  asked = undefined;
}

/** Above the chat while the consent is missing: what the core will answer, and the way to the step. */
export function ConsentNeeded() {
  useLanguage();
  const given = useConsent();
  if (!given || given.at !== null) return null;
  return (
    <div className="mx-5 mt-4 flex flex-wrap items-center gap-x-4 gap-y-2 rounded-lg bg-stone px-4 py-3">
      <p className="min-w-0 flex-1">{t("consentNeeded")}</p>
      <button type="button" onClick={() => openSetup("ai", true)} className={primary}>
        {t("connectAi")}
      </button>
    </div>
  );
}

type Via = "claude_code" | "api_key";
type Check = "idle" | "checking" | "works" | Text;

export function ConnectAi({ nav }: { nav: Nav }) {
  useLanguage();
  const given = useConsent();
  const [failed, setFailed] = useState<Text>();
  const [via, setVia] = useState<Via>();
  const [found, setFound] = useState<{ found: boolean; version: string | null }>();
  const [check, setCheck] = useState<Check>("idle");
  const agreed = given?.at != null;

  async function agree() {
    setFailed(undefined);
    const response = await send("/settings/ai-consent", "PUT", { text_version: given?.text_version ?? 1 });
    if (!response?.ok) return setFailed(texts.consentNotSaved);
    const body = (await response.json().catch(() => ({}))) as { at?: string };
    changed({ at: body.at ?? new Date().toISOString(), text_version: given?.text_version ?? 1 });
  }

  async function findClaudeCode() {
    const response = await api("/settings/claude-code").catch(() => undefined);
    const body = response?.ok ? ((await response.json().catch(() => undefined)) as typeof found) : undefined;
    setFound(body ?? { found: false, version: null });
    return body;
  }

  async function run(chosen: Via) {
    setCheck("checking");
    if (chosen === "claude_code" && !(await findClaudeCode())?.found) return setCheck("idle");
    const response = await send("/settings/ai/check", "POST", { via: chosen });
    setCheck(response?.ok ? "works" : await coreLine(response, texts.claudeCodeCheckFailed));
  }

  function choose(chosen: Via) {
    setVia(chosen);
    setCheck("idle");
    if (chosen === "claude_code" && !found) void findClaudeCode();
  }

  const checking = check === "checking";
  return (
    <StepScreen
      title={t("connectAi")}
      nav={nav}
      failed={failed && pick(failed)}
      next={
        check === "works" && (
          <button type="button" onClick={() => void nav.pass("done")} className={primary}>
            {t("setupNext")}
          </button>
        )
      }
    >
      <div className="flex flex-col gap-3 rounded-lg bg-stone px-5 py-4">
        <h2 className="text-lg font-semibold">{t("consentTitle")}</h2>
        <p>{t("consentBody")}</p>
        <div className="flex flex-wrap items-center gap-x-1 gap-y-2">
          <OpenLink link="terms" label={t("consentTerms")} first />
          <OpenLink link="privacy" label={t("consentPrivacy")} />
          {given && !agreed && (
            <button type="button" onClick={() => void agree()} className={`${primary} ms-auto`}>
              {t("consentAgree")}
            </button>
          )}
        </div>
      </div>

      <fieldset disabled={!agreed} className="flex min-w-0 flex-col gap-4 disabled:opacity-60">
        <legend className="mb-4 text-lg font-semibold">{t("aiLinkTitle")}</legend>
        {!agreed && <p className="text-slate">{t("aiLinkAfterConsent")}</p>}
        <div className="grid gap-3 sm:grid-cols-2">
          <button type="button" aria-pressed={via === "claude_code"} onClick={() => choose("claude_code")} className={option(via === "claude_code")}>
            <span className="block font-semibold">{t("aiLinkClaudeCode")}</span>
            <span className={`block text-sm ${via === "claude_code" ? "text-paper/80" : "text-slate"}`}>{t("aiLinkClaudeCodeHelp")}</span>
          </button>
          <button type="button" aria-pressed={via === "api_key"} onClick={() => choose("api_key")} className={option(via === "api_key")}>
            <span className="block font-semibold">{t("aiLinkApiKey")}</span>
            <span className={`block text-sm ${via === "api_key" ? "text-paper/80" : "text-slate"}`}>{t("aiLinkApiKeyHelp")}</span>
          </button>
        </div>

        {via === "claude_code" && (
          <div className="flex flex-col gap-3">
            {found &&
              (found.found ? (
                <p>{fill(t("aiLinkClaudeCodeFound"), { version: found.version ?? "" })}</p>
              ) : (
                <p className="text-slate">{t("aiLinkClaudeCodeMissing")}</p>
              ))}
            <div>
              <button type="button" disabled={checking} onClick={() => void run("claude_code")} className={secondary}>
                {t("aiLinkCheck")}
              </button>
            </div>
          </div>
        )}
        {via === "api_key" && <AiKey plain onSaved={() => void run("api_key")} />}

        {checking && <p className="text-slate">{t("aiLinkChecking")}</p>}
        {check === "works" && <p role="status">{t("aiLinkWorks")}</p>}
        {typeof check === "object" && <Alert>{pick(check)}</Alert>}
      </fieldset>
    </StepScreen>
  );
}

/** A fixed outside link, opened by the core in the browser (POST /app/open), never by the page. */
function OpenLink({ link, label, first = false }: { link: "terms" | "privacy"; label: string; first?: boolean }) {
  return (
    <button
      type="button"
      onClick={() => void send("/app/open", "POST", { link, lang: language() })}
      className={`${quiet} ${first ? "-ms-3" : ""} underline decoration-slate/40 underline-offset-4`}
    >
      {label}
    </button>
  );
}
