// Connect AI: first the consent (where the engineer's text goes, with the terms and the privacy policy), then how ONE
// reaches AI: the engineer's own Claude Code, an API key (the key field AI settings use), or another provider's
// OpenAI-compatible address and key (a Standard Link, audit R16). Neither choice can be
// made before "I understand"; the core refuses every AI call until then as well (AI_CONSENT_NEEDED). The same step
// opens alone from the chat's "Connect AI" when the consent is missing. No Check button: choosing Claude Code checks
// it at once (choosing it again, or coming back to ONE's window after a failed check, checks it again), and a key
// checks itself as it is pasted or typed. Next waits, in its place, until the check works, so no button moves.
import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { api, inInstalledApp } from "../api";
import { ProviderLogo } from "../brand/providers/ProviderLogo";
import { coreLine, send } from "../core";
import { fill, language, pick, t, type Text, texts, useLanguage } from "../i18n";
import { AiKey } from "../settings/AiKey";
import { KEY_MIN, useLiveKey } from "../ui/live";
import { DUR, reducedMotion } from "../ui/motion";
import { Feedback, type Nav, openSetup, option, primary, quiet, secondary, StepScreen } from "./parts";

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

type Via = "claude_code" | "api_key" | "standard";
type Check = "idle" | "checking" | "works" | Text;

export function ConnectAi({ nav }: { nav: Nav }) {
  useLanguage();
  const given = useConsent();
  const [failed, setFailed] = useState<Text>();
  const [via, setVia] = useState<Via>();
  const [found, setFound] = useState<{ found: boolean; version: string | null }>();
  const [check, setCheck] = useState<Check>("idle");
  const runs = useRef(0); // only the latest check's answer shows
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

  async function checkClaudeCode() {
    const mine = ++runs.current;
    setCheck("checking");
    let answer: Check = texts.aiLinkClaudeCodeMissing;
    if ((await findClaudeCode())?.found) {
      const response = await send("/settings/ai/check", "POST", { via: "claude_code" });
      answer = response?.ok ? "works" : await coreLine(response, texts.claudeCodeCheckFailed);
    }
    if (mine === runs.current) setCheck(answer);
  }

  // What a choice shows comes into view, clear of the step's bar (another provider's form opened below the fold): once
  // drawn, and again once the step has grown to it
  const shown = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!via) return;
    const reveal = () => shown.current?.scrollIntoView?.({ block: "nearest", behavior: reducedMotion() ? "auto" : "smooth" });
    reveal();
    const timer = setTimeout(reveal, DUR.long + 20);
    return () => clearTimeout(timer);
  }, [via]);

  function choose(chosen: Via) {
    runs.current++; // a check still running for the other choice is no longer this screen's answer
    setVia(chosen);
    setCheck("idle");
    if (chosen === "claude_code") void checkClaudeCode();
  }

  // Back in ONE's window after a failed check (Claude Code installed, or signed in, meanwhile): check it again.
  const again = useRef<() => void>(undefined);
  again.current = via === "claude_code" && typeof check === "object" ? () => void checkClaudeCode() : undefined;
  useEffect(() => {
    const back = () => again.current?.();
    window.addEventListener("focus", back);
    return () => window.removeEventListener("focus", back);
  }, []);

  return (
    <StepScreen
      title={t("connectAi")}
      nav={nav}
      failed={failed && pick(failed)}
      next={
        <button type="button" disabled={check !== "works"} onClick={() => void nav.pass("done")} className={primary}>
          {t("setupNext")}
        </button>
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
        {agreed && <Feedback state="done">{t("consentGiven")}</Feedback>}
      </div>

      <fieldset disabled={!agreed} className="flex min-w-0 flex-col gap-4">
        <legend className="mb-4 text-lg font-semibold">{t("aiLinkTitle")}</legend>
        {!agreed && <p className="text-slate">{t("aiLinkAfterConsent")}</p>}
        <div className="grid gap-3 sm:grid-cols-2">
          <button type="button" aria-pressed={via === "claude_code"} onClick={() => choose("claude_code")} className={`${option(via === "claude_code")} text-start`}>
            <span className="flex items-center gap-2 font-semibold">
              <ProviderLogo provider="anthropic" size={20} />
              {t("aiLinkClaudeCode")}
            </span>
            <span className={`block text-sm ${via === "claude_code" ? "text-paper/80" : "text-slate"}`}>{t("aiLinkClaudeCodeHelp")}</span>
          </button>
          <button type="button" aria-pressed={via === "api_key"} onClick={() => choose("api_key")} className={`${option(via === "api_key")} text-start`}>
            <span className="flex items-center gap-2 font-semibold">
              <ProviderLogo provider="anthropic" size={20} />
              {t("aiLinkApiKey")}
            </span>
            <span className={`block text-sm ${via === "api_key" ? "text-paper/80" : "text-slate"}`}>{t("aiLinkApiKeyHelp")}</span>
          </button>
          <button type="button" aria-pressed={via === "standard"} onClick={() => choose("standard")} className={`${option(via === "standard")} text-start sm:col-span-2`}>
            <span className="block font-semibold">{t("aiLinkStandard")}</span>
            <span className={`block text-sm ${via === "standard" ? "text-paper/80" : "text-slate"}`}>{t("aiLinkStandardHelp")}</span>
          </button>
        </div>

        {/* what the choice shows keeps one height (the key field's), so the buttons under it never move */}
        <div ref={shown} className="min-h-40 scroll-mb-28">
          {via === "claude_code" && (
            <div className="flex flex-col gap-2">
              {found?.found && <p className="fl-rise">{fill(t("aiLinkClaudeCodeFound"), { version: found.version ?? "" })}</p>}
              {check === "checking" && <Feedback state="busy">{t("aiLinkChecking")}</Feedback>}
              {check === "works" && <Feedback state="done">{t("aiLinkWorks")}</Feedback>}
              {typeof check === "object" && (
                <>
                  <Feedback state="failed">{pick(check)}</Feedback>
                  {/* every failed line ends "then try again": this is where (coming back to the window does it too) */}
                  <button type="button" onClick={() => void checkClaudeCode()} className={`${secondary} self-start`}>
                    {t("tryAgain")}
                  </button>
                </>
              )}
            </div>
          )}
          {via === "api_key" && <AiKey plain onChecking={() => setCheck("idle")} onChecked={(works) => setCheck(works ? "works" : "idle")} />}
          {via === "standard" && <StandardFirst onChecked={(works) => setCheck(works ? "works" : "idle")} />}
        </div>
      </fieldset>
    </StepScreen>
  );
}

