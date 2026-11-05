// Motion in the chat (docs/specs/2026-11-05-motion-design.md, §2.3 and §2.4): a sent message moves from the message
// box into its place, "Thinking" shimmers while ONE works, and a real step from the core rises in as a new line.
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { setLanguage, texts } from "../i18n";
import { setCurrentProject } from "../records/project";
import { App } from "../shell/App";
import { core, reply, running, streamed } from "../shell/testing";
import { ProgressLine } from "./parts/ProgressLine";

vi.mock("../canvas/Canvas", async () => ({ Canvas: (await import("../shell/testing")).CanvasStandIn }));

/** The system's reduced-motion setting, and an `animate` that records what played on which element. */
function motion(reduced = false) {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: reduced && query.includes("reduce"),
    media: query,
    addEventListener() {},
    removeEventListener() {},
  }));
  const played: { el: Element; keyframes: Keyframe[] }[] = [];
  const animate = vi.fn(function (this: Element, keyframes: Keyframe[]) {
    played.push({ el: this, keyframes });
    return { finished: Promise.resolve(), finish() {}, cancel() {} } as unknown as Animation;
  });
  Object.defineProperty(Element.prototype, "animate", { configurable: true, writable: true, value: animate });
  return played;
}

/** Where the message box and each message sit on the screen (jsdom has no layout). */
function layout(box: DOMRect, bubble: DOMRect) {
  vi.spyOn(Element.prototype, "getBoundingClientRect").mockImplementation(function (this: Element) {
    if (this.matches("[data-command-box]")) return box;
    if (this.matches("[data-own]")) return bubble;
    return new DOMRect(0, 0, 0, 0);
  });
}

const box = () => screen.findByRole("textbox", { name: texts.message.ar });
/** The engineer's message by its whole text (its other-script runs sit in their own <bdi>). */
const bubbleOf = async (text: string) =>
  (await screen.findByText((_, el) => el?.tagName === "P" && el.textContent === text)).closest("li")!;

beforeEach(() => {
  setLanguage("ar");
  setCurrentProject(undefined);
});

describe("sending a message", () => {
  it("the sent text moves from the message box into its place in the chat", async () => {
    const played = motion();
    layout(new DOMRect(300, 800, 600, 48), new DOMRect(500, 200, 360, 52));
    core({ routes: { "POST /api/chat": (init) => streamed(reply, init) } });
    const user = userEvent.setup();
    render(<App />);
    await user.type(await box(), "سعّر البند ده{enter}");
    const bubble = await bubbleOf("سعّر البند ده");
    await waitFor(() => expect(played.filter((p) => p.el === bubble)).toHaveLength(1));
    // Arabic text starts at the right: the right edges meet (900 - 860), then the tops (800 - 200)
    expect(played.find((p) => p.el === bubble)!.keyframes[0]!.transform).toBe("translate(40px, 600px)");
  });

  it("RF3: the box's real rect, on the side the text starts, never mirrored", async () => {
    const played = motion();
    layout(new DOMRect(300, 800, 600, 48), new DOMRect(500, 200, 360, 52));
    core({ routes: { "POST /api/chat": (init) => streamed(reply, init) } });
    const user = userEvent.setup();
    render(<App />);
    // an English line on the Arabic page: it starts at the left, so the left edges meet (300 - 500)
    await user.type(await box(), "BOQ 3/01 سعّر{enter}");
    const bubble = await bubbleOf("BOQ 3/01 سعّر");
    await waitFor(() => expect(played.filter((p) => p.el === bubble)).toHaveLength(1));
    expect(played.find((p) => p.el === bubble)!.keyframes[0]!.transform).toBe("translate(-200px, 600px)");
  });

  it("with reduced motion the message is just there", async () => {
    const played = motion(true);
    layout(new DOMRect(300, 800, 600, 48), new DOMRect(500, 200, 360, 52));
    core({ routes: { "POST /api/chat": (init) => streamed(reply, init) } });
    const user = userEvent.setup();
    render(<App />);
    await user.type(await box(), "سعّر البند ده{enter}");
    await bubbleOf("سعّر البند ده");
    expect(played).toHaveLength(0);
  });

  it("earlier messages loaded with the chat do not move", async () => {
    const played = motion();
    const earlier = [{ id: "u1", role: "user", parts: [{ type: "text", text: "سؤال قديم - عينة" }] }];
    core({ routes: { "GET /api/chat/general/messages": () => Response.json({ messages: earlier }) } });
    render(<App />);
    await bubbleOf("سؤال قديم - عينة");
    expect(played).toHaveLength(0);
  });
});

