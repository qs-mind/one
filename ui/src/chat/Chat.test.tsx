import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { setLanguage, texts } from "../i18n";
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

// A body in the AI SDK UI message stream format, as the core sends it. Left open (`end: false`), it behaves like a
// slow reply that only ends when the request is aborted.
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

type Chats = (init: RequestInit) => Response | Promise<Response>;

const modelList = [
  { id: "claude-fable-5-1", name: "Claude Fable 5.1" },
  { id: "claude-opus-5-5", name: "Claude Opus 5.5" },
];

function core({
  keySet = true,
  chat,
  models = () => Response.json(modelList),
  saveModel,
}: { keySet?: boolean; chat?: Chats; models?: () => Response | Promise<Response>; saveModel?: () => Response } = {}) {
  let model = "claude-opus-5-5";
  const fetch = vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = String(input);
    const method = init.method ?? "GET";
    if (url === "/api/settings/ai-key" && method === "GET") return Response.json({ set: keySet });
    if (url === "/api/settings/ai-key" && method === "PUT") return Response.json({ set: true });
    if (url === "/api/settings/models") return models();
    if (url === "/api/settings/model" && method === "GET") return Response.json({ id: model });
    if (url === "/api/settings/model" && method === "PUT") {
      if (saveModel) return saveModel();
      model = (JSON.parse(String(init.body)) as { id: string }).id;
      return Response.json({ id: model });
    }
    if (url === "/api/chat" && chat) return chat(init);
    return new Response("not found", { status: 404 });
  });
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

const uiStream = { "content-type": "text/event-stream", "x-vercel-ai-ui-message-stream": "v1" };

beforeEach(() => setLanguage("ar"));

describe("Chat", () => {
  it("streams the reply and shows it", async () => {
    const fetch = core({ chat: (init) => new Response(stream(reply, init.signal), { headers: uiStream }) });
    const user = userEvent.setup();
    render(<Chat />);
    await user.type(await screen.findByRole("textbox"), "سعّر البند ده{enter}");

    const answer = await screen.findByText(/مرحبا Hello/);
    expect(answer.closest("[dir]")).toHaveAttribute("dir", "auto"); // mixed Arabic and English lines render right
    expect(screen.getByText("سعّر البند ده")).toBeInTheDocument();
    const [, init] = fetch.mock.calls.find(([url]) => url === "/api/chat")!;
    expect(String(init?.body)).toContain("سعّر البند ده");
  });

  it("stop ends the reply and the box is ready again", async () => {
    const signals: AbortSignal[] = [];
    core({
      chat: (init) => {
        signals.push(init.signal!);
        return new Response(stream(reply.slice(0, 4), init.signal, false), { headers: uiStream });
      },
    });
    const user = userEvent.setup();
    render(<Chat />);
    await user.type(await screen.findByRole("textbox"), "hello{enter}");
    await screen.findByText(/مرحبا/);

    await user.click(screen.getByRole("button", { name: texts.stop.ar }));
    expect(signals[0]!.aborted).toBe(true); // no request is left running
    expect(await screen.findByRole("button", { name: texts.send.ar })).toBeInTheDocument();

    await user.type(screen.getByRole("textbox"), "again{enter}");
    await waitFor(() => expect(signals).toHaveLength(2));
  });

  it("shows a plain line when the reply fails", async () => {
    core({ chat: () => new Response("boom", { status: 500 }) });
    const user = userEvent.setup();
    render(<Chat />);
    await user.type(await screen.findByRole("textbox"), "hello{enter}");
    expect(await screen.findByRole("alert")).toHaveTextContent(texts.chatError.ar);
  });

  it("shows the core's plain {en, ar} line when the model fails, in the engineer's language", async () => {
    const refused = {
      en: "The Claude key was refused. Check it, or add a new one.",
      ar: "مفتاح Claude اترفض. راجعه، أو ضيف مفتاح جديد.",
    };
    const failed = [...reply.slice(0, 2), { type: "error", errorText: JSON.stringify(refused) }];
    core({ chat: () => new Response(stream(failed), { headers: uiStream }) });
    const user = userEvent.setup();
    render(<Chat />);
    await user.type(await screen.findByRole("textbox"), "hello{enter}");
    expect(await screen.findByRole("alert")).toHaveTextContent(refused.ar);

    await user.click(screen.getByRole("button", { name: texts.otherLanguage.ar }));
    expect(screen.getByRole("alert")).toHaveTextContent(refused.en);
  });

  it("no key: shows the add-key screen in both languages", async () => {
    core({ keySet: false });
    const { unmount } = render(<Chat />);
    expect(await screen.findByRole("heading", { name: texts.aiKeyTitle.ar })).toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    unmount();

    setLanguage("en");
    render(<Chat />);
    expect(await screen.findByRole("heading", { name: texts.aiKeyTitle.en })).toBeInTheDocument();
  });

  it("saving the key stores it in the core and shows only that it was added", async () => {
    const fetch = core({ keySet: false });
    const user = userEvent.setup();
    render(<Chat />);
    const field = await screen.findByLabelText(texts.aiKeyLabel.ar);
    expect(field).toHaveAttribute("type", "password");
    await user.type(field, "sk-ant-test");
    await user.click(screen.getByRole("button", { name: texts.save.ar }));

    expect(await screen.findByRole("status")).toHaveTextContent(texts.keyAdded.ar);
    expect(screen.queryByDisplayValue("sk-ant-test")).not.toBeInTheDocument();
    expect(screen.getByRole("textbox")).toBeInTheDocument(); // the chat is open now
    const put = fetch.mock.calls.find(([, init]) => init?.method === "PUT")!;
    expect(JSON.parse(String(put[1]!.body))).toEqual({ provider: "anthropic", value: "sk-ant-test" });
  });

  it("replacing the key opens its panel beside the chat, which stays", async () => {
    core();
    const user = userEvent.setup();
    render(<Chat />);
    await user.click(await screen.findByRole("button", { name: texts.aiKey.ar }));
    expect(screen.getByRole("heading", { name: texts.aiKeyTitle.ar })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: texts.message.ar })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: texts.close.ar }));
    expect(screen.queryByRole("heading", { name: texts.aiKeyTitle.ar })).not.toBeInTheDocument();
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
    core({ chat: () => new Response(stream(bold), { headers: uiStream }) });
    const user = userEvent.setup();
    render(<Chat />);
    await user.type(await screen.findByRole("textbox"), "**as typed**{enter}");

    expect((await screen.findByText("total")).tagName).toBe("STRONG");
    expect(screen.getByText("**as typed**")).toBeInTheDocument();
  });
});

