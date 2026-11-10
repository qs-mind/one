// The routes of today that the new screens keep using (contract section 5). They are not in the contract's OpenAPI
// document, so their shapes are written here as the core answers them. Every call leaves through api(), as client.ts.
//
// A call answers { data } on 2xx and { error } otherwise: the core's {en, ar} words, or null when it gave none (a
// 503 with an empty body, or a core that cannot be reached). It never throws.
import { api, inInstalledApp } from "../api";
import type { Schemas } from "./client";

type Text = Schemas["Text"];
export type Answer<T> = { data: T; error?: undefined } | { data?: undefined; error: Text | null };

const isText = (value: unknown): value is Text =>
  typeof value === "object" && value !== null && typeof (value as Text).en === "string" && typeof (value as Text).ar === "string";

async function call<T>(path: string, method = "GET", body?: unknown): Promise<Answer<T>> {
  const init: RequestInit = { method };
  if (body !== undefined) {
    init.headers = { "content-type": "application/json" };
    init.body = JSON.stringify(body);
  }
  let response: Response;
  try {
    response = await api(path, init);
  } catch {
    return { error: null };
  }
  const json: unknown = await response.json().catch(() => undefined);
  if (response.ok) return { data: json as T };
  const words = (json as { error?: unknown } | undefined)?.error;
  return { error: isText(words) ? words : null };
}

// First launch: GET /setup and PUT /setup/{step} ------------------------------------------------------------------

export const getSetupSteps = () => call<Schemas["SetupSteps"]>("/setup");

/** Step 1 says the language chosen; step 3 ends "done", or "skipped" with no AI (contract Q2). */
export const passStep = (step: "language" | "ai", state: "done" | "skipped", lang?: "ar" | "en") =>
  call<Schemas["SetupSteps"]>(`/setup/${step}`, "PUT", lang ? { state, lang } : { state });

// The QS Mind account ---------------------------------------------------------------------------------------------

export type Account = {
  state: "signed_out" | "waiting" | "signed_in";
  email?: string | null;
  name?: string | null;
  url?: string;
  /** Why the last sign-in failed. */
  note?: Text;
};

export const getAccount = () => call<Account>("/account");
export const signIn = (locale: "ar" | "en") => call<Account>("/account/sign-in", "POST", { locale, device: false });
export const cancelSignIn = () => call<Account>("/account/cancel", "POST");

// The AI consent, and the engineer's own Claude Code ---------------------------------------------------------------

/** `at` is null until the engineer agreed to `text_version`. */
export type Consent = { at: string | null; text_version: number };

export const getConsent = () => call<Consent>("/settings/ai-consent");
export const giveConsent = (text_version: number) => call<{ at: string }>("/settings/ai-consent", "PUT", { text_version });

export const findClaudeCode = () => call<{ found: boolean; version: string | null }>("/settings/claude-code");

/** One small check through the engineer's Claude Code; one that answers is turned on by the core. */
export const checkClaudeCode = () => call<{ ok: true }>("/settings/ai/check", "POST", { via: "claude_code" });

// Pages outside ONE ------------------------------------------------------------------------------------------------

/** The terms or the privacy policy. In the installed app the core opens the browser (POST /app/open); in a plain
 * browser, which may sit on another computer than the core, the page opens it in a new tab. */
export function openPage(link: "terms" | "privacy", lang: "ar" | "en"): void {
  if (inInstalledApp()) void call("/app/open", "POST", { link, lang });
  else window.open(`https://qsmind.app/${lang}/${link}`, "_blank", "noopener");
}