describe("while ONE works", () => {
  const thinking = () => screen.queryByText(texts.thinking.ar);

  it("Thinking shimmers while the Brief runs, and goes when it is done", async () => {
    motion();
    let finish: () => void = () => undefined;
    core({
      routes: {
        "POST /api/chat": (init) =>
          new Promise<Response>((resolve) => {
            finish = () => resolve(streamed([...reply.slice(0, 2), running, { type: "data-status", id: "b1", data: { state: "done", step: null } }, ...reply.slice(6)], init));
          }),
      },
    });
    const user = userEvent.setup();
    render(<App />);
    await user.type(await box(), "سعّر{enter}");
    expect(await screen.findByText(texts.thinking.ar)).toHaveClass("shimmer"); // sent, nothing back yet
    finish();
    await waitFor(() => expect(thinking()).toBeNull());
  });

  it("stays on while a Brief is at work, and stops while it waits for the engineer", async () => {
    motion();
    const waiting = { type: "data-status", id: "b1", data: { state: "waiting_engineer", step: null } };
    let chunks: object[] = [...reply.slice(0, 4), running];
    core({ routes: { "POST /api/chat": (init) => streamed(chunks, init, false) } });
    const user = userEvent.setup();
    const { unmount } = render(<App />);
    await user.type(await box(), "سعّر{enter}");
    await screen.findByText(/مرحبا/);
    expect(screen.getByText(texts.thinking.ar)).toHaveClass("shimmer"); // words come, the Brief still works
    unmount();
    chunks = [...reply.slice(0, 4), running, waiting];
    render(<App />);
    await user.type(await box(), "سعّر{enter}");
    await screen.findByText(/مرحبا/);
    await waitFor(() => expect(thinking()).toBeNull());
  });

  it("with reduced motion Thinking is plain Slate text", async () => {
    motion(true);
    core({ routes: { "POST /api/chat": (init) => streamed([...reply.slice(0, 2), running], init, false) } });
    const user = userEvent.setup();
    render(<App />);
    await user.type(await box(), "سعّر{enter}");
    const line = await screen.findByText(texts.thinking.ar);
    expect(line).not.toHaveClass("shimmer");
    expect(line).toHaveClass("text-slate");
  });
});

describe("a step from the core", () => {
  const lead = { en: "Lead QS", ar: "مهندس الكميات الرئيسي" };
  const step = (text: string) => ({ id: "r1", data: { agent: lead, text: { en: text, ar: text } } });

  it("rises in as a new line when the core reports it, and only then", () => {
    vi.useFakeTimers();
    const played = motion();
    const { rerender } = render(<ProgressLine items={[]} lang="ar" live />);
    vi.advanceTimersByTime(5000);
    expect(screen.queryByRole("list")).toBeNull(); // nothing on a timer
    rerender(<ProgressLine items={[step("بيقرا المقايسة")]} lang="ar" live />);
    expect(played.map((p) => p.el.textContent)).toEqual([`${lead.ar} بيقرا المقايسة`]);
    rerender(<ProgressLine items={[step("بيقرا المقايسة")]} lang="ar" live />);
    expect(played).toHaveLength(1); // the same step again: no new line
    rerender(<ProgressLine items={[step("بيسعّر البنود")]} lang="ar" live />);
    expect(played.map((p) => p.el.textContent)).toEqual([`${lead.ar} بيقرا المقايسة`, `${lead.ar} بيسعّر البنود`]);
    expect(played[1]!.keyframes[0]).toMatchObject({ opacity: 0 });
    vi.useRealTimers();
  });

  it("steps of a finished Brief, read again, do not move", () => {
    const played = motion();
    render(<ProgressLine items={[step("خلص - عينة")]} lang="ar" />);
    expect(played).toHaveLength(0);
  });
});
