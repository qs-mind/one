import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { setLanguage, texts } from "../i18n";
import { AiSettings, useAiSettings } from "./AiSettings";

type Route = (init: RequestInit) => Response | Promise<Response>;

// Model Data Sheet cards, as GET /settings/ai sends them. Prices and sources are sample data, not real prices.
function card(connector: string, model: string, name: string, price: [string, string] | null, more = {}) {
  return {
    connector,
    model,
    name,
    provider: connector === "anthropic" ? "anthropic" : "sample-provider",
    images: true,
    tools: true,
    context: 200000,
    price_in: price?.[0] ?? null,
    price_out: price?.[1] ?? null,
    price_source: price ? "genai-prices sample: https://example.com/prices" : null,
    on_device: false,
    subscription: false,
    ...more,
  };
}

const opus = { connector: "anthropic", model: "claude-opus-5-5" };
const haiku = { connector: "anthropic", model: "claude-haiku-5-5" };
const roles = { lead: opus, checker: haiku, specialist: haiku, quick: haiku };

function settings(more: { connectors?: object[] } = {}) {
  return {
    connectors: [
      { id: "anthropic", kind: "model", name: "Claude", provider: "anthropic", on_device: false, key_set: true, error: null },
      {
        id: "standard:s1",
        kind: "model",
        name: "Sample provider",
        provider: "sample-provider",
        on_device: false,
        key_set: true,
        error: { en: "Could not reach Sample provider.", ar: "مقدرناش نوصل لـ Sample provider." },
      },
      ...(more.connectors ?? []),
    ],
    sheet: [
      card("anthropic", "claude-opus-5-5", "Claude Opus 5.5", ["5.00", "25.00"]),
      card("anthropic", "claude-haiku-5-5", "Claude Haiku 5.5", ["1.00", "5.00"]),
      card("standard:s1", "sample-model", "sample-model", null),
    ],
    roles,
    defaults: { ...roles, checker: { connector: "standard:s1", model: "sample-model" } },
  };
}

const caps = { brief: "3.00", day: "15.00", month: "150.00", budget_above: "0.50", subscription_stops: false };

function core(routes: Record<string, Route> = {}) {
  const fetch = vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const key = `${init.method ?? "GET"} ${String(input)}`;
    const route = routes[key];
    if (route) return route(init);
    if (key === "GET /api/settings/ai") return Response.json(settings());
    if (key === "GET /api/settings/ai/caps") return Response.json(caps);
    return new Response("not found", { status: 404 });
  });
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

const calls = (fetch: ReturnType<typeof core>, method: string, url: string) =>
  fetch.mock.calls.filter(([u, init]) => String(u) === url && (init?.method ?? "GET") === method);
const bodies = (fetch: ReturnType<typeof core>, method: string, url: string) =>
  calls(fetch, method, url).map(([, init]) => JSON.parse(String(init!.body)) as unknown);

function Harness() {
  const ai = useAiSettings();
  return <AiSettings ai={ai} />;
}

beforeEach(() => setLanguage("ar"));

