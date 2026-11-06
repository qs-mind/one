import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { crashReport, reportCrash, resetCrashReports } from "../app/crash";
import { language, setLanguage, texts } from "../i18n";
import { perMillion } from "../ui/digits";
import { ConsentNeeded, resetConsent } from "./ConnectAi";
import { FirstLaunch, SetupGate } from "./FirstLaunch";
import { closeSetup, type Setup, type Step, STEPS } from "./parts";

type Handler = (body: Record<string, unknown> | undefined) => Response | Promise<Response>;

const fresh = (): Setup => ({ done: false, steps: { language: null, account: null, ai: null, card: null, usage: null } });

/** The core behind /api, from the HTTP contract of Plan 8: the setup steps, then whatever a test adds. */
function mockCore(routes: Record<string, Handler> = {}) {
  const setup = fresh();
  const fetch = vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const path = String(input).replace(/^\/api/, "");
    const key = `${init.method ?? "GET"} ${path}`;
    const body = init.body ? (JSON.parse(String(init.body)) as Record<string, unknown>) : undefined;
    if (routes[key]) return routes[key](body);
    if (key === "GET /setup") return Response.json(setup);
    const step = /^PUT \/setup\/(\w+)$/.exec(key)?.[1] as Step | undefined;
    if (step) {
      setup.steps[step] = body!.state as "done" | "skipped";
      setup.done = STEPS.every((s) => setup.steps[s] !== null);
      return Response.json(setup);
    }
    if (key === "GET /settings/ai-consent") return Response.json({ at: null, text_version: 1 });
    if (key === "GET /account") return Response.json({ state: "signed_out" });
    if (key === "GET /engineer/card") return Response.json({});
    if (key === "GET /settings/usage-stats") return Response.json({ on: null });
    return new Response("not found", { status: 404 });
  });
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

const calls = (fetch: ReturnType<typeof mockCore>, key: string) =>
  fetch.mock.calls
    .filter(([url, init]) => `${init?.method ?? "GET"} ${String(url).replace(/^\/api/, "")}` === key)
    .map(([, init]) => (init?.body ? (JSON.parse(String(init.body)) as Record<string, unknown>) : undefined));

/** A sample key, long enough to be whole: not a real key. */
const KEY = "sk-ant-sample-not-a-real-key-0000000000000000";

/** The buttons whose name is Save or Check, in either language: none must be left. */
const noSaveOrCheck = () =>
  screen
    .queryAllByRole("button")
    .map((button) => button.textContent ?? "")
    .filter((name) => /\b(save|check)\b|حفظ|احفظ|افحص|اتأكد/i.test(name));

/** A choice button, named by its title and its help line. */
const choice = (title: string) => (name: string) => name.startsWith(title);

function systemLanguageIs(lang: string) {
  vi.spyOn(navigator, "languages", "get").mockReturnValue([lang]);
  vi.spyOn(navigator, "language", "get").mockReturnValue(lang);
}

/** The flow, opened at `from`, in English unless said otherwise. */
function flowAt(from: Step | undefined, onDone = vi.fn()) {
  const setup = fresh();
  if (from) for (const step of STEPS.slice(0, STEPS.indexOf(from))) setup.steps[step] = "skipped";
  render(<FirstLaunch initial={setup} onDone={onDone} />);
  return onDone;
}

beforeEach(() => {
  resetConsent();
  resetCrashReports();
  closeSetup();
  systemLanguageIs("en-US");
  setLanguage("en");
});
afterEach(() => vi.useRealTimers());