const field = "rounded-md border border-slate bg-paper px-3 py-2 outline-none focus:border-ink";

/** Another provider: its name and OpenAI-compatible address, the model to use first if the engineer has one, then its
 * key, which adds the link and checks it at once (no Save or Check button). A link whose check fails is taken out
 * again, so a corrected key never leaves a second one. */
function StandardFirst({ onChecked }: { onChecked: (works: boolean) => void }) {
  const [name, setName] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [model, setModel] = useState("");
  const ready = name.trim() !== "" && baseUrl.trim() !== "";
  const key = useLiveKey(KEY_MIN.brave, async (value, signal) => {
    onChecked(false);
    // a typed model is the Lead QS's default, and the one the check runs on (finding 12)
    const typed = model.trim() ? { model: model.trim() } : {};
    const body = { name: name.trim(), base_url: baseUrl.trim(), ...typed, key: value };
    const added = await send("/settings/ai/standard", "POST", body, signal);
    if (!added?.ok) return coreLine(added, added?.status === 422 ? texts.providerUrlRefused : texts.providerNotAdded);
    const link = (await added.json().catch(() => undefined)) as { id?: string } | undefined;
    if (!link?.id) return texts.providerNotAdded;
    const checked = await send("/settings/ai/check", "POST", { via: "standard", connector: link.id }, signal);
    if (checked?.ok) {
      onChecked(true);
      return null;
    }
    const line = await coreLine(checked, texts.claudeCodeCheckFailed);
    await send(`/settings/ai/standard/${encodeURIComponent(link.id)}`, "DELETE");
    return line;
  });
  return (
    <div className="flex flex-col gap-2">
      <label className="flex flex-col gap-1">
        <span>{t("providerName")}</span>
        <input dir="auto" value={name} onChange={(event) => setName(event.target.value)} className={field} />
      </label>
      <label className="flex flex-col gap-1">
        <span>{t("baseUrl")}</span>
        <input type="url" dir="ltr" spellCheck={false} value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} className={field} />
      </label>
      <label className="flex flex-col gap-1">
        <span>{t("providerModel")}</span>
        <input dir="ltr" spellCheck={false} value={model} onChange={(event) => setModel(event.target.value)} className={field} />
      </label>
      <label className="flex flex-col gap-1">
        <span>{t("providerKey")}</span>
        <input type="password" dir="ltr" autoComplete="off" spellCheck={false} disabled={!ready} {...key.field} className={field} />
      </label>
      {key.live.state === "busy" && <Feedback state="busy">{t("aiLinkChecking")}</Feedback>}
      {key.live.state === "done" && <Feedback state="done">{t("aiLinkWorks")}</Feedback>}
      {key.live.state === "failed" && <Feedback state="failed">{pick(key.live.line)}</Feedback>}
    </div>
  );
}

/** A fixed outside page, in the page's language: the same addresses as the core's (journey/routes.py LINKS). */
const linkUrl = (link: "terms" | "privacy") => `https://qsmind.app/${language()}/${link}`;

/** A fixed outside link. In the installed app the core opens it in the browser (POST /app/open), never the page; in a
 * plain browser, which may be on another computer than the core, it is a real link, in a new tab. */
function OpenLink({ link, label, first = false }: { link: "terms" | "privacy"; label: string; first?: boolean }) {
  const look = `${quiet} ${first ? "-ms-3" : ""} underline decoration-slate/40 underline-offset-4`;
  if (!inInstalledApp())
    return (
      <a href={linkUrl(link)} target="_blank" rel="noopener" className={look}>
        {label}
      </a>
    );
  return (
    <button type="button" onClick={() => void send("/app/open", "POST", { link, lang: language() })} className={look}>
      {label}
    </button>
  );
}