describe("AiSettings", () => {
  it("role selects show each model's price and source; an unknown price says so", async () => {
    core();
    render(<Harness />);
    const lead = await screen.findByRole("combobox", { name: texts.roleLead.ar });
    expect(lead).toHaveValue(JSON.stringify(opus));
    const options = within(lead).getAllByRole("option").map((option) => option.textContent);
    expect(options).toEqual([
      expect.stringContaining("Claude Opus 5.5"),
      expect.stringContaining("Claude Haiku 5.5"),
      expect.stringContaining("sample-model"),
    ]);
    expect(options[0]).toContain("5.00 دولار للداخل، 25.00 دولار للخارج لكل مليون توكن");
    expect(options[0]).toContain("المصدر: genai-prices sample: https://example.com/prices");
    expect(options[2]).toContain(texts.priceUnknown.ar);
    expect(options[0]).toContain(texts.recommended.ar); // the Recommended Setting for the Lead QS

    const checker = screen.getByRole("combobox", { name: texts.roleChecker.ar });
    const marked = within(checker).getAllByRole("option").filter((o) => o.textContent?.includes(texts.recommended.ar));
    expect(marked.map((o) => o.textContent)).toEqual([expect.stringContaining("sample-model")]);
  });

  it("choosing a model for a role saves every role in the core", async () => {
    const fetch = core({ "PUT /api/settings/ai/roles": (init) => Response.json(JSON.parse(String(init.body))) });
    const user = userEvent.setup();
    render(<Harness />);
    const lead = await screen.findByRole("combobox", { name: texts.roleLead.ar });
    await user.selectOptions(lead, JSON.stringify(haiku));
    await waitFor(() => expect(bodies(fetch, "PUT", "/api/settings/ai/roles")).toEqual([{ ...roles, lead: haiku }]));
    expect(lead).toHaveValue(JSON.stringify(haiku));
  });

  it("a role the core refuses goes back, and says so", async () => {
    core({ "PUT /api/settings/ai/roles": () => Response.json({ role: "lead", allowed: [opus] }, { status: 422 }) });
    const user = userEvent.setup();
    render(<Harness />);
    const lead = await screen.findByRole("combobox", { name: texts.roleLead.ar });
    await user.selectOptions(lead, JSON.stringify(haiku));
    expect(await screen.findByText(texts.roleNotSaved.ar)).toHaveAttribute("role", "alert");
    expect(lead).toHaveValue(JSON.stringify(opus));
  });

  it("adding a Standard Link sends the key once and never shows it", async () => {
    let added = false;
    const fresh = { id: "standard:s2", kind: "model", name: "Local - sample", provider: "local", on_device: true, key_set: true, error: null };
    const fetch = core({
      "GET /api/settings/ai": () => Response.json(settings(added ? { connectors: [fresh] } : {})),
      "POST /api/settings/ai/standard": () => {
        added = true;
        return Response.json(fresh, { status: 201 });
      },
    });
    const user = userEvent.setup();
    render(<Harness />);
    await user.type(await screen.findByLabelText(texts.providerName.ar), "Local - sample");
    await user.type(screen.getByLabelText(texts.baseUrl.ar), "http://127.0.0.1:11434/v1");
    const key = screen.getByLabelText(texts.providerKey.ar);
    expect(key).toHaveAttribute("type", "password");
    await user.type(key, "sk-sample-secret");
    await user.click(screen.getByRole("button", { name: texts.addProvider.ar }));

    expect(await screen.findByText("Local - sample")).toBeInTheDocument();
    expect(bodies(fetch, "POST", "/api/settings/ai/standard")).toEqual([
      { name: "Local - sample", base_url: "http://127.0.0.1:11434/v1", key: "sk-sample-secret" },
    ]);
    expect(screen.queryByDisplayValue("sk-sample-secret")).not.toBeInTheDocument();
    expect(document.body.textContent).not.toContain("sk-sample-secret");
    expect(screen.getByText(texts.onDevice.ar)).toBeInTheDocument();
  });

  it("a Standard Link with no key sends no key", async () => {
    const fetch = core({ "POST /api/settings/ai/standard": () => Response.json({}, { status: 201 }) });
    const user = userEvent.setup();
    render(<Harness />);
    await user.type(await screen.findByLabelText(texts.providerName.ar), "Ollama - sample");
    await user.type(screen.getByLabelText(texts.baseUrl.ar), "http://localhost:11434/v1");
    await user.click(screen.getByRole("button", { name: texts.addProvider.ar }));
    await waitFor(() =>
      expect(bodies(fetch, "POST", "/api/settings/ai/standard")).toEqual([
        { name: "Ollama - sample", base_url: "http://localhost:11434/v1" },
      ]),
    );
  });

  it("shows why a connector's models could not be listed, and removes a Standard Link", async () => {
    const url = "/api/settings/ai/standard/standard%3As1"; // the connector's whole id
    const fetch = core({ [`DELETE ${url}`]: () => new Response(null, { status: 204 }) });
    const user = userEvent.setup();
    render(<Harness />);
    const row = (await screen.findByText("Sample provider")).closest("li")!;
    expect(within(row).getByText("مقدرناش نوصل لـ Sample provider.")).toBeInTheDocument();
    await user.click(within(row).getByRole("button", { name: texts.remove.ar }));
    await waitFor(() => expect(calls(fetch, "DELETE", url)).toHaveLength(1));
  });

  it("a refused address says what One needs, in its own words", async () => {
    const detail = [{ loc: ["body", "base_url"], msg: "a key needs https", type: "value_error" }];
    core({ "POST /api/settings/ai/standard": () => Response.json({ detail }, { status: 422 }) });
    const user = userEvent.setup();
    render(<Harness />);
    await user.type(await screen.findByLabelText(texts.providerName.ar), "Remote - sample");
    await user.type(screen.getByLabelText(texts.baseUrl.ar), "http://example.com/v1");
    await user.type(screen.getByLabelText(texts.providerKey.ar), "sk-sample");
    await user.click(screen.getByRole("button", { name: texts.addProvider.ar }));
    expect(await screen.findByText(texts.providerUrlRefused.ar)).toHaveAttribute("role", "alert");
    expect(screen.getByLabelText(texts.providerKey.ar)).toHaveValue(""); // never kept on the page
  });

  it("Claude Code is checked only when the button is pressed", async () => {
    let answer = { installed: true, compatible: true, signed_in: true, version: "2.1.318", code: null, models: ["opus"] };
    const fetch = core({ "GET /api/settings/ai/claude-code": () => Response.json(answer) });
    const user = userEvent.setup();
    render(<Harness />);
    const check = await screen.findByRole("button", { name: texts.check.ar });
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(calls(fetch, "GET", "/api/settings/ai/claude-code")).toHaveLength(0); // no check by itself, no polling

    await user.click(check);
    expect(await screen.findByText("Claude Code 2.1.318 جاهز.")).toBeInTheDocument();
    expect(calls(fetch, "GET", "/api/settings/ai/claude-code")).toHaveLength(1);

    answer = { ...answer, compatible: false, code: "CLAUDE_CODE_TOO_OLD" as never };
    await user.click(check);
    expect(await screen.findByText(texts.claudeCodeTooOld.ar)).toBeInTheDocument();
  });

  it("switching Claude Code on saves it and says it keeps its own copy", async () => {
    const fetch = core({ "PUT /api/settings/ai/claude-code": (init) => Response.json(JSON.parse(String(init.body))) });
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(await screen.findByRole("checkbox", { name: texts.useClaudeCode.ar }));
    expect(await screen.findByText(texts.claudeCodeCopy.ar)).toBeInTheDocument();
    expect(bodies(fetch, "PUT", "/api/settings/ai/claude-code")).toEqual([{ path: null, on: true }]);
  });

  it("enters a price for a model One does not know", async () => {
    const fetch = core({ "PUT /api/settings/ai/prices": (init) => Response.json(JSON.parse(String(init.body))) });
    const user = userEvent.setup();
    render(<Harness />);
    const form = (await screen.findByRole("heading", { name: texts.enterPrice.ar })).closest("form")!;
    expect(within(form).getAllByRole("option").map((o) => o.textContent)).toEqual(["sample-model"]);
    await user.type(within(form).getByLabelText(texts.priceIn.ar), "0.27");
    await user.type(within(form).getByLabelText(texts.priceOut.ar), "1.10");
    await user.click(within(form).getByRole("button", { name: texts.save.ar }));
    await waitFor(() =>
      expect(bodies(fetch, "PUT", "/api/settings/ai/prices")).toEqual([
        { connector: "standard:s1", model: "sample-model", in: "0.27", out: "1.10" },
      ]),
    );
  });

  it("the caps are exact numbers, saved as typed", async () => {
    const fetch = core({ "PUT /api/settings/ai/caps": (init) => Response.json(JSON.parse(String(init.body))) });
    const user = userEvent.setup();
    render(<Harness />);
    const day = await screen.findByLabelText(texts.capDay.ar);
    await waitFor(() => expect(day).toHaveValue("15.00"));
    expect(screen.getByLabelText(texts.budgetAbove.ar)).toHaveValue("0.50");
    await user.clear(day);
    await user.type(day, "20.50");
    const form = day.closest("form")!;
    await user.click(within(form).getByRole("button", { name: texts.save.ar }));
    expect(await within(form).findByRole("status")).toHaveTextContent(texts.capsSaved.ar);
    expect(bodies(fetch, "PUT", "/api/settings/ai/caps")).toEqual([{ ...caps, day: "20.50" }]);
  });

  it("caps the core refuses say why", async () => {
    const notExact = { en: "Write the amount as an exact number, like 20.50.", ar: "اكتب المبلغ رقم مظبوط، زي 20.50." };
    core({ "PUT /api/settings/ai/caps": () => Response.json({ error: notExact, field: "day" }, { status: 422 }) });
    const user = userEvent.setup();
    render(<Harness />);
    const day = await screen.findByLabelText(texts.capDay.ar);
    await waitFor(() => expect(day).toHaveValue("15.00"));
    await user.click(within(day.closest("form")!).getByRole("button", { name: texts.save.ar }));
    expect(await screen.findByRole("alert")).toHaveTextContent(notExact.ar);
  });

  it("a settings load that fails says so and Retry tries again", async () => {
    let calls = 0;
    core({ "GET /api/settings/ai": () => (++calls === 1 ? new Response("boom", { status: 500 }) : Response.json(settings())) });
    const user = userEvent.setup();
    render(<Harness />);
    expect(await screen.findByRole("alert")).toHaveTextContent(texts.aiFailed.ar);
    await user.click(screen.getByRole("button", { name: texts.retry.ar }));
    expect(await screen.findByRole("combobox", { name: texts.roleLead.ar })).toBeInTheDocument();
  });
});
