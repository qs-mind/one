// For tests and the fake-core dev page only: the routes of today that first launch keeps using (GET /setup, the account, the AI consent, Claude
// Code, a provider by its address), served beside the fake core with today's shapes. NEVER import this from application code.
//
// `older` is what the core holds now, and a test or the page changes it to set the scene. Every call to these routes
// is noted in `older.calls` ("PUT /setup/ai {...}"). Tests use it through fakeCoreFirstLaunch.ts.
import { http, HttpResponse } from "msw";
import type { Account, Consent } from "@/api/existing";

type Step = "done" | "skipped" | null;
type Older = {
  steps: { language: Step; account: Step; ai: Step; card: Step; usage: Step };
  consent: Consent;
  account: Account;
  /** What GET /account answers while a sign-in waits, from the second ask on. */
  signsInAs: Account;
  claudeCode: { found: boolean; answers: boolean };
  /** How many of the next POST /settings/ai/standard the core refuses (503, the key store is down). */
  standardRefuses: number;
  calls: string[];
};

export const older = {} as Older;

/** Puts back what the core holds at the start of a test. */
export function resetFirstLaunch(): void {
  Object.assign(older, {
    steps: { language: null, account: null, ai: null, card: null, usage: null },
    consent: { at: null, text_version: 3 },
    account: { state: "signed_out" },
    signsInAs: { state: "signed_in", email: "engineer@example.com", name: "مهندس تجريبي" },
    claudeCode: { found: true, answers: true },
    standardRefuses: 0,
    calls: [],
  } satisfies Older);
}
resetFirstLaunch();

const setup = () => ({ done: older.steps.ai !== null, steps: older.steps });
async function note(request: Request, path: string): Promise<unknown> {
  const text = await request.text();
  older.calls.push(`${request.method} ${path}${text ? ` ${text}` : ""}`);
  return text ? JSON.parse(text) : undefined;
}

/** Today's routes first launch keeps using, answered from `older`. */
export const firstLaunchRoutes = [
  http.get("*/api/setup", () => HttpResponse.json(setup())),
  http.put("*/api/setup/:step", async ({ request, params }) => {
    const body = (await note(request, `/setup/${String(params.step)}`)) as { state: Step };
    older.steps[params.step as keyof Older["steps"]] = body.state;
    return HttpResponse.json(setup());
  }),
  http.get("*/api/account", () => {
    const now = older.account;
    if (now.state === "waiting") older.account = older.signsInAs; // the browser finished meanwhile
    return HttpResponse.json(now);
  }),
  http.post("*/api/account/sign-in", async ({ request }) => {
    await note(request, "/account/sign-in");
    older.account = { state: "waiting" };
    return HttpResponse.json({ state: "waiting", url: "https://auth.qsmind.app/ar/account" });
  }),
  http.post("*/api/account/cancel", async ({ request }) => {
    await note(request, "/account/cancel");
    older.account = { state: "signed_out" };
    return HttpResponse.json(older.account);
  }),
  http.get("*/api/settings/ai-consent", () => HttpResponse.json(older.consent)),
  http.put("*/api/settings/ai-consent", async ({ request }) => {
    const body = (await note(request, "/settings/ai-consent")) as { text_version: number };
    older.consent = { at: "2026-11-10T09:00:00.000000+00:00", text_version: body.text_version };
    return HttpResponse.json({ at: older.consent.at });
  }),
  http.post("*/api/settings/ai/standard", async ({ request }) => {
    const body = (await note(request, "/settings/ai/standard")) as { name: string; base_url: string };
    if (older.standardRefuses > 0) {
      older.standardRefuses -= 1;
      const words = { en: "ONE could not keep the key just now. Try again.", ar: "ONE ماقدرش يحفظ المفتاح دلوقتي. جرّب تاني." };
      return HttpResponse.json({ error: words }, { status: 503 });
    }
    const link = { id: "standard:sample", kind: "standard", name: body.name, provider: body.name, on_device: false, key_set: true, error: null };
    return HttpResponse.json(link, { status: 201 });
  }),
  http.get("*/api/settings/claude-code", () => HttpResponse.json({ found: older.claudeCode.found, version: "2.1.0" })),
  http.post("*/api/settings/ai/check", async ({ request }) => {
    await note(request, "/settings/ai/check");
    if (older.claudeCode.answers) return HttpResponse.json({ ok: true });
    const words = { en: "Claude Code is not signed in. Sign in to it, then try again.", ar: "Claude Code مش داخل بحساب. ادخل بحسابك فيه، وبعدين جرّب تاني." };
    return HttpResponse.json({ error: words }, { status: 409 });
  }),
];