describe("FirstLaunch", () => {
  it("skips through every step and lands in the app", async () => {
    const fetch = mockCore();
    const user = userEvent.setup();
    render(
      <SetupGate>
        <p>the app</p>
      </SetupGate>,
    );
    for (const title of ["languageTitle", "accountTitle", "connectAi", "cardTitle", "usageTitle"] as const) {
      expect(await screen.findByRole("heading", { level: 1, name: texts[title].en })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: texts.setupSkip.en })).toBeInTheDocument();
      await user.click(screen.getByRole("button", { name: texts.setupSkip.en }));
    }
    expect(await screen.findByRole("heading", { level: 1, name: texts.readyTitle.en })).toBeInTheDocument();
    expect(screen.getByText(texts.aiLinkLater.en)).toBeInTheDocument(); // AI was skipped: where to connect it later
    for (const step of STEPS) expect(calls(fetch, `PUT /setup/${step}`)[0]).toMatchObject({ state: "skipped" });
    expect(calls(fetch, "PUT /setup/language")[0]).toEqual({ state: "skipped", lang: "en" });
    await user.click(screen.getByRole("button", { name: texts.readyStart.en }));
    expect(screen.getByText("the app")).toBeInTheDocument();
    expect(calls(fetch, "PUT /settings/usage-stats")).toHaveLength(0); // skipping Usage Stats sends no "yes"
  });

  it("shows the app when the first launch was passed, and opens the flow again from Setup", async () => {
    mockCore({ "GET /setup": () => Response.json({ ...fresh(), done: true }) });
    render(
      <SetupGate>
        <button type="button">in the app</button>
      </SetupGate>,
    );
    expect(await screen.findByRole("button", { name: "in the app" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { level: 1 })).toBeNull();
    const { openSetup } = await import("./parts");
    act(() => openSetup());
    expect(await screen.findByRole("heading", { level: 1, name: texts.languageTitle.en })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "in the app" }).closest("[inert]")).not.toBeNull(); // inert under the flow
  });

  it("follows the system language the very first time", async () => {
    mockCore();
    systemLanguageIs("ar-EG");
    flowAt(undefined);
    expect(await screen.findByRole("heading", { level: 1, name: texts.languageTitle.ar })).toBeInTheDocument();
    expect(language()).toBe("ar");
    expect(document.documentElement.dir).toBe("rtl");
    expect(screen.getByRole("button", { name: "العربية" })).toHaveAttribute("aria-pressed", "true");
  });

  it("the language chosen goes to the core with the step", async () => {
    const fetch = mockCore();
    const user = userEvent.setup();
    flowAt(undefined);
    await user.click(screen.getByRole("button", { name: "العربية" }));
    expect(document.documentElement.lang).toBe("ar");
    await user.click(screen.getByRole("button", { name: texts.setupNext.ar }));
    expect(calls(fetch, "PUT /setup/language")[0]).toEqual({ state: "done", lang: "ar" });
    expect(await screen.findByRole("heading", { level: 1, name: texts.accountTitle.ar })).toBeInTheDocument();
  });

  it("signs in: opens the browser through the core and waits", async () => {
    let polls = 0;
    const fetch = mockCore({
      "POST /account/sign-in": () => Response.json({ state: "waiting", url: "https://auth.example/authorize?x=1" }),
      "GET /account": () => {
        polls += 1;
        return Response.json(polls < 3 ? { state: polls === 1 ? "signed_out" : "waiting" } : { state: "signed_in", email: "qs@example.com" });
      },
    });
    const user = userEvent.setup();
    flowAt("account");
    await user.click(await screen.findByRole("button", { name: texts.accountSignIn.en }));
    expect(calls(fetch, "POST /account/sign-in")[0]).toEqual({ locale: "en", device: false });
    expect(await screen.findByText(texts.accountWaiting.en)).toBeInTheDocument();
    expect(await screen.findByText("Signed in as qs@example.com", {}, { timeout: 4000 })).toBeInTheDocument();
    expect(calls(fetch, "GET /account").length).toBeGreaterThanOrEqual(3);
    await user.click(screen.getByRole("button", { name: texts.setupNext.en }));
    expect(calls(fetch, "PUT /setup/account")[0]).toEqual({ state: "done" });
  });

  it("shows the sign-in link when the browser does not open", async () => {
    mockCore({
      "POST /account/sign-in": () => Response.json({ state: "waiting", url: "https://auth.example/authorize?x=1" }),
    });
    const user = userEvent.setup();
    flowAt("account");
    await user.click(await screen.findByRole("button", { name: texts.accountSignIn.en }));
    expect(await screen.findByText(texts.accountNoBrowser.en)).toBeInTheDocument();
    const link = screen.getByText("https://auth.example/authorize?x=1");
    expect(link.tagName).toBe("CODE"); // text to copy: the page opens no link itself
    expect(document.querySelector("a")).toBeNull();
  });

  it("signs in on another device: the code, and the device page as a link in a new tab", async () => {
    const device = { user_code: "SAMPLE12", verification_uri: "https://auth.example/device" };
    const waiting = { state: "waiting", url: "https://auth.example/device?user_code=SAMPLE12", device };
    let started = false;
    const fetch = mockCore({
      "POST /account/sign-in": () => ((started = true), Response.json(waiting)),
      "GET /account": () => Response.json(started ? waiting : { state: "signed_out" }),
    });
    const user = userEvent.setup();
    flowAt("account");
    await screen.findByText(texts.accountSignInHow.en);
    await user.click(screen.getByRole("button", { name: texts.accountUseDevice.en }));
    expect(calls(fetch, "POST /account/sign-in")[0]).toEqual({ locale: "en", device: true });
    expect(await screen.findByText("SAMPLE12")).toBeInTheDocument();
    const page = screen.getByRole("link", { name: "auth.example/device" });
    expect(page).toHaveAttribute("href", "https://auth.example/device?user_code=SAMPLE12");
    expect(page).toHaveAttribute("target", "_blank");
    expect(screen.getByText(texts.accountDeviceWaiting.en).closest("[data-feedback]")).toHaveAttribute("data-feedback", "busy");
  });

  it("a sign-in that fails says why, in the core's words", async () => {
    const note = { en: "The sign-in ran out of time (sample).", ar: "وقت الدخول خلص (عينة)." };
    let polls = 0;
    mockCore({
      "POST /account/sign-in": () => Response.json({ state: "waiting", url: "https://auth.example/authorize?x=1" }),
      "GET /account": () => Response.json((polls += 1) < 2 ? { state: "signed_out" } : { state: "signed_out", note }),
    });
    const user = userEvent.setup();
    flowAt("account");
    await user.click(await screen.findByRole("button", { name: texts.accountSignIn.en }));
    expect(await screen.findByRole("alert", {}, { timeout: 4000 })).toHaveTextContent(note.en);
    expect(screen.getByRole("button", { name: texts.accountSignIn.en })).toBeEnabled(); // and it can start again
  });

  it("a sign-in still waiting is stopped when the step is skipped", async () => {
    const fetch = mockCore({
      "POST /account/sign-in": () => Response.json({ state: "waiting" }),
      "POST /account/cancel": () => Response.json({ state: "signed_out" }),
    });
    const user = userEvent.setup();
    flowAt("account");
    await user.click(await screen.findByRole("button", { name: texts.accountSignIn.en }));
    await screen.findByText(texts.accountWaiting.en);
    await user.click(screen.getByRole("button", { name: texts.setupSkip.en }));
    await waitFor(() => expect(calls(fetch, "PUT /setup/account")).toHaveLength(1));
    expect(calls(fetch, "POST /account/cancel")).toHaveLength(1);
  });

  it("asks for consent before any AI choice", async () => {
    const fetch = mockCore({ "PUT /settings/ai-consent": () => Response.json({ at: "2026-11-05T08:00:00+00:00" }) });
    const user = userEvent.setup();
    flowAt("ai");
    const agree = await screen.findByRole("button", { name: texts.consentAgree.en });
    expect(screen.getByText(texts.consentBody.en)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: choice(texts.aiLinkClaudeCode.en) })).toBeDisabled();
    expect(screen.getByRole("button", { name: choice(texts.aiLinkApiKey.en) })).toBeDisabled();
    expect(screen.getByText(texts.aiLinkAfterConsent.en)).toBeInTheDocument();

    // in a plain browser (maybe on another computer than the core) the website's pages open in a new tab
    const terms = screen.getByRole("link", { name: texts.consentTerms.en });
    expect(terms).toHaveAttribute("href", "https://qsmind.app/en/terms");
    expect(terms).toHaveAttribute("target", "_blank");
    expect(terms).toHaveAttribute("rel", "noopener");
    expect(screen.getByRole("link", { name: texts.consentPrivacy.en })).toHaveAttribute("href", "https://qsmind.app/en/privacy");
    expect(calls(fetch, "POST /app/open")).toHaveLength(0);

    await user.click(agree);
    expect(calls(fetch, "PUT /settings/ai-consent")[0]).toEqual({ text_version: 1 });
    expect(await screen.findByRole("button", { name: choice(texts.aiLinkApiKey.en) })).toBeEnabled();
    expect(screen.queryByRole("button", { name: texts.consentAgree.en })).toBeNull();
    expect(screen.getByText(texts.consentGiven.en).closest("[data-feedback]")).toHaveAttribute("data-feedback", "done");
    expect(calls(fetch, "POST /settings/ai/check")).toHaveLength(0); // no AI call was asked for
  });

  it("a pasted API key is saved, then checked through the core, at once", async () => {
    const fetch = mockCore({
      "GET /settings/ai-consent": () => Response.json({ at: "2026-11-05T08:00:00+00:00", text_version: 1 }),
      "PUT /settings/ai-key": () => Response.json({ set: true }),
      "POST /settings/ai/check": () => Response.json({ ok: true }),
    });
    const user = userEvent.setup();
    flowAt("ai");
    await user.click(await screen.findByRole("button", { name: choice(texts.aiLinkApiKey.en) }));
    const next = screen.getByRole("button", { name: texts.setupNext.en });
    expect(next).toBeDisabled(); // in its place from the start, so no button moves when it works
    await user.click(screen.getByLabelText(texts.aiKeyLabel.en));
    await user.paste(KEY);
    const works = await screen.findByText(texts.aiLinkWorks.en, {}, { timeout: 300 }); // no wait for a pause
    expect(works.closest("[data-feedback]")).toHaveAttribute("data-feedback", "done"); // the same mark on every step
    expect(works.closest("[role=status]")).not.toBeNull();
    expect(calls(fetch, "PUT /settings/ai-key")).toEqual([{ provider: "anthropic", value: KEY }]);
    expect(calls(fetch, "POST /settings/ai/check")[0]).toEqual({ via: "api_key" });
    expect(next).toBeEnabled();
    await user.click(next);
    expect(calls(fetch, "PUT /setup/ai")[0]).toEqual({ state: "done" });
  });

  it("another AI provider: its address and key are added as a Standard Link and checked at once (audit R16)", async () => {
    const link = { id: "standard:g1", kind: "model", name: "Gemini - sample", provider: "google", on_device: false, key_set: true, error: null };
    const fetch = mockCore({
      "GET /settings/ai-consent": () => Response.json({ at: "2026-11-05T08:00:00+00:00", text_version: 1 }),
      "POST /settings/ai/standard": () => Response.json(link, { status: 201 }),
      "POST /settings/ai/check": () => Response.json({ ok: true }),
    });
    const user = userEvent.setup();
    flowAt("ai");
    await user.click(await screen.findByRole("button", { name: choice(texts.aiLinkStandard.en) }));
    await user.type(screen.getByLabelText(texts.providerName.en), "Gemini - sample");
    await user.type(screen.getByLabelText(texts.baseUrl.en), "https://generativelanguage.googleapis.com/v1beta/openai");
    await user.click(screen.getByLabelText(texts.providerKey.en));
    await user.paste("sample-google-key-not-real");
    expect(await screen.findByText(texts.aiLinkWorks.en, {}, { timeout: 2000 })).toBeInTheDocument();
    expect(calls(fetch, "POST /settings/ai/standard")).toEqual([
      { name: "Gemini - sample", base_url: "https://generativelanguage.googleapis.com/v1beta/openai", key: "sample-google-key-not-real" },
    ]);
    expect(calls(fetch, "POST /settings/ai/check")).toEqual([{ via: "standard", connector: "standard:g1" }]);
    expect(noSaveOrCheck()).toEqual([]);
    expect(screen.getByRole("button", { name: texts.setupNext.en })).toBeEnabled();
  });

  it("another AI provider: Google Gemini fills its name and address, and the checking line comes into view", async () => {
    const link = { id: "standard:g4", kind: "model", name: "Google Gemini", provider: "google", on_device: false, key_set: true, error: null };
    let answer: (r: Response) => void = () => {};
    const fetch = mockCore({
      "GET /settings/ai-consent": () => Response.json({ at: "2026-11-05T08:00:00+00:00", text_version: 1 }),
      "POST /settings/ai/standard": () => Response.json(link, { status: 201 }),
      "POST /settings/ai/check": () => new Promise<Response>((resolve) => (answer = resolve)),
    });
    const seen = vi.fn();
    Element.prototype.scrollIntoView = function (this: Element) {
      seen(this.textContent);
    };
    const user = userEvent.setup();
    flowAt("ai");
    await user.click(await screen.findByRole("button", { name: choice(texts.aiLinkStandard.en) }));
    await user.click(screen.getByRole("button", { name: texts.presetGemini.en }));
    expect(screen.getByLabelText(texts.providerName.en)).toHaveValue("Google Gemini");
    expect(screen.getByLabelText(texts.baseUrl.en)).toHaveValue("https://generativelanguage.googleapis.com/v1beta/openai");
    await user.click(screen.getByLabelText(texts.providerKey.en));
    await user.paste("sample-google-key-not-real");
    const checking = await screen.findByText(texts.aiLinkChecking.en, {}, { timeout: 2000 });
    await waitFor(() => expect(seen).toHaveBeenCalledWith(texts.aiLinkChecking.en));
    // real walk: the line sat half under the bar's fade; it keeps clear of the bar and its fade
    expect(checking.closest("[data-feedback]")).toHaveClass("scroll-mb-32");
    answer(Response.json({ ok: true }));
    expect(await screen.findByText(texts.aiLinkWorks.en)).toBeInTheDocument();
    expect(calls(fetch, "POST /settings/ai/standard")[0]).toMatchObject({ name: "Google Gemini" });
    delete (Element.prototype as { scrollIntoView?: unknown }).scrollIntoView;
  });

  it("another AI provider: the model the engineer typed goes with the link (finding 12)", async () => {
    const link = { id: "standard:g3", kind: "model", name: "Gemini - sample", provider: "google", on_device: false, key_set: true, error: null };
    const fetch = mockCore({
      "GET /settings/ai-consent": () => Response.json({ at: "2026-11-05T08:00:00+00:00", text_version: 1 }),
      "POST /settings/ai/standard": () => Response.json(link, { status: 201 }),
      "POST /settings/ai/check": () => Response.json({ ok: true }),
    });
    const user = userEvent.setup();
    flowAt("ai");
    await user.click(await screen.findByRole("button", { name: choice(texts.aiLinkStandard.en) }));
    await user.type(screen.getByLabelText(texts.providerName.en), "Gemini - sample");
    await user.type(screen.getByLabelText(texts.baseUrl.en), "https://generativelanguage.googleapis.com/v1beta/openai");
    await user.type(screen.getByLabelText(texts.providerModel.en), "gemini-3.1-flash-lite");
    await user.click(screen.getByLabelText(texts.providerKey.en));
    await user.paste("sample-google-key-not-real");
    expect(await screen.findByText(texts.aiLinkWorks.en, {}, { timeout: 2000 })).toBeInTheDocument();
    expect(calls(fetch, "POST /settings/ai/standard")[0]).toMatchObject({ model: "gemini-3.1-flash-lite" });
  });

  it("Ready names each role's model with its price, and a way to change them (finding 12)", async () => {
    const card = (model: string, name: string, price_in: string | null, price_out: string | null) => ({
      connector: "standard:g",
      model,
      name,
      provider: "google",
      images: false,
      tools: true,
      context: null,
      price_in,
      price_out,
      price_source: price_in ? "genai-prices 0.2.1: https://ai.google.dev/pricing (sample)" : null,
      on_device: false,
      subscription: false,
    });
    const lite = card("models/gemini-3.1-flash-lite", "Gemini 3.1 Flash Lite", "0.25", "1.5");
    const gemma = card("models/gemma-3-27b-it", "gemma-3-27b-it", null, null);
    const pick = (c: typeof lite) => ({ connector: c.connector, model: c.model });
    const roles = { lead: pick(lite), checker: pick(gemma), specialist: pick(lite), quick: pick(lite) };
    mockCore({
      "GET /settings/ai": () =>
        Response.json({ connectors: [], sheet: [lite, gemma], roles, defaults: roles, effort: null, key_store: "system" }),
    });
    const { onOpenPanel } = await import("../shell/FixAction");
    const user = userEvent.setup();
    const onDone = flowAt("usage");
    await user.click(await screen.findByRole("button", { name: texts.setupSkip.en }));
    const line = await screen.findByText((_, el) => el?.tagName === "P" && (el.textContent ?? "").startsWith(texts.roleLead.en));
    expect(line.textContent).toBe(
      `${texts.roleLead.en}: Gemini 3.1 Flash Lite (${perMillion("0.25", "1.5")}) · ` +
        `${texts.roleChecker.en}: gemma-3-27b-it (${texts.priceUnknown.en}) · ` +
        `${texts.roleSpecialist.en}: Gemini 3.1 Flash Lite (${perMillion("0.25", "1.5")}) · ` +
        `${texts.roleQuick.en}: Gemini 3.1 Flash Lite (${perMillion("0.25", "1.5")})`,
    );
    expect(screen.getByText(/genai-prices 0\.2\.1/)).toBeInTheDocument(); // every price with its source
    await user.click(screen.getByRole("button", { name: texts.readyRolesChange.en }));
    expect(onDone).toHaveBeenCalled();
    const opened = vi.fn();
    onOpenPanel(opened)(); // the app, once it shows, opens AI settings
    expect(opened).toHaveBeenCalledWith("ai");
  });

  it("another AI provider: its form comes into view, clear of the buttons' bar (tender day: it opened below the fold)", async () => {
    mockCore({ "GET /settings/ai-consent": () => Response.json({ at: "2026-11-05T08:00:00+00:00", text_version: 1 }) });
    const scrolled: { el: Element; how: ScrollIntoViewOptions | boolean | undefined }[] = [];
    Element.prototype.scrollIntoView = function (this: Element, how?: ScrollIntoViewOptions | boolean) {
      scrolled.push({ el: this, how });
    };
    try {
      const user = userEvent.setup();
      flowAt("ai");
      await user.click(await screen.findByRole("button", { name: choice(texts.aiLinkStandard.en) }));
      const name = screen.getByLabelText(texts.providerName.en);
      await waitFor(() => expect(scrolled.some(({ el }) => el.contains(name))).toBe(true));
      const { el, how } = scrolled.find(({ el }) => el.contains(name))!;
      expect(how).toMatchObject({ block: "nearest" });
      expect(el).toHaveClass("scroll-mb-28"); // kept above the sticky bar of Back, Skip and Next
    } finally {
      delete (Element.prototype as { scrollIntoView?: unknown }).scrollIntoView;
    }
  });

  it("another AI provider whose check fails says why, and takes the link out again", async () => {
    const link = { id: "standard:g2", kind: "model", name: "Gemini - sample", provider: "google", on_device: false, key_set: true, error: null };
    const refused = { en: "Gemini - sample refused the key.", ar: "Gemini - sample رفض المفتاح." };
    const fetch = mockCore({
      "GET /settings/ai-consent": () => Response.json({ at: "2026-11-05T08:00:00+00:00", text_version: 1 }),
      "POST /settings/ai/standard": () => Response.json(link, { status: 201 }),
      "POST /settings/ai/check": () => Response.json({ error: refused, fix: "ai" }, { status: 409 }),
      "DELETE /settings/ai/standard/standard%3Ag2": () => Response.json({ undo: "u1", window_ms: 10000 }),
    });
    const user = userEvent.setup();
    flowAt("ai");
    await user.click(await screen.findByRole("button", { name: choice(texts.aiLinkStandard.en) }));
    await user.type(screen.getByLabelText(texts.providerName.en), "Gemini - sample");
    await user.type(screen.getByLabelText(texts.baseUrl.en), "https://generativelanguage.googleapis.com/v1beta/openai");
    await user.click(screen.getByLabelText(texts.providerKey.en));
    await user.paste("sample-google-key-not-real");
    expect(await screen.findByText(refused.en, {}, { timeout: 2000 })).toBeInTheDocument();
    expect(calls(fetch, "DELETE /settings/ai/standard/standard%3Ag2")).toHaveLength(1);
    expect(screen.getByRole("button", { name: texts.setupNext.en })).toBeDisabled();
  });

  it("a key the check refuses says why, and stays in the field to be fixed", async () => {
    const refused = { en: "The key was refused (sample).", ar: "المفتاح اترفض (عينة)." };
    mockCore({
      "GET /settings/ai-consent": () => Response.json({ at: "2026-11-05T08:00:00+00:00", text_version: 1 }),
      "PUT /settings/ai-key": () => Response.json({ set: true }),
      "POST /settings/ai/check": () => Response.json({ error: refused }, { status: 409 }),
    });
    const user = userEvent.setup();
    flowAt("ai");
    await user.click(await screen.findByRole("button", { name: choice(texts.aiLinkApiKey.en) }));
    await user.click(screen.getByLabelText(texts.aiKeyLabel.en));
    await user.paste(KEY);
    expect(await screen.findByRole("alert")).toHaveTextContent(refused.en);
    expect(screen.getByLabelText(texts.aiKeyLabel.en)).toHaveValue(KEY);
    expect(screen.getByRole("button", { name: texts.setupNext.en })).toBeDisabled();
  });

  // The core's own words for each failure of the check (core/qsone/copy.py), with the fix it sends. In the first launch
  // there is no top bar and the key field is where the key is fixed: a line here never sends the engineer elsewhere.
  const PLACE = /at the top|top bar|\babove\b|in settings|\bpress\b|open ai settings|فوق|الإعدادات|دوس|افتح/i;
  const failures = [
    {
      name: "a refused key",
      fix: "ai",
      error: {
        en: "Anthropic refused this Claude key. Check that you copied all of it, or make a new key at console.anthropic.com.",
        ar: "Anthropic رفض مفتاح Claude ده. اتأكد إنك نسخته كله، أو اعمل مفتاح جديد من console.anthropic.com.",
      },
      retry: false,
    },
    {
      name: "no internet",
      fix: "retry",
      error: {
        en: "Could not reach Claude. Check the internet connection, then try again.",
        ar: "مقدرناش نوصل لـ Claude. اتأكد إن النت شغال وجرّب تاني.",
      },
      retry: true,
    },
    {
      name: "a busy provider",
      fix: "retry",
      error: { en: "Claude is busy right now. Try again in a minute.", ar: "في ضغط على Claude دلوقتي. جرّب تاني كمان دقيقة." },
      retry: true,
    },
    {
      name: "a check the provider did not answer",
      fix: "retry",
      error: { en: "Claude did not answer the check. Try again in a few minutes.", ar: "Claude مارَدّش على الفحص. جرّب تاني كمان كام دقيقة." },
      retry: true,
    },
  ];
  for (const failure of failures) {
    it(`the key's check fails (${failure.name}): what to do, in place, and Try again only where it helps`, async () => {
      const fetch = mockCore({
        "GET /settings/ai-consent": () => Response.json({ at: "2026-11-05T08:00:00+00:00", text_version: 1 }),
        "PUT /settings/ai-key": () => Response.json({ set: true }),
        "POST /settings/ai/check": () => Response.json({ error: failure.error, fix: failure.fix }, { status: 409 }),
      });
      const user = userEvent.setup();
      for (const lang of ["en", "ar"] as const) {
        setLanguage(lang);
        const { unmount } = render(<FirstLaunch initial={{ ...fresh(), steps: { ...fresh().steps, language: "done", account: "skipped" } }} onDone={vi.fn()} />);
        await user.click(await screen.findByRole("button", { name: choice(texts.aiLinkApiKey[lang]) }));
        await user.click(screen.getByLabelText(texts.aiKeyLabel[lang]));
        await user.paste(KEY);
        const alert = await screen.findByRole("alert");
        expect(alert).toHaveTextContent(failure.error[lang]);
        const line = alert.closest("[data-key-line]") as HTMLElement;
        expect(line.textContent).not.toMatch(PLACE);
        expect(within(line).queryByRole("button", { name: texts.openAiSettings[lang] })).toBeNull();
        const again = within(line).queryByRole("button", { name: texts.tryAgain[lang] });
        expect(again !== null).toBe(failure.retry);
        if (again) {
          const before = calls(fetch, "POST /settings/ai/check").length;
          await user.click(again); // the same key, checked once more
          await waitFor(() => expect(calls(fetch, "POST /settings/ai/check")).toHaveLength(before + 1));
          expect(screen.getByLabelText(texts.aiKeyLabel[lang])).toHaveValue(KEY);
        }
        unmount();
      }
    });
  }

  it("Claude Code that fails its check says what to do, and Try again checks it once more", async () => {
    const signedOut = {
      en: "Claude Code is signed out. Sign in to it once in a terminal, then try again.",
      ar: "Claude Code مش مسجّل دخول. سجّل دخولك فيه مرة من الـ terminal، وبعدين جرّب تاني.",
    };
    const fetch = mockCore({
      "GET /settings/ai-consent": () => Response.json({ at: "2026-11-05T08:00:00+00:00", text_version: 1 }),
      "GET /settings/claude-code": () => Response.json({ found: true, version: "2.3.1" }),
      "POST /settings/ai/check": () => Response.json({ error: signedOut, fix: "retry" }, { status: 409 }),
    });
    const user = userEvent.setup();
    flowAt("ai");
    await user.click(await screen.findByRole("button", { name: choice(texts.aiLinkClaudeCode.en) }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(signedOut.en);
    expect(alert.textContent).not.toMatch(PLACE);
    await user.click(screen.getByRole("button", { name: texts.tryAgain.en }));
    await waitFor(() => expect(calls(fetch, "POST /settings/ai/check")).toHaveLength(2));
  });

  it("Claude Code not found: what to do names no button the step lacks", async () => {
    mockCore({
      "GET /settings/ai-consent": () => Response.json({ at: "2026-11-05T08:00:00+00:00", text_version: 1 }),
      "GET /settings/claude-code": () => Response.json({ found: false, version: null }),
    });
    const user = userEvent.setup();
    flowAt("ai");
    await user.click(await screen.findByRole("button", { name: choice(texts.aiLinkClaudeCode.en) }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(texts.aiLinkClaudeCodeMissing.en);
    expect(alert.textContent).not.toMatch(PLACE);
    expect(screen.getByRole("button", { name: texts.tryAgain.en })).toBeInTheDocument(); // "then try again": here
  });

  it("Claude Code is checked as soon as it is chosen; not found says how to get it, and coming back checks again", async () => {
    let found = false;
    const refused = { en: "Claude Code is signed out (sample).", ar: "Claude Code مش داخل (عينة)." };
    const fetch = mockCore({
      "GET /settings/ai-consent": () => Response.json({ at: "2026-11-05T08:00:00+00:00", text_version: 1 }),
      "GET /settings/claude-code": () => Response.json(found ? { found: true, version: "2.3.1" } : { found: false, version: null }),
      "POST /settings/ai/check": () => Response.json({ error: refused }, { status: 409 }),
    });
    const user = userEvent.setup();
    flowAt("ai");
    await user.click(await screen.findByRole("button", { name: choice(texts.aiLinkClaudeCode.en) }));
    expect(await screen.findByRole("alert")).toHaveTextContent(texts.aiLinkClaudeCodeMissing.en); // and what to do
    expect(calls(fetch, "POST /settings/ai/check")).toHaveLength(0); // nothing to check yet

    found = true; // the engineer installed it, and comes back to ONE's window
    window.dispatchEvent(new Event("focus"));
    expect(await screen.findByText("Found: Claude Code 2.3.1")).toBeInTheDocument();
    expect(calls(fetch, "POST /settings/ai/check")[0]).toEqual({ via: "claude_code" });
    expect(await screen.findByRole("alert")).toHaveTextContent(refused.en); // the core's plain reason
    expect(screen.getByRole("button", { name: texts.setupNext.en })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: choice(texts.aiLinkClaudeCode.en) })); // chosen again: again
    await waitFor(() => expect(calls(fetch, "POST /settings/ai/check")).toHaveLength(2));
  });

  it("an answer for a choice the engineer left is not shown", async () => {
    let answer!: (response: Response) => void;
    mockCore({
      "GET /settings/ai-consent": () => Response.json({ at: "2026-11-05T08:00:00+00:00", text_version: 1 }),
      "GET /settings/claude-code": () => Response.json({ found: true, version: "2.3.1" }),
      "POST /settings/ai/check": () => new Promise<Response>((resolve) => (answer = resolve)),
    });
    const user = userEvent.setup();
    flowAt("ai");
    await user.click(await screen.findByRole("button", { name: choice(texts.aiLinkClaudeCode.en) }));
    await waitFor(() => expect(answer).toBeDefined());
    await user.click(screen.getByRole("button", { name: choice(texts.aiLinkApiKey.en) }));
    await act(async () => answer(Response.json({ ok: true })));
    expect(screen.queryByText(texts.aiLinkWorks.en)).toBeNull();
    expect(screen.getByRole("button", { name: texts.setupNext.en })).toBeDisabled();
  });

  it("the AI step has no Save or Check button, in either language, for any choice", async () => {
    mockCore({ "GET /settings/ai-consent": () => Response.json({ at: "2026-11-05T08:00:00+00:00", text_version: 1 }) });
    const user = userEvent.setup();
    for (const lang of ["en", "ar"] as const) {
      setLanguage(lang);
      const { unmount } = render(<FirstLaunch initial={{ ...fresh(), steps: { ...fresh().steps, language: "done", account: "skipped" } }} onDone={vi.fn()} />);
      for (const via of [texts.aiLinkClaudeCode, texts.aiLinkApiKey, texts.aiLinkStandard]) {
        await user.click(await screen.findByRole("button", { name: choice(via[lang]) }));
        expect(noSaveOrCheck()).toEqual([]);
      }
      unmount();
    }
  });

  it("the AI step's two choices show the Claude logo, 20 px", async () => {
    mockCore({ "GET /settings/ai-consent": () => Response.json({ at: "2026-11-05T08:00:00+00:00", text_version: 1 }) });
    flowAt("ai");
    for (const via of [texts.aiLinkClaudeCode, texts.aiLinkApiKey]) {
      const logo = (await screen.findByRole("button", { name: choice(via.en) })).querySelector("svg[data-logo]");
      expect(logo).toHaveAttribute("data-logo", "claude");
      expect(logo).toHaveAttribute("width", "20");
    }
  });

  it("introduction card: the country starts at the system's, with no blank choice", async () => {
    mockCore();
    systemLanguageIs("ar-AE");
    flowAt("card");
    const country = await screen.findByLabelText(texts.cardCountry.en);
    expect(country).toHaveValue("AE");
    expect([...(country as HTMLSelectElement).options].map((o) => o.value)).toEqual(["EG", "SA", "AE", "other"]);
    expect(document.querySelector("input[maxlength='3']")).toBeNull(); // no currency field: the country says it
  });

  it("introduction card: Egypt when the system names none of the three", async () => {
    mockCore();
    systemLanguageIs("en-US");
    flowAt("card");
    expect(await screen.findByLabelText(texts.cardCountry.en)).toHaveValue("EG");
  });

  it("introduction card: Saudi Arabia sends SAR; a city in Arabic stays as typed", async () => {
    const fetch = mockCore({ "PUT /engineer/card": (body) => Response.json(body) });
    const user = userEvent.setup();
    flowAt("card");
    const next = await screen.findByRole("button", { name: texts.setupNext.en });
    expect(next).toBeDisabled();
    await user.click(screen.getByRole("radio", { name: texts.cardRoleConsultant.en }));
    await user.selectOptions(screen.getByLabelText(texts.cardCountry.en), texts.cardCountrySA.en);
    await user.type(screen.getByLabelText(texts.cardCity.en), "الرياض");
    await user.click(next);
    expect(calls(fetch, "PUT /engineer/card")[0]).toEqual({ role: "consultant", country: "SA", city: "الرياض", currency: "SAR" });
    await waitFor(() => expect(calls(fetch, "PUT /setup/card")[0]).toEqual({ state: "done" }));
  });

  it("introduction card: Other sends no currency, and asks for none", async () => {
    const fetch = mockCore({ "PUT /engineer/card": (body) => Response.json(body) });
    const user = userEvent.setup();
    flowAt("card");
    await user.click(await screen.findByRole("radio", { name: texts.cardRoleProcurement.en }));
    await user.selectOptions(screen.getByLabelText(texts.cardCountry.en), texts.cardCountryOther.en);
    expect(document.querySelector("input[maxlength='3']")).toBeNull();
    await user.type(screen.getByLabelText(texts.cardCity.en), "Doha");
    await user.click(screen.getByRole("button", { name: texts.setupNext.en }));
    expect(calls(fetch, "PUT /engineer/card")[0]).toEqual({ role: "procurement", country: "other", city: "Doha" });
    await waitFor(() => expect(calls(fetch, "PUT /setup/card")[0]).toEqual({ state: "done" }));
  });

  it("introduction card: while it saves, Next shows it and nothing appears above the buttons", async () => {
    let answer!: (response: Response) => void;
    mockCore({ "PUT /engineer/card": () => new Promise<Response>((resolve) => (answer = resolve)) });
    const user = userEvent.setup();
    flowAt("card");
    await user.click(await screen.findByRole("radio", { name: texts.cardRoleContractor.en }));
    await user.click(screen.getByRole("button", { name: texts.setupNext.en }));
    const next = await screen.findByRole("button", { name: new RegExp(texts.cardSaving.en.replace("…", "")) });
    expect(next).toHaveAttribute("aria-busy", "true");
    expect(next).toBeEnabled(); // not dimmed
    expect(screen.queryByRole("status")).toBeNull(); // no new line that would push the row down
    answer(Response.json({}));
    await waitFor(() => expect(screen.queryByRole("heading", { name: texts.cardTitle.en })).toBeNull());
  });

  it.each([
    ["the core's own words", () => Response.json({ error: { en: "The project file cannot be read - sample.", ar: "ملف المشروع مش مقروء - عينة." } }, { status: 409 }), "The project file cannot be read - sample."],
    ["a plain retry", () => new Response("Internal Server Error", { status: 500 }), texts.cardNotSavedRetry.en],
  ])("introduction card: a failure shows %s", async (_, answer, shown) => {
    const fetch = mockCore({ "PUT /engineer/card": answer });
    const user = userEvent.setup();
    flowAt("card");
    await user.click(await screen.findByRole("radio", { name: texts.cardRoleContractor.en }));
    await user.selectOptions(screen.getByLabelText(texts.cardCountry.en), texts.cardCountryEG.en);
    await user.click(screen.getByRole("button", { name: texts.setupNext.en }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(shown);
    expect(calls(fetch, "PUT /setup/card")).toHaveLength(0);
  });

  it("Usage Stats: Share and Don't share are equal buttons; Skip means don't share", async () => {
    const fetch = mockCore({ "PUT /settings/usage-stats": (body) => Response.json(body) });
    const user = userEvent.setup();
    flowAt("usage");
    const share = await screen.findByRole("button", { name: texts.usageShare.en });
    const dont = screen.getByRole("button", { name: texts.usageDontShare.en });
    expect(share.className).toBe(dont.className);
    expect(screen.getByText(texts.usageSkipMeans.en)).toBeInTheDocument();
    expect(screen.getByText(texts.usageNever.en)).toBeInTheDocument();
    await user.click(dont);
    expect(calls(fetch, "PUT /settings/usage-stats")[0]).toEqual({ on: false });
    expect(calls(fetch, "PUT /setup/usage")[0]).toEqual({ state: "done" });
  });

  it("Back goes to the step before, and a step the core did not save stays", async () => {
    mockCore({ "PUT /setup/card": () => new Response(null, { status: 503 }) });
    const user = userEvent.setup();
    flowAt("card");
    await user.click(await screen.findByRole("button", { name: texts.setupSkip.en }));
    expect(await screen.findByRole("alert")).toHaveTextContent(texts.setupNotSaved.en);
    expect(screen.getByRole("heading", { level: 1, name: texts.cardTitle.en })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: texts.setupBack.en }));
    expect(screen.getByRole("heading", { level: 1, name: texts.connectAi.en })).toBeInTheDocument();
  });

  it("every step reads the same in English and Arabic", async () => {
    mockCore();
    const keys: Record<Step | "ready", (keyof typeof texts)[]> = {
      language: ["languageTitle", "languageHelp", "setupNext", "setupSkip"],
      account: ["accountTitle", "accountWhy", "accountSignIn", "accountUseDevice", "setupBack"],
      ai: ["connectAi", "consentTitle", "consentBody", "consentTerms", "consentPrivacy", "consentAgree", "aiLinkTitle", "aiLinkClaudeCode", "aiLinkApiKey", "aiLinkStandard"],
      card: ["cardTitle", "cardHelp", "cardRole", "cardRoleProcurement", "cardCountry", "cardCountryOther", "cardCity"],
      usage: ["usageTitle", "usageHelp", "usageSentTitle", "usageSent", "usageNeverTitle", "usageNever", "usageShare", "usageDontShare"],
      ready: ["readyTitle", "readyStart"],
    };
    for (const lang of ["en", "ar"] as const) {
      for (const [step, wanted] of Object.entries(keys)) {
        const setup = fresh();
        for (const s of STEPS) if (step === "ready" || STEPS.indexOf(s) < STEPS.indexOf(step as Step)) setup.steps[s] = "done";
        setLanguage(lang);
        systemLanguageIs(`${lang}-EG`);
        const { unmount } = render(<FirstLaunch initial={setup} onDone={() => undefined} />);
        await screen.findByRole("heading", { level: 1 });
        await waitFor(() => expect(screen.getAllByText(texts[wanted.at(-1)!][lang]).length).toBeGreaterThan(0));
        const page = document.body.textContent ?? "";
        for (const key of wanted) expect(page, `${step} ${lang}: ${key}`).toContain(texts[key][lang]);
        if (lang === "ar") expect(page).not.toMatch(/\b(Skip|Back|Next|Share)\b/);
        unmount();
      }
    }
  });

  it("the chat's Connect AI opens the AI step alone, and closes it once passed", async () => {
    const fetch = mockCore({ "GET /setup": () => Response.json({ ...fresh(), done: true }) });
    const user = userEvent.setup();
    render(
      <SetupGate>
        <ConsentNeeded />
      </SetupGate>,
    );
    expect(await screen.findByText(texts.consentNeeded.en)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: texts.connectAi.en }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByRole("heading", { level: 1, name: texts.connectAi.en })).toBeInTheDocument();
    expect(within(dialog).queryByRole("button", { name: texts.setupBack.en })).toBeNull();
    await user.click(within(dialog).getByRole("button", { name: texts.setupSkip.en }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(calls(fetch, "PUT /setup/ai")[0]).toEqual({ state: "skipped" });
  });

  it("no consent banner once the consent is given", async () => {
    mockCore({ "GET /settings/ai-consent": () => Response.json({ at: "2026-11-05T08:00:00+00:00", text_version: 1 }) });
    render(<ConsentNeeded />);
    await waitFor(() => expect(fetch).toHaveBeenCalled());
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(screen.queryByText(texts.consentNeeded.en)).toBeNull();
  });
});

describe("crash reports", () => {
  const error = () => {
    const e = new TypeError("خرسانة /home/user/مشروع https://example.com/x?token=1");
    e.stack = [
      "TypeError: خرسانة /home/user/مشروع https://example.com/x?token=1",
      "    at render (http://127.0.0.1:1442/node_modules/.vite/deps/react-dom.js?v=1:100:5)",
      "    at Chat (http://127.0.0.1:1442/src/chat/Chat.tsx?t=1730000000:120:15)",
      "    at App (http://127.0.0.1:1442/src/shell/App.tsx:300:3)",
    ].join("\n");
    return e;
  };

  it("a screen crash is reported as class and our file:line only", async () => {
    expect(crashReport(error())).toEqual({ kind: "TypeError", where: "Chat.tsx:120" });
    const webkit = new RangeError("x");
    webkit.stack = "Chat@tauri://localhost/assets/index-a1B2.js:1:2345\nglobal code@tauri://localhost/assets/index-a1B2.js:9:1";
    expect(crashReport(webkit)).toEqual({ kind: "RangeError", where: "index-a1B2.js:1" });
    const library = new Error("x");
    library.stack = "Error: x\n    at f (http://127.0.0.1:1442/node_modules/.vite/deps/ai.js:1:1)";
    expect(crashReport(library)).toBeUndefined(); // not in our code: nothing to say

    const fetch = mockCore({
      "GET /about": () => Response.json({ version: "0.1.0", release: false }),
      "POST /usage/crash": () => new Response(null, { status: 204 }),
    });
    await reportCrash(error());
    await reportCrash(error()); // once per session
    const sent = calls(fetch, "POST /usage/crash");
    expect(sent).toEqual([{ from: "screen", kind: "TypeError", where: "Chat.tsx:120", version: "0.1.0" }]);
    const all = JSON.stringify(fetch.mock.calls);
    expect(all).not.toContain("خرسانة");
    expect(all).not.toContain("/home/");
    expect(all).not.toContain("example.com");
  });

  it("a crash report never throws, whatever the core answers", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("offline")));
    await expect(reportCrash(error())).resolves.toBeUndefined();
  });
});

it("Ready keeps the import help in a compact, non-clipping content flow at laptop height", async () => {
  mockCore();
  const setup = fresh();
  for (const step of STEPS) setup.steps[step] = "done";
  render(<FirstLaunch initial={setup} onDone={vi.fn()} onImport={vi.fn()} />);
  await screen.findByRole("heading", { name: texts.readyTitle.en });
  const help = screen.getByText(texts.readyImportOldHelp.en);
  const content = help.closest("[data-step-content]");
  expect(content).not.toBeNull();
  expect(content).toHaveClass("shrink-0");
  expect(document.querySelector("[data-step]")).toHaveClass("gap-4");
  expect(screen.getByText(texts.readyDrop.en).parentElement).toHaveClass("py-6");
});
