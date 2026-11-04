import { render, screen, waitFor } from "@testing-library/react";
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

function core({ keySet = true, chat }: { keySet?: boolean; chat?: Chats } = {}) {
  const fetch = vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = String(input);
    if (url === "/api/settings/ai-key" && (init.method ?? "GET") === "GET") return Response.json({ set: keySet });
    if (url === "/api/settings/ai-key" && init.method === "PUT") return Response.json({ set: true });
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

  it("switches the language from the header", async () => {
    core();
    const user = userEvent.setup();
    render(<Chat />);
    await user.click(screen.getByRole("button", { name: texts.otherLanguage.ar }));
    expect(document.documentElement.dir).toBe("ltr");
    expect(await screen.findByRole("button", { name: texts.send.en })).toBeInTheDocument();
  });
});
