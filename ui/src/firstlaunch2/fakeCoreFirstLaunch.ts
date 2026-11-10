// For tests only: the routes of today that first launch keeps using (GET /setup, the account, the AI consent, Claude
// Code), served beside the fake core with today's shapes. NEVER import this from application code.
//
// Call serveFirstLaunch() once in a test file, after startFakeCore(); `older` is what the core holds now, and a test
// changes it to set the scene. Every call to these routes is noted in `older.calls` ("PUT /setup/ai {...}").
import { http, HttpResponse } from "msw";
import { beforeEach } from "vitest";
import type { Account, Consent } from "@/api/existing";
import { server } from "@/api/fakeCore";

type Step = "done" | "skipped" | null;
type Older = {
  steps: { language: Step; account: Step; ai: Step; card: Step; usage: Step };
  consent: Consent;
  account: Account;
  /** What GET /account answers while a sign-in waits, from the second ask on. */
  signsInAs: Account;
  claudeCode: { found: boolean; answers: boolean };
  calls: string[];
};

export const older = {} as Older;

function reset(): void {
  Object.assign(older, {
    steps: { language: null, account: null, ai: null, card: null, usage: null },
    consent: { at: null, text_version: 3 },
    account: { state: "signed_out" },
    signsInAs: { state: "signed_in", email: "engineer@example.com", name: "مهندس تجريبي" },
    claudeCode: { found: true, answers: true },
    calls: [],
  } satisfies Older);
}
reset();

const setup = () => ({ done: older.steps.ai !== null, steps: older.steps });
async function note(request: Request, path: string): Promise<unknown> {
  const text = await request.text();
  older.calls.push(`${request.method} ${path}${text ? ` ${text}` : ""}`);
  return text ? JSON.parse(text) : undefined;
}

const handlers = [
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
  http.get("*/api/settings/claude-code", () => HttpResponse.json({ found: older.claudeCode.found, version: "2.1.0" })),
  http.post("*/api/settings/ai/check", async ({ request }) => {
    await note(request, "/settings/ai/check");
    if (older.claudeCode.answers) return HttpResponse.json({ ok: true });
    const words = { en: "Claude Code is not signed in. Sign in to it, then try again.", ar: "Claude Code مش داخل بحساب. ادخل بحسابك فيه، وبعدين جرّب تاني." };
    return HttpResponse.json({ error: words }, { status: 409 });
  }),
];

export function serveFirstLaunch(): void {
  beforeEach(() => {
    reset();
    server.use(...handlers);
  });
}