describe("Model", () => {
  const panel = () => screen.getByRole("region", { name: texts.modelTitle.ar });

  it("the header shows the model in use; its panel lists the key's models with that one marked", async () => {
    core();
    const user = userEvent.setup();
    render(<Chat />);
    await user.click(await screen.findByRole("button", { name: "Claude Opus 5.5" }));

    const choices = within(panel()).getAllByRole("button", { name: /Claude/ });
    expect(choices.map((choice) => choice.textContent)).toEqual([
      expect.stringContaining("Claude Fable 5.1"),
      expect.stringContaining("Claude Opus 5.5"),
    ]);
    expect(choices[1]).toHaveAttribute("aria-current", "true");
    expect(choices[1]).toHaveTextContent(texts.modelInUse.ar);
    expect(choices[0]).not.toHaveAttribute("aria-current");
  });

  it("choosing a model saves it in the core, closes the panel and names it in the header", async () => {
    const fetch = core();
    const user = userEvent.setup();
    render(<Chat />);
    await user.click(await screen.findByRole("button", { name: "Claude Opus 5.5" }));
    await user.click(within(panel()).getByRole("button", { name: /Claude Fable 5.1/ }));

    expect(await screen.findByRole("button", { name: "Claude Fable 5.1" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: texts.modelTitle.ar })).not.toBeInTheDocument();
    const put = fetch.mock.calls.find(([url, init]) => url === "/api/settings/model" && init?.method === "PUT")!;
    expect(JSON.parse(String(put[1]!.body))).toEqual({ id: "claude-fable-5-1" });
  });

  it("works from the keyboard", async () => {
    const fetch = core();
    const user = userEvent.setup();
    render(<Chat />);
    await screen.findByRole("button", { name: "Claude Opus 5.5" });

    await user.tab(); // Projects
    await user.tab(); // Project Records
    await user.tab();
    expect(screen.getByRole("button", { name: "Claude Opus 5.5" })).toHaveFocus();
    await user.keyboard("{Enter}");
    await waitFor(() => expect(within(panel()).getByRole("button", { name: /Claude Opus 5.5/ })).toHaveFocus());
    await user.keyboard("{Shift>}{Tab}{/Shift}{Enter}");

    expect(await screen.findByRole("button", { name: "Claude Fable 5.1" })).toBeInTheDocument();
    expect(fetch.mock.calls.some(([url, init]) => url === "/api/settings/model" && init?.method === "PUT")).toBe(true);
  });

  it("says it is loading while the list comes", async () => {
    let answer: (response: Response) => void = () => undefined;
    core({ models: () => new Promise<Response>((resolve) => (answer = resolve)) });
    const user = userEvent.setup();
    render(<Chat />);
    await user.click(await screen.findByRole("button", { name: "claude-opus-5-5" })); // the name comes with the list

    expect(within(panel()).getByText(texts.modelsLoading.ar)).toBeInTheDocument();
    answer(Response.json(modelList));
    expect(await within(panel()).findByRole("button", { name: /Claude Fable 5.1/ })).toBeInTheDocument();
  });

  it("no key: says to add the key first", async () => {
    core({ keySet: false, models: () => Response.json({ error: { en: "no key", ar: "مفيش مفتاح" } }, { status: 409 }) });
    const user = userEvent.setup();
    render(<Chat />);
    await user.click(await screen.findByRole("button", { name: "claude-opus-5-5" }));
    expect(await within(panel()).findByText(texts.modelsNoKey.ar)).toBeInTheDocument();
  });

  it("shows the core's plain line when the list fails, and Retry tries again", async () => {
    const busy = { en: "Claude is busy right now.", ar: "في ضغط على Claude دلوقتي." };
    let calls = 0; // fails when the app starts and when the panel opens, then works
    core({ models: () => (++calls <= 2 ? Response.json({ error: busy }, { status: 502 }) : Response.json(modelList)) });
    const user = userEvent.setup();
    render(<Chat />);
    await user.click(await screen.findByRole("button", { name: "claude-opus-5-5" }));

    expect(await within(panel()).findByRole("alert")).toHaveTextContent(busy.ar);
    await user.click(within(panel()).getByRole("button", { name: texts.retry.ar }));
    expect(await within(panel()).findByRole("button", { name: /Claude Fable 5.1/ })).toBeInTheDocument();
  });

  it("a choice the core could not save keeps the panel open with a plain line", async () => {
    core({ saveModel: () => new Response("boom", { status: 500 }) });
    const user = userEvent.setup();
    render(<Chat />);
    await user.click(await screen.findByRole("button", { name: "Claude Opus 5.5" }));
    await user.click(within(panel()).getByRole("button", { name: /Claude Fable 5.1/ }));

    expect(await within(panel()).findByRole("alert")).toHaveTextContent(texts.modelNotSaved.ar);
    expect(screen.getByRole("button", { name: "Claude Opus 5.5" })).toBeInTheDocument();
  });
});
