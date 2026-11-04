import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { setLanguage, texts } from "../i18n";
import { setCurrentProject } from "../records/project";
import { Chat } from "./Chat";

const reply = [
  { type: "start", messageId: "m1" },
  { type: "start-step" },
  { type: "text-start", id: "t1" },
  { type: "text-delta", id: "t1", delta: "مرحبا" },
  { type: "text-delta", id: "t1", delta: " Hello" },
  { type: "text-end", id: "t1" },
  { type: "finish-step" },
  { type: "finish" },
];

const running = { type: "data-status", id: "b1", data: { state: "running", step: null } };

// A body in the AI SDK UI message stream format, as the core sends it. Left open (`end: false`), it behaves like a
// Brief still at work, which only ends when the request is aborted.
function stream(chunks: object[], signal?: AbortSignal | null, end = true) {
  const encoder = new TextEncoder();
  return new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(`data: ${JSON.stringify(chunk)}\n\n`));
      if (end) {
        controller.enqueue(encoder.encode("data: [DONE]\n\n"));
        controller.close();
      }
      signal?.addEventListener("abort", () => controller.error(new DOMException("aborted", "AbortError")));
    },
  });
}

const uiStream = { "content-type": "text/event-stream", "x-vercel-ai-ui-message-stream": "v1" };
const streamed = (chunks: object[], init: RequestInit, end = true) =>
  new Response(stream(chunks, init.signal, end), { headers: uiStream });

type Route = (init: RequestInit) => Response | Promise<Response>;

const anthropic = { id: "anthropic", kind: "model", name: "Claude", provider: "anthropic", on_device: false, key_set: true, error: null };
const opus = { connector: "anthropic", model: "claude-opus-5-5" };
const aiSettings = (keySet: boolean) => ({
  connectors: [{ ...anthropic, key_set: keySet }],
  sheet: keySet
    ? [
        {
          ...opus,
          name: "Claude Opus 5.5",
          provider: "anthropic",
          images: true,
          tools: true,
          context: 200000,
          price_in: "5.00",
          price_out: "25.00",
          price_source: "genai-prices sample: https://example.com/prices",
          on_device: false,
          subscription: false,
        },
      ]
    : [],
  roles: keySet ? { lead: opus, checker: opus, specialist: opus, quick: opus } : {},
  defaults: keySet ? { lead: opus, checker: opus, specialist: opus, quick: opus } : {},
});

// The core behind /api: the routes a test gives, then what an idle core answers.
function core({ keySet = true, routes = {} }: { keySet?: boolean; routes?: Record<string, Route> } = {}) {
  let saved = keySet;
  const fetch = vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = String(input);
    const key = `${init.method ?? "GET"} ${url}`;
    const route = routes[key];
    if (route) return route(init);
    if (key === "GET /api/settings/ai") return Response.json(aiSettings(saved));
    if (key === "PUT /api/settings/ai-key") {
      saved = true;
      return Response.json({ set: true });
    }
    if (key === "GET /api/settings/ai/caps") return Response.json({ brief: "3.00", day: "15.00", month: "150.00", budget_above: "0.50" });
    if (key === "GET /api/briefs/unfinished") return Response.json({ briefs: [] });
    if (/^GET \/api\/chat\/[^/]+\/messages$/.test(key)) return Response.json({ messages: [] });
    if (/^GET \/api\/chat\/[^/]+\/stream$/.test(key)) return new Response(null, { status: 204 });
    return new Response("not found", { status: 404 });
  });
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

const calls = (fetch: ReturnType<typeof core>, method: string, url: string) =>
  fetch.mock.calls.filter(([u, init]) => String(u) === url && (init?.method ?? "GET") === method);
const box = () => screen.findByRole("textbox", { name: texts.message.ar });

beforeEach(() => {
  setLanguage("ar");
  setCurrentProject(undefined);
});

