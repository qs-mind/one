// A card that comes while a Brief is at work shows at once, without reloading the chat (founder's run, 5 Nov).
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fakeSources } from "../canvas/fake";
import { setLanguage, texts } from "../i18n";
import { setCurrentProject } from "../records/project";
import { App } from "./App";
import { core, P1 } from "./testing";

vi.mock("../canvas/Canvas", async () => ({ Canvas: (await import("./testing")).CanvasStandIn }));

beforeEach(() => {
  setLanguage("ar");
  setCurrentProject(undefined);
});

/** A Brief's stream the test writes to as it goes, as the core does. */
function liveStream() {
  const encoder = new TextEncoder();
  let controller!: ReadableStreamDefaultController<Uint8Array>;
  const body = new ReadableStream<Uint8Array>({ start: (c) => void (controller = c) });
  return {
    response: () =>
      new Response(body, { headers: { "content-type": "text/event-stream", "x-vercel-ai-ui-message-stream": "v1" } }),
    send: (chunk: object) => controller.enqueue(encoder.encode(`data: ${JSON.stringify(chunk)}\n\n`)),
    close: () => controller.close(),
  };
}

const agent = { en: "Lead QS", ar: "كبير مهندسي الكميات" };
const progress = (n: number) => ({
  type: "data-progress",
  id: "run-1",
  data: { agent, text: { en: `Look at the BOQ columns ${n}`, ar: `يبص على أعمدة المقايسة ${n}` }, lang: "ar" },
});
const status = (state: string) => ({ type: "data-status", id: "b1", data: { state, step: null } });
const rows = {
  kind: "rows",
  title: { en: "Import the BOQ?", ar: "أستورد المقايسة؟" },
  detail: { en: "Rows 5 to 200.", ar: "الصفوف من 5 لـ 200." },
  options: ["keep", "no"],
  status: "pending",
  payload: {
    columns: [{ key: "field", label: { en: "Field", ar: "الحقل" } }],
    rows: [{ field: "الوصف" }],
    tick: true,
  },
};
const cards: Record<string, { data: object; shows: string }> = {
  rows: { data: rows, shows: "الصفوف من 5 لـ 200." },
  question: {
    data: {
      kind: "question",
      title: { en: "Question", ar: "سؤال" },
      detail: { en: "One question.", ar: "سؤال واحد." },
      options: ["sent"],
      status: "pending",
      payload: { questions: [{ id: "q1", text: "الخرسانة جاهزة؟" }] },
    },
    shows: "الخرسانة جاهزة؟",
  },
  cost: {
    data: { kind: "cost", title: { en: "Spend more?", ar: "نصرف أكتر؟" }, detail: { en: "Over the cap.", ar: "فوق الحد." }, options: ["yes", "no"], status: "pending" },
    shows: "فوق الحد.",
  },
  connector: {
    data: {
      kind: "connector",
      title: { en: "Add a Connector?", ar: "نضيف وصلة؟" },
      detail: { en: "A tool server.", ar: "سيرفر أدوات." },
      options: ["yes", "no"],
      status: "pending",
      payload: { connector: { name: "عينة", transport: "stdio", runs: "npx sample" }, tools: [] },
    },
    shows: "سيرفر أدوات.",
  },
};

