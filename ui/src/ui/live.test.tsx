import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setLanguage, texts } from "../i18n";
import { AiKey } from "../settings/AiKey";
import { AiSettings, useAiSettings } from "../settings/AiSettings";
import { Connectors } from "../settings/Connectors";
import { SearchKey } from "../settings/SearchKey";
import { looksLikeKey, PAUSE } from "./live";

// Sample keys, long enough to be whole: none is a real key.
const KEY = "sk-ant-sample-not-a-real-key-0000000000000000";
const OTHER = "sk-ant-sample-not-a-real-key-1111111111111111";

type Route = (init: RequestInit) => Response | Promise<Response>;

function core(routes: Record<string, Route>) {
  const fetch = vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const route = routes[`${init.method ?? "GET"} ${String(input)}`];
    return route ? route(init) : new Response("not found", { status: 404 });
  });
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

const bodies = (fetch: ReturnType<typeof core>, key: string) =>
  fetch.mock.calls
    .filter(([url, init]) => `${init?.method ?? "GET"} ${String(url)}` === key)
    .map(([, init]) => JSON.parse(String(init!.body)) as unknown);

/** The key's line: what shows under the field. */
const line = () => document.querySelector("[data-key-line]")!;

beforeEach(() => setLanguage("en"));
afterEach(() => vi.useRealTimers());

describe("a key field that checks itself", () => {
  it("a whole key is one with no space, long enough", () => {
    expect(looksLikeKey(KEY, 40)).toBe(true);
    expect(looksLikeKey(`  ${KEY}  `, 40)).toBe(true);
    expect(looksLikeKey("sk-ant-api03-abc", 40)).toBe(false);
    expect(looksLikeKey(`${KEY.slice(0, 20)} ${KEY.slice(20)}`, 40)).toBe(false);
  });

  it("a pasted key is saved and checked at once", async () => {
    const fetch = core({
      "PUT /api/settings/ai-key": () => Response.json({ set: true }),
      "POST /api/settings/ai/check": () => Response.json({ ok: true }),
    });
    const user = userEvent.setup();
    render(<AiKey />);
    await user.click(screen.getByLabelText(texts.aiKeyLabel.en));
    await user.paste(KEY);
    await waitFor(() => expect(bodies(fetch, "PUT /api/settings/ai-key")).toEqual([{ provider: "anthropic", value: KEY }]), {
      timeout: PAUSE / 2,
    });
    expect(await within(line() as HTMLElement).findByText(texts.aiLinkWorks.en)).toBeInTheDocument();
    expect(bodies(fetch, "POST /api/settings/ai/check")).toEqual([{ via: "api_key" }]);
    expect(screen.getByLabelText(texts.aiKeyLabel.en)).toHaveValue(""); // the page holds no saved key
    expect(screen.queryByRole("button")).toBeNull(); // no Save, no Check
  });

  it("a typed key is checked once, after a pause in typing, and never while it is partial", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const fetch = core({
      "PUT /api/settings/ai-key": () => Response.json({ set: true }),
      "POST /api/settings/ai/check": () => Response.json({ ok: true }),
    });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<AiKey />);
    const field = screen.getByLabelText(texts.aiKeyLabel.en);
    await user.type(field, KEY.slice(0, 20));
    await act(async () => vi.advanceTimersByTime(PAUSE * 2));
    expect(fetch).not.toHaveBeenCalled(); // too short to be a key: nothing leaves the page
    expect(line()).toHaveTextContent(texts.keyTooShort.en);

    await user.type(field, KEY.slice(20));
    await act(async () => vi.advanceTimersByTime(PAUSE - 100));
    expect(fetch).not.toHaveBeenCalled(); // still within the pause
    await act(async () => vi.advanceTimersByTime(200));
    await waitFor(() => expect(bodies(fetch, "PUT /api/settings/ai-key")).toEqual([{ provider: "anthropic", value: KEY }]));
    expect(await within(line() as HTMLElement).findByText(texts.aiLinkWorks.en)).toBeInTheDocument();
    expect(bodies(fetch, "POST /api/settings/ai/check")).toHaveLength(1);
  });

  it("a newer key stops the older check: only the latest answer shows", async () => {
    const answers: ((response: Response) => void)[] = [];
    const signals: AbortSignal[] = [];
    const fetch = core({
      "PUT /api/settings/ai-key": () => Response.json({ set: true }),
      "POST /api/settings/ai/check": (init) => {
        signals.push(init.signal!);
        return new Promise<Response>((resolve) => answers.push(resolve));
      },
    });
    const user = userEvent.setup();
    render(<AiKey />);
    const field = screen.getByLabelText(texts.aiKeyLabel.en);
    await user.click(field);
    await user.paste(KEY);
    await waitFor(() => expect(answers).toHaveLength(1));
    await user.clear(field);
    await user.paste(OTHER);
    await waitFor(() => expect(answers).toHaveLength(2));
    expect(signals[0]!.aborted).toBe(true); // the older check was stopped
    expect(signals[1]!.aborted).toBe(false);

    const refused = { en: "The key was refused (sample).", ar: "المفتاح اترفض (عينة)." };
    await act(async () => answers[1]!(Response.json({ error: refused }, { status: 409 })));
    await act(async () => answers[0]!(Response.json({ ok: true }))); // late, and for a key no longer there
    expect(await screen.findByRole("alert")).toHaveTextContent(refused.en);
    expect(screen.queryByText(texts.aiLinkWorks.en)).toBeNull();
    expect(bodies(fetch, "PUT /api/settings/ai-key").map((body) => (body as { value: string }).value)).toEqual([KEY, OTHER]);
  });

  it("a key that fails stays in the field, marked, to be fixed", async () => {
    const refused = { en: "The key was refused (sample).", ar: "المفتاح اترفض (عينة)." };
    core({
      "PUT /api/settings/ai-key": () => Response.json({ set: true }),
      "POST /api/settings/ai/check": () => Response.json({ error: refused }, { status: 409 }),
    });
    const user = userEvent.setup();
    render(<AiKey />);
    const field = screen.getByLabelText(texts.aiKeyLabel.en);
    await user.click(field);
    await user.paste(KEY);
    expect(await screen.findByRole("alert")).toHaveTextContent(refused.en);
    expect(field).toHaveValue(KEY);
    expect(field).toHaveAttribute("aria-invalid", "true");
    expect(field).toHaveAttribute("type", "password");
  });

  it("a key the key store did not take says so, and stays", async () => {
    const down = { en: "The key store is not answering (sample).", ar: "مخزن المفاتيح مش بيرد (عينة)." };
    const fetch = core({ "PUT /api/settings/ai-key": () => Response.json({ error: down }, { status: 503 }) });
    const user = userEvent.setup();
    render(<AiKey />);
    await user.click(screen.getByLabelText(texts.aiKeyLabel.en));
    await user.paste(KEY);
    expect(await screen.findByRole("alert")).toHaveTextContent(down.en);
    expect(screen.getByLabelText(texts.aiKeyLabel.en)).toHaveValue(KEY);
    expect(bodies(fetch, "POST /api/settings/ai/check")).toHaveLength(0); // nothing to check
  });
});

