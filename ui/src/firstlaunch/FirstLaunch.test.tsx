import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { crashReport, reportCrash, resetCrashReports } from "../app/crash";
import { language, setLanguage, texts } from "../i18n";
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

  it("an API key is saved, then checked through the core", async () => {
    const fetch = mockCore({
      "GET /settings/ai-consent": () => Response.json({ at: "2026-11-05T08:00:00+00:00", text_version: 1 }),
      "PUT /settings/ai-key": () => Response.json({ set: true }),
      "POST /settings/ai/check": () => Response.json({ ok: true }),
    });
    const user = userEvent.setup();
    flowAt("ai");
    await user.click(await screen.findByRole("button", { name: choice(texts.aiLinkApiKey.en) }));
    await user.type(screen.getByLabelText(texts.aiKeyLabel.en), "sk-ant-sample-not-a-key");
    await user.click(screen.getByRole("button", { name: texts.save.en }));
    const works = await screen.findByText(texts.aiLinkWorks.en);
    expect(works.closest("[data-feedback]")).toHaveAttribute("data-feedback", "done"); // the same mark on every step
    expect(works.closest("[role=status]")).not.toBeNull();
    expect(calls(fetch, "POST /settings/ai/check")[0]).toEqual({ via: "api_key" });
    await user.click(screen.getByRole("button", { name: texts.setupNext.en }));
    expect(calls(fetch, "PUT /setup/ai")[0]).toEqual({ state: "done" });
  });

  it("a key the check refuses says why, and the key field comes back for another", async () => {
    const refused = { en: "The key was refused (sample).", ar: "المفتاح اترفض (عينة)." };
    mockCore({
      "GET /settings/ai-consent": () => Response.json({ at: "2026-11-05T08:00:00+00:00", text_version: 1 }),
      "PUT /settings/ai-key": () => Response.json({ set: true }),
      "POST /settings/ai/check": () => Response.json({ error: refused }, { status: 409 }),
    });
    const user = userEvent.setup();
    flowAt("ai");
    await user.click(await screen.findByRole("button", { name: choice(texts.aiLinkApiKey.en) }));
    await user.type(screen.getByLabelText(texts.aiKeyLabel.en), "sk-ant-sample-not-a-key");
    await user.click(screen.getByRole("button", { name: texts.save.en }));
    expect(await screen.findByRole("alert")).toHaveTextContent(refused.en);
    expect(screen.getByLabelText(texts.aiKeyLabel.en)).toHaveValue("");
    expect(screen.queryByRole("button", { name: texts.setupNext.en })).toBeNull();
  });

  it("Claude Code: found shows its version and Check; not found says how to get it", async () => {
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
    expect(await screen.findByText(texts.aiLinkClaudeCodeMissing.en)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: texts.aiLinkCheck.en }));
    expect(calls(fetch, "POST /settings/ai/check")).toHaveLength(0); // nothing to check yet
    expect(await screen.findByRole("alert")).toHaveTextContent(texts.aiLinkClaudeCodeMissing.en); // and what to do

    found = true; // the engineer installed it
    await user.click(screen.getByRole("button", { name: texts.aiLinkCheck.en }));
    expect(await screen.findByText("Found: Claude Code 2.3.1")).toBeInTheDocument();
    expect(calls(fetch, "POST /settings/ai/check")[0]).toEqual({ via: "claude_code" });
    expect(await screen.findByRole("alert")).toHaveTextContent(refused.en); // the core's plain reason
    expect(screen.queryByRole("button", { name: texts.setupNext.en })).toBeNull();
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

  it("introduction card: a currency the core refuses says so and stays", async () => {
    const refused = { detail: [{ loc: ["body", "currency"], msg: "String should match pattern", type: "string_pattern_mismatch" }] };
    const fetch = mockCore({ "PUT /engineer/card": () => Response.json(refused, { status: 422 }) });
    const user = userEvent.setup();
    flowAt("card");
    await user.click(await screen.findByRole("radio", { name: texts.cardRoleContractor.en }));
    await user.click(screen.getByRole("button", { name: texts.setupNext.en }));
    expect(await screen.findByRole("alert")).toHaveTextContent(texts.cardNotSaved.en);
    expect(calls(fetch, "PUT /setup/card")).toHaveLength(0);
  });

  it.each([
    ["the core's own words", () => Response.json({ error: { en: "The project file cannot be read - sample.", ar: "ملف المشروع مش مقروء - عينة." } }, { status: 409 }), "The project file cannot be read - sample."],
    ["a plain retry, not the currency", () => new Response("Internal Server Error", { status: 500 }), texts.cardNotSavedRetry.en],
  ])("introduction card: any other failure shows %s", async (_, answer, shown) => {
    const fetch = mockCore({ "PUT /engineer/card": answer });
    const user = userEvent.setup();
    flowAt("card");
    await user.click(await screen.findByRole("radio", { name: texts.cardRoleContractor.en }));
    await user.selectOptions(screen.getByLabelText(texts.cardCountry.en), texts.cardCountryEG.en);
    await user.click(screen.getByRole("button", { name: texts.setupNext.en }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(shown);
    expect(alert).not.toHaveTextContent(texts.cardNotSaved.en);
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
      ai: ["connectAi", "consentTitle", "consentBody", "consentTerms", "consentPrivacy", "consentAgree", "aiLinkTitle", "aiLinkClaudeCode", "aiLinkApiKey"],
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