describe("a card that comes mid-Brief", () => {
  for (const [kind, card] of Object.entries(cards)) {
    it(`a ${kind} card after progress parts shows without reload`, async () => {
      setCurrentProject(P1);
      const live = liveStream();
      core({ routes: { "POST /api/chat": () => live.response() } });
      const user = userEvent.setup();
      render(<App />);
      await user.type(await screen.findByRole("textbox", { name: texts.message.ar }), "استورد الـ BOQ{enter}");
      act(() => {
        live.send({ type: "start", messageId: "a1" });
        live.send({ type: "start-step" });
        live.send(status("running"));
        live.send(progress(1));
      });
      await screen.findByText("يبص على أعمدة المقايسة 1");
      await act(async () => {
        live.send(progress(2));
        await new Promise((resolve) => setTimeout(resolve, 30));
        live.send(status("waiting_engineer"));
        live.send({ type: "data-card", id: "c1", data: card.data });
      });
      expect(await screen.findByText(card.shows)).toBeInTheDocument();
    });
  }

  const asked = [
    { id: "u1", role: "user", parts: [{ type: "text", text: "استورد الـ BOQ" }] },
    {
      id: "a1",
      role: "assistant",
      parts: [progress(1), status("waiting_engineer"), { type: "data-card", id: "c1", data: rows }],
    },
  ];

  it("a stream that drops while the Brief runs is joined again, and the card shows", async () => {
    setCurrentProject(P1);
    const live = liveStream();
    let reloaded = false;
    const fetch = core({
      routes: {
        "POST /api/chat": () => live.response(),
        "GET /api/chat/p1/messages": () => Response.json({ messages: reloaded ? asked : [] }),
      },
    });
    const user = userEvent.setup();
    render(<App />);
    await user.type(await screen.findByRole("textbox", { name: texts.message.ar }), "استورد الـ BOQ{enter}");
    act(() => {
      live.send({ type: "start", messageId: "a1" });
      live.send(status("running"));
      live.send(progress(1));
    });
    await screen.findByText("يبص على أعمدة المقايسة 1");
    reloaded = true;
    act(() => live.close()); // the connection is gone before the card came
    expect(await screen.findByText("الصفوف من 5 لـ 200.", {}, { timeout: 4000 })).toBeInTheDocument();
    expect(fetch.mock.calls.some(([url]) => String(url) === "/api/chat/p1/stream")).toBe(true);
  });

  it("scrolled up, new content shows “New below”; a card that comes to wait is brought into view", async () => {
    setCurrentProject(P1);
    const live = liveStream();
    core({ routes: { "POST /api/chat": () => live.response() } });
    const intoView = vi.fn();
    Element.prototype.scrollIntoView = intoView;
    const user = userEvent.setup();
    render(<App />);
    await user.type(await screen.findByRole("textbox", { name: texts.message.ar }), "استورد الـ BOQ{enter}");
    act(() => {
      live.send({ type: "start", messageId: "a1" });
      live.send(status("running"));
      live.send(progress(1));
    });
    await screen.findByText("يبص على أعمدة المقايسة 1");
    const log = screen.getByRole("log");
    const scrollTo = vi.fn();
    Object.assign(log, { scrollTo });
    Object.defineProperties(log, {
      scrollHeight: { value: 2000, configurable: true },
      clientHeight: { value: 300, configurable: true },
      scrollTop: { value: 100, configurable: true, writable: true },
    });
    act(() => void log.dispatchEvent(new Event("scroll"))); // the engineer scrolled up to read
    act(() => live.send(progress(2)));
    const below = await screen.findByRole("button", { name: texts.newBelow.ar });
    expect(scrollTo).not.toHaveBeenCalled(); // the log stays where the engineer reads
    act(() => {
      live.send(status("waiting_engineer"));
      live.send({ type: "data-card", id: "c1", data: rows });
    });
    await screen.findByText("الصفوف من 5 لـ 200.");
    await waitFor(() => expect(intoView).toHaveBeenCalled());
    expect((intoView.mock.contexts[0] as HTMLElement).dataset.card).toBe("c1");
    await user.click(below);
    expect(scrollTo).toHaveBeenCalledWith({ top: 2000 });
    expect(screen.queryByRole("button", { name: texts.newBelow.ar })).not.toBeInTheDocument();
  });

  it("the engineer's own Arabic message with English in it: one block per line, the English isolated", async () => {
    setCurrentProject(P1);
    const live = liveStream();
    core({ routes: { "POST /api/chat": () => live.response() } });
    const user = userEvent.setup();
    render(<App />);
    await user.type(await screen.findByRole("textbox", { name: texts.message.ar }), "اقرا الـ BOQ{shift>}{enter}{/shift}وقولي الإجمالي{enter}");
    const first = await screen.findByText((_, el) => el?.tagName === "P" && el.textContent === "اقرا الـ BOQ");
    expect(first).toHaveAttribute("dir", "auto");
    expect(first.querySelector("bdi")).toHaveTextContent("BOQ");
    expect(first.nextElementSibling).toHaveTextContent("وقولي الإجمالي");
  });

  it("an older reply with no language on its progress follows the engineer's message, in the English page", async () => {
    setLanguage("en");
    setCurrentProject(P1);
    const old = {
      type: "data-progress",
      id: "run-1",
      data: { agent, text: { en: "Look at the BOQ columns", ar: "يبص على أعمدة المقايسة" } },
    };
    const messages = [
      { id: "u1", role: "user", parts: [{ type: "text", text: "اقرا الـ BOQ وقولي إجمالي البنود" }] },
      { id: "a1", role: "assistant", parts: [old] },
    ];
    core({ routes: { "GET /api/chat/p1/messages": () => Response.json({ messages }) } });
    render(<App />);
    const line = await screen.findByRole("list", { name: texts.progressLine.en });
    expect(line).toHaveTextContent("يبص على أعمدة المقايسة");
    expect(line).not.toHaveTextContent("Look at");
  });

  it("“Waiting for you” with no card in the chat reads the chat again from the core", async () => {
    setCurrentProject(P1);
    let reads = 0;
    core({
      routes: {
        "GET /api/chat/p1/messages": () => Response.json({ messages: reads++ ? asked : asked.slice(0, 1) }),
      },
    });
    const sources = fakeSources({ status: { waiting: 1 } });
    render(<App sourcesFor={() => sources} />);
    expect(await screen.findByText("الصفوف من 5 لـ 200.", {}, { timeout: 4000 })).toBeInTheDocument();
    expect(reads).toBe(2);
  });
});