// The settings, with every part showing: a key set, a Standard Link, Claude Code on, a model with no price, the caps.
const opus = { connector: "anthropic", model: "claude-opus-5-5" };
const card = (connector: string, model: string, price: [string, string] | null) => ({
  connector,
  model,
  name: model,
  provider: connector,
  images: true,
  tools: true,
  context: 200000,
  price_in: price?.[0] ?? null,
  price_out: price?.[1] ?? null,
  price_source: price ? "sample source" : null,
  on_device: false,
  subscription: false,
});
const settings = {
  connectors: [
    { id: "anthropic", kind: "model", name: "Claude", provider: "anthropic", on_device: false, key_set: true, error: null },
    { id: "standard:s1", kind: "model", name: "Sample", provider: "sample", on_device: false, key_set: true, error: null },
    { id: "claude-code", kind: "agent", name: "Claude Code", provider: "anthropic", on_device: true, key_set: false, error: null },
  ],
  sheet: [card("anthropic", "claude-opus-5-5", ["5.00", "25.00"]), card("standard:s1", "sample-model", null)],
  roles: { lead: opus, checker: opus, specialist: opus, quick: opus },
  defaults: { lead: opus, checker: opus, specialist: opus, quick: opus },
};
const caps = { brief: "2.00", day: "15.00", month: "150.00", budget_above: "0.50", subscription_stops: false };
const status = { installed: true, compatible: true, signed_in: true, version: "2.1.318", code: null, models: [] };

function Settings() {
  const ai = useAiSettings();
  return (
    <>
      <AiSettings ai={ai} />
      <SearchKey />
      <Connectors />
    </>
  );
}

describe("settings", () => {
  it("have no Save or Check button, in either language", async () => {
    core({
      "GET /api/settings/ai": () => Response.json(settings),
      "GET /api/settings/ai/caps": () => Response.json({ caps, recommended: caps }),
      "GET /api/settings/ai/claude-code": () => Response.json(status),
      "GET /api/settings/search": () => Response.json({ provider: "brave", own_key: true }),
      "GET /api/connectors": () => Response.json({ connectors: [] }),
    });
    for (const lang of ["en", "ar"] as const) {
      setLanguage(lang);
      const { unmount } = render(<Settings />);
      // the AI settings open on one box; the rest is under Advanced settings
      await userEvent.click(await screen.findByText(texts.advancedAi[lang]));
      await screen.findByLabelText(texts.priceIn[lang]); // every part is there
      await screen.findByLabelText(texts.capDay[lang]);
      await screen.findAllByText(texts.searchProvider[lang]);
      const names = screen.queryAllByRole("button").map((button) => button.textContent ?? "");
      expect(names.length).toBeGreaterThan(0);
      expect(names.filter((name) => /\b(save|check)\b|حفظ|احفظ|افحص|اتأكد/i.test(name))).toEqual([]);
      unmount();
    }
  });
});
