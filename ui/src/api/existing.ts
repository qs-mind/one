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

/** The answer and its JSON body (undefined when it has none); null when the core cannot be reached. */
async function reach(path: string, init: RequestInit): Promise<{ response: Response; json: unknown } | null> {
  let response: Response;
  try {
    response = await api(path, init);
  } catch {
    return null;
  }
  return { response, json: await response.json().catch(() => undefined) };
}

const wordsOf = (json: unknown) => {
  const words = (json as { error?: unknown } | undefined)?.error;
  return isText(words) ? words : null;
};

async function request<T>(path: string, init: RequestInit): Promise<Answer<T>> {
  const got = await reach(path, init);
  if (!got) return { error: null };
  return got.response.ok ? { data: got.json as T } : { error: wordsOf(got.json) };
}

function call<T>(path: string, method = "GET", body?: unknown): Promise<Answer<T>> {
  const init: RequestInit = { method };
  if (body !== undefined) {
    init.headers = { "content-type": "application/json" };
    init.body = JSON.stringify(body);
  }
  return request<T>(path, init);
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

/** A link made by the provider's address, for a key ONE does not recognise (contract routes 23-24). It saves the
 * key; it does not check it. A bad address answers 422 with no words (`error: null`). */
export type StandardLink = { id: string; name: string; provider: string | null; key_set: boolean };
export const addStandard = (body: { name: string; base_url: string; key: string }) =>
  call<StandardLink>("/settings/ai/standard", "POST", body);

// Pages outside ONE ------------------------------------------------------------------------------------------------

/** The terms or the privacy policy. In the installed app the core opens the browser (POST /app/open); in a plain
 * browser, which may sit on another computer than the core, the page opens it in a new tab. */
export function openPage(link: "terms" | "privacy", lang: "ar" | "en"): void {
  if (inInstalledApp()) void call("/app/open", "POST", { link, lang });
  else window.open(`https://qsmind.app/${lang}/${link}`, "_blank", "noopener");
}

// Home: a dropped tender folder (contract S32) and the Home conversation (S28, S31, S36) ----------------------------

const idOf = (value: unknown) =>
  typeof value === "object" && value !== null && "id" in value ? String((value as { id: unknown }).id) : undefined;

/** POST /projects: a tender named after a dropped folder. A name already here answers 409 with that tender
 * (`taken`): two tenders never share a name. */
export async function createProject(folder: string): Promise<{ id: string } | { taken: string } | { error: Text | null }> {
  const got = await reach("/projects", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ folder }),
  });
  if (!got) return { error: null };
  const id = idOf(got.json);
  if (got.response.ok && id) return { id };
  const taken = got.response.status === 409 ? idOf((got.json as { project?: unknown } | undefined)?.project) : undefined;
  return taken ? { taken } : { error: wordsOf(got.json) };
}

const at = (project: string) => `/projects/${encodeURIComponent(project)}`;

export const openProject = (project: string) => call<unknown>(`${at(project)}/open`, "POST");

/** One file of the tender, with its place inside the dropped folder (`folder`, display text only). A zip answers
 * `{ files }`, one for each file it held. */
export type AddedFile = { id: string; duplicate?: boolean };
export function addFile(project: string, file: File, folder: string) {
  const query = `name=${encodeURIComponent(file.name)}${folder ? `&folder=${encodeURIComponent(folder)}` : ""}`;
  return request<AddedFile | { files: AddedFile[] }>(`${at(project)}/files?${query}`, { method: "POST", body: file });
}

/** ONE's own report of the files that came in. */
export const reportFiles = (project: string, file_ids: string[]) => call<unknown>(`${at(project)}/files/report`, "POST", { file_ids });

/** The Lead's first reading of a new tender. */
export const understand = (project: string) => call<unknown>(`${at(project)}/understand`, "POST");

/** The earlier messages of a conversation (UIMessages, as the chat stream sends them). */
export const getChatMessages = (chat: string) => call<{ messages?: unknown[] }>(`/chat/${encodeURIComponent(chat)}/messages`);

/** What the engineer writes to a Brief that runs, or waits on a card (answers 202). */
export const steerBrief = (brief: string, text: string) => call<unknown>(`/briefs/${encodeURIComponent(brief)}/steer`, "POST", { text });

/** The chat stream's fetch (POST /chat): its URLs are core routes, so they leave through api() too. */
export const chatFetch = (input: RequestInfo | URL, init?: RequestInit) => api(String(input), init);