describe("Chat", () => {
  it("streams the reply and sends only the new message, under the chat's id", async () => {
    const fetch = core({ routes: { "POST /api/chat": (init) => streamed(reply, init) } });
    const user = userEvent.setup();
    render(<Chat />);
    await user.type(await box(), "سعّر البند ده{enter}");

    const answer = await screen.findByText(/مرحبا Hello/);
    expect(answer.closest("[dir]")).toHaveAttribute("dir", "auto"); // mixed Arabic and English lines render right
    expect(screen.getByText("سعّر البند ده")).toBeInTheDocument();
    const [, init] = calls(fetch, "POST", "/api/chat")[0]!;
    const body = JSON.parse(String(init!.body)) as { id: string; messages: { parts: { text: string }[] }[] };
    expect(body.id).toBe("general");
    expect(body.messages).toHaveLength(1);
    expect(body.messages[0]!.parts[0]!.text).toBe("سعّر البند ده");
  });

  it("a project's chat has the project's id", async () => {
    setCurrentProject({ id: "p".repeat(32), name: "مدرسة - عينة", created_at: "2026-11-04T08:00:00+00:00" });
    const fetch = core({ routes: { "POST /api/chat": (init) => streamed(reply, init) } });
    const user = userEvent.setup();
    render(<Chat />);
    await waitFor(() => expect(calls(fetch, "GET", `/api/chat/${"p".repeat(32)}/messages`)).toHaveLength(1));
    await user.type(await box(), "hello{enter}");
    await screen.findByText(/مرحبا/);
    const [, init] = calls(fetch, "POST", "/api/chat")[0]!;
    expect((JSON.parse(String(init!.body)) as { id: string }).id).toBe("p".repeat(32));
  });

  it("stop ends the reply and the box is ready again", async () => {
    const signals: AbortSignal[] = [];
    core({
      routes: {
        "POST /api/chat": (init) => {
          signals.push(init.signal!);
          return streamed(reply.slice(0, 4), init, false);
        },
      },
    });
    const user = userEvent.setup();
    render(<Chat />);
    await user.type(await box(), "hello{enter}");
    await screen.findByText(/مرحبا/);

    await user.click(screen.getByRole("button", { name: texts.stop.ar }));
    expect(signals[0]!.aborted).toBe(true); // no request is left running
    expect(await screen.findByRole("button", { name: texts.send.ar })).toBeInTheDocument();

    await user.type(screen.getByRole("textbox", { name: texts.message.ar }), "again{enter}");
    await waitFor(() => expect(signals).toHaveLength(2));
  });

  it("stop posts the Brief's stop call and the box is ready", async () => {
    const signals: AbortSignal[] = [];
    const fetch = core({
      routes: {
        "POST /api/chat": (init) => {
          signals.push(init.signal!);
          return streamed([...reply.slice(0, 4), running], init, false);
        },
        "POST /api/briefs/b1/stop": () => Response.json({ state: "stopped" }),
      },
    });
    const user = userEvent.setup();
    render(<Chat />);
    await user.type(await box(), "سعّر البنود - عينة{enter}");
    await screen.findByText(/مرحبا/);

    await user.click(screen.getByRole("button", { name: texts.stop.ar }));
    await waitFor(() => expect(calls(fetch, "POST", "/api/briefs/b1/stop")).toHaveLength(1));
    expect(signals[0]!.aborted).toBe(true);
    expect(await screen.findByRole("button", { name: texts.send.ar })).toBeInTheDocument();

    await user.type(screen.getByRole("textbox", { name: texts.message.ar }), "again{enter}");
    await waitFor(() => expect(signals).toHaveLength(2)); // a new Brief, not steering the stopped one
    expect(calls(fetch, "POST", "/api/briefs/b1/steer")).toHaveLength(0);
  });

  it("sending while a Brief runs steers it, and shows it as steering", async () => {
    const fetch = core({
      routes: {
        "POST /api/chat": (init) => streamed([...reply.slice(0, 4), running], init, false),
        "POST /api/briefs/b1/steer": () => new Response(null, { status: 202 }),
      },
    });
    const user = userEvent.setup();
    render(<Chat />);
    await user.type(await box(), "سعّر البنود - عينة{enter}");
    await screen.findByText(/مرحبا/);

    const field = screen.getByRole("textbox", { name: texts.message.ar });
    expect(field).toBeEnabled();
    await user.type(field, "استخدم أسعار الشهر ده{enter}");
    await waitFor(() => expect(calls(fetch, "POST", "/api/briefs/b1/steer")).toHaveLength(1));
    const [, init] = calls(fetch, "POST", "/api/briefs/b1/steer")[0]!;
    expect(JSON.parse(String(init!.body))).toEqual({ text: "استخدم أسعار الشهر ده" });
    const bubble = (await screen.findByText("استخدم أسعار الشهر ده")).closest("li")!;
    expect(within(bubble).getByText(texts.steering.ar)).toBeInTheDocument();
    expect(calls(fetch, "POST", "/api/chat")).toHaveLength(1);
  });

  it("a message to a chat whose Brief runs elsewhere steers that Brief and joins its stream", async () => {
    let joined = false;
    const fetch = core({
      routes: {
        "POST /api/chat": () => Response.json({ brief_id: "b9" }, { status: 409 }),
        "POST /api/briefs/b9/steer": () => {
          joined = true;
          return new Response(null, { status: 202 });
        },
        "GET /api/chat/general/stream": (init) =>
          joined ? streamed(reply, init) : new Response(null, { status: 204 }),
      },
    });
    const user = userEvent.setup();
    render(<Chat />);
    await user.type(await box(), "كمان بند 04/01{enter}");
    expect(await screen.findByText(/مرحبا Hello/)).toBeInTheDocument();
    const [, init] = calls(fetch, "POST", "/api/briefs/b9/steer")[0]!;
    expect(JSON.parse(String(init!.body))).toEqual({ text: "كمان بند 04/01" });
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("shows the Progress Line and updates it in place", async () => {
    const progress = (text: string) => ({
      type: "data-progress",
      id: "run-1",
      data: { agent: { en: "Estimator", ar: "مهندس التسعير" }, text: { en: text, ar: text } },
    });
    core({
      routes: {
        "POST /api/chat": (init) => streamed([reply[0]!, progress("بيقرا صفحة 3"), progress("بيقرا صفحة 12"), running], init, false),
      },
    });
    const user = userEvent.setup();
    render(<Chat />);
    await user.type(await box(), "سعّر{enter}");
    const line = await screen.findByRole("list", { name: texts.progressLine.ar });
    await waitFor(() => expect(within(line).getAllByRole("listitem")).toHaveLength(1));
    expect(within(line).getByRole("listitem")).toHaveTextContent("بيقرا صفحة 12");
  });

  it("shows the team's messages, cards, costs and the Review code in the reply", async () => {
    const parts = [
      reply[0]!,
      { type: "data-team", id: "tm1", data: { sender: { en: "Lead QS", ar: "كبير مهندسي الكميات" }, recipient: { en: "Estimator", ar: "مهندس التسعير" }, text: "سعّر بند 03/02" } },
      { type: "data-card", id: "c1", data: { kind: "outside", title: { en: "Send?", ar: "نبعت؟" }, detail: { en: "Lead QS: emailing the BOQ.", ar: "كبير مهندسي الكميات: بيبعت المقايسة بالإيميل." }, options: ["yes", "no"], status: "pending" } },
      { type: "data-cost", id: "brief", data: { level: "info", scope: "brief", spent: "1.20", cap: "3.00", equivalent: false, text: { en: "1.20 of 3.00 USD", ar: "1.20 من 3.00 دولار" } } },
      { type: "data-review", id: "d1", data: { code: "B", comments: [{ about: "03/02", text: "quote is old" }], same_provider: false } },
      ...reply.slice(1),
    ];
    core({ routes: { "POST /api/chat": (init) => streamed(parts, init) } });
    const user = userEvent.setup();
    render(<Chat />);
    await user.type(await box(), "سعّر{enter}");
    expect(await screen.findByText("غرفة التنسيق، 1 رسالة")).toBeInTheDocument();
    expect(screen.getByText("كبير مهندسي الكميات: بيبعت المقايسة بالإيميل.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: texts.allowOnce.ar })).toBeInTheDocument();
    expect(screen.getByText("1.20 من 3.00 دولار")).toBeInTheDocument();
    expect(screen.getByText(texts.codeB.ar)).toBeInTheDocument();
  });

  it("marks unsourced numbers in the reply", async () => {
    const parts = [
      reply[0]!,
      { type: "text-start", id: "t1" },
      { type: "text-delta", id: "t1", delta: "Total 7,500 EGP from 39,850.50 EGP" },
      { type: "text-end", id: "t1" },
      { type: "data-unsourced", id: "u1", data: { values: ["7,500"] } },
      { type: "finish" },
    ];
    core({ routes: { "POST /api/chat": (init) => streamed(parts, init) } });
    const user = userEvent.setup();
    const { container } = render(<Chat />);
    await user.type(await box(), "سعّر{enter}");
    await screen.findByText(texts.noSourceNote.ar);
    expect([...container.querySelectorAll("mark")].map((mark) => mark.textContent)).toEqual(["7,500"]);
  });

  it("loads earlier messages when the chat opens, and joins a Brief still running", async () => {
    const earlier = [
      { id: "u1", role: "user", parts: [{ type: "text", text: "سعّر بند الخرسانة - عينة" }] },
      { id: "a1", role: "assistant", parts: [{ type: "text", text: "Done." }, { type: "data-review", id: "d1", data: { code: "A", comments: [], same_provider: false } }] },
      { id: "u2", role: "user", parts: [{ type: "text", text: "والحديد؟" }] },
    ];
    const live = [{ type: "start", messageId: "a2" }, running, ...reply.slice(2, 5)];
    const fetch = core({
      routes: {
        "GET /api/chat/general/messages": () => Response.json({ messages: earlier }),
        "GET /api/chat/general/stream": (init) => streamed(live, init, false),
      },
    });
    render(<Chat />);
    expect(await screen.findByText("سعّر بند الخرسانة - عينة")).toBeInTheDocument();
    expect(screen.getByText(texts.codeA.ar)).toBeInTheDocument();
    expect(await screen.findByText(/مرحبا Hello/)).toBeInTheDocument();
    const items = screen.getAllByRole("listitem").map((item) => item.textContent);
    expect(items.findIndex((text) => text?.includes("والحديد؟"))).toBeLessThan(
      items.findIndex((text) => text?.includes("مرحبا Hello")),
    );
    expect(screen.getByRole("button", { name: texts.stop.ar })).toBeInTheDocument(); // the Brief runs
    expect(calls(fetch, "GET", "/api/chat/general/stream")).toHaveLength(1);
  });

  it("offers to continue an unfinished Brief, and continues only on press", async () => {
    let continued = false;
    const fetch = core({
      routes: {
        "GET /api/briefs/unfinished": () =>
          Response.json({
            briefs: continued
              ? []
              : [{ id: "b1", chat_id: "general", project_name: null, step: { en: "pricing", ar: "بيسعّر البنود" }, state: "running" }],
          }),
        "POST /api/briefs/b1/continue": () => {
          continued = true;
          return Response.json({ state: "running" });
        },
        "GET /api/chat/general/stream": (init) => (continued ? streamed(reply, init) : new Response(null, { status: 204 })),
      },
    });
    const user = userEvent.setup();
    render(<Chat />);
    expect(await screen.findByText("التكليف ده وقف عند: بيسعّر البنود. نكمّله؟")).toBeInTheDocument();
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(calls(fetch, "POST", "/api/briefs/b1/continue")).toHaveLength(0); // never by itself

    await user.click(screen.getByRole("button", { name: texts.continue.ar }));
    expect(await screen.findByText(/مرحبا Hello/)).toBeInTheDocument(); // its stream joined
    expect(calls(fetch, "POST", "/api/briefs/b1/continue")).toHaveLength(1);
  });

  it("shows a plain line when the reply fails", async () => {
    core({ routes: { "POST /api/chat": () => new Response("boom", { status: 500 }) } });
    const user = userEvent.setup();
    render(<Chat />);
    await user.type(await box(), "hello{enter}");
    expect(await screen.findByRole("alert")).toHaveTextContent(texts.chatError.ar);
  });

  it("shows the core's plain {en, ar} line when the model fails, in the engineer's language", async () => {
    const refused = {
      en: "The Claude key was refused. Check it, or add a new one.",
      ar: "مفتاح Claude اترفض. راجعه، أو ضيف مفتاح جديد.",
    };
    const failed = [...reply.slice(0, 2), { type: "error", errorText: JSON.stringify(refused) }];
    core({ routes: { "POST /api/chat": (init) => streamed(failed, init) } });
    const user = userEvent.setup();
    render(<Chat />);
    await user.type(await box(), "hello{enter}");
    expect(await screen.findByRole("alert")).toHaveTextContent(refused.ar);

    await user.click(screen.getByRole("button", { name: texts.otherLanguage.ar }));
    expect(screen.getByRole("alert")).toHaveTextContent(refused.en);
  });

  it("no AI connected: AI settings show in place of the chat, in both languages", async () => {
    core({ keySet: false });
    const { unmount } = render(<Chat />);
    expect(await screen.findByRole("heading", { name: texts.aiTitle.ar })).toBeInTheDocument();
    expect(screen.getByText(texts.noAiYet.ar)).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: texts.message.ar })).not.toBeInTheDocument();
    unmount();

    setLanguage("en");
    render(<Chat />);
    expect(await screen.findByRole("heading", { name: texts.aiTitle.en })).toBeInTheDocument();
  });

  it("saving the first key stores it in the core, shows only that it was added, and opens the chat", async () => {
    const fetch = core({ keySet: false });
    const user = userEvent.setup();
    render(<Chat />);
    const field = await screen.findByLabelText(texts.aiKeyLabel.ar);
    expect(field).toHaveAttribute("type", "password");
    await user.type(field, "sk-ant-test");
    await user.click(screen.getByRole("button", { name: texts.save.ar }));

    expect(await screen.findByText(texts.keyAdded.ar)).toBeInTheDocument();
    expect(screen.queryByDisplayValue("sk-ant-test")).not.toBeInTheDocument();
    expect(await box()).toBeInTheDocument(); // the chat is open now
    const [, init] = calls(fetch, "PUT", "/api/settings/ai-key")[0]!;
    expect(JSON.parse(String(init!.body))).toEqual({ provider: "anthropic", value: "sk-ant-test" });
  });

  it("“AI” opens its settings beside the chat, which stays, and closes again", async () => {
    core();
    const user = userEvent.setup();
    render(<Chat />);
    await user.click(await screen.findByRole("button", { name: texts.ai.ar }));
    const panel = await screen.findByRole("region", { name: texts.aiTitle.ar });
    expect(await within(panel).findByRole("combobox", { name: texts.roleLead.ar })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: texts.message.ar })).toBeInTheDocument();
    await user.click(within(panel).getByRole("button", { name: texts.close.ar }));
    expect(screen.queryByRole("region", { name: texts.aiTitle.ar })).not.toBeInTheDocument();
  });

  it("“AI” is reached from the keyboard and its panel comes next", async () => {
    core();
    const user = userEvent.setup();
    render(<Chat />);
    await box();
    await user.tab(); // Projects
    await user.tab(); // Project Records
    await user.tab();
    expect(screen.getByRole("button", { name: texts.ai.ar })).toHaveFocus();
    await user.keyboard("{Enter}");
    const panel = await screen.findByRole("region", { name: texts.aiTitle.ar });
    await user.tab(); // language
    await user.tab();
    expect(panel).toContainElement(document.activeElement as HTMLElement);
  });

  it("switches the language from the header", async () => {
    core();
    const user = userEvent.setup();
    render(<Chat />);
    await user.click(screen.getByRole("button", { name: texts.otherLanguage.ar }));
    expect(document.documentElement.dir).toBe("ltr");
    expect(await screen.findByRole("button", { name: texts.send.en })).toBeInTheDocument();
  });

  it("shows the reply's Markdown, not its marks; the engineer's own message stays plain", async () => {
    const bold = [...reply.slice(0, 3), { type: "text-delta", id: "t1", delta: "The **total** is known." }, ...reply.slice(5)];
    core({ routes: { "POST /api/chat": (init) => streamed(bold, init) } });
    const user = userEvent.setup();
    render(<Chat />);
    await user.type(await box(), "**as typed**{enter}");

    expect((await screen.findByText("total")).tagName).toBe("STRONG");
    expect(screen.getByText("**as typed**")).toBeInTheDocument();
  });
});
