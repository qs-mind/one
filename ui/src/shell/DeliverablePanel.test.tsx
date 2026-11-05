// A Deliverable grows from its card in the chat into the review board, and closes back to the same card
// (docs/specs/2026-11-05-motion-design.md, §2.5): a clip-path reveal, 300 ms; a fade when the card is gone.
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { D, entry, sheet } from "../deliverables/fixtures";
import { setLanguage, texts } from "../i18n";
import { setCurrentProject } from "../records/project";
import { App } from "./App";
import { core, P1, reply, streamed } from "./testing";

vi.mock("../canvas/Canvas", async () => ({ Canvas: (await import("./testing")).CanvasStandIn }));

/** The system's reduced-motion setting, and an `animate` that records what played on which element. */
function motion(reduced = false) {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: reduced && query.includes("reduce"),
    media: query,
    addEventListener() {},
    removeEventListener() {},
  }));
  const played: { el: Element; keyframes: Keyframe[]; ms: number }[] = [];
  const animate = vi.fn(function (this: Element, keyframes: Keyframe[], options: KeyframeAnimationOptions) {
    played.push({ el: this, keyframes, ms: Number(options.duration) });
    return { finished: Promise.resolve(), finish() {}, cancel() {} } as unknown as Animation;
  });
  Object.defineProperty(Element.prototype, "animate", { configurable: true, writable: true, value: animate });
  return played;
}

// jsdom's window is 1024 × 768. The board takes the inline end; the card sits under it, in the chat.
const PANEL = new DOMRect(400, 40, 624, 728);
const CARD = new DOMRect(640, 300, 360, 120);
const FROM_CARD = "inset(260px 24px 348px 240px round 14px)";
const WHOLE = "inset(0px 0px 0px 0px round 0px)";

function layout(card = { rect: CARD }) {
  vi.spyOn(Element.prototype, "getBoundingClientRect").mockImplementation(function (this: Element) {
    if (this.matches("[data-deliverable-panel]")) return PANEL;
    if (this.matches("[data-deliverable-card]")) return card.rect;
    return new DOMRect(0, 0, 0, 0);
  });
}

const d = `/api/projects/p1/deliverables/${D}`;
function aCore() {
  const parts = [reply[0]!, { type: "data-deliverable", id: D, data: { id: D } }, ...reply.slice(1)];
  core({
    routes: {
      "POST /api/chat": (init) => streamed(parts, init),
      "GET /api/projects/p1/deliverables": () => Response.json({ deliverables: [entry()] }),
      [`GET ${d}`]: () => Response.json(sheet()),
      [`GET ${d}/changes?status=pending`]: () => Response.json({ changes: [] }),
      [`GET ${d}/changes?status=stale`]: () => Response.json({ changes: [] }),
      [`GET ${d}/comments`]: () => Response.json({ comments: [] }),
    },
  });
}

/** Sends a message whose reply has the Deliverable's card, and opens it from the card. */
async function openFromCard() {
  const user = userEvent.setup();
  render(<App />);
  await user.type(await screen.findByRole("textbox", { name: texts.message.ar }), "اعمل المقايسة{enter}");
  const card = await screen.findByRole("article", { name: "جدول الكميات - عينة" });
  const open = within(card).getByRole("button", { name: new RegExp(texts.deliverableOpen.ar) });
  await user.click(open);
  await screen.findByText("03/02");
  return { user, open, panel: () => document.querySelector("[data-deliverable-panel]") };
}

beforeEach(() => {
  setLanguage("ar");
  setCurrentProject(P1);
});

describe("a Deliverable opening from its card", () => {
  it("grows from the card's place to the whole board", async () => {
    const played = motion();
    layout();
    aCore();
    const { panel } = await openFromCard();
    const reveal = played.filter((p) => p.el === panel());
    expect(reveal).toHaveLength(1);
    expect(reveal[0]!.keyframes[0]!.clipPath).toBe(FROM_CARD);
    expect(reveal[0]!.keyframes.at(-1)!.clipPath).toBe(WHOLE);
    expect(reveal[0]!.ms).toBe(300);
  });

  it("Escape closes it back to the card, and focus returns to the card", async () => {
    const played = motion();
    layout();
    aCore();
    const { user, open, panel } = await openFromCard();
    const board = panel();
    await user.keyboard("{Escape}");
    await waitFor(() => expect(panel()).toBeNull());
    const back = played.filter((p) => p.el === board).at(-1)!;
    expect(back.keyframes[0]!.clipPath).toBe(WHOLE);
    expect(back.keyframes.at(-1)!.clipPath).toBe(FROM_CARD);
    await waitFor(() => expect(open).toHaveFocus());
  });

  it("closes with a fade when its card is no longer on screen", async () => {
    const played = motion();
    const card = { rect: CARD };
    layout(card);
    aCore();
    const { user, panel } = await openFromCard();
    const board = panel();
    card.rect = new DOMRect(640, -400, 360, 120); // the chat scrolled on
    await user.click(screen.getByRole("button", { name: texts.close.ar }));
    await waitFor(() => expect(panel()).toBeNull());
    const back = played.filter((p) => p.el === board).at(-1)!;
    expect(back.keyframes).toEqual([{ opacity: 1 }, { opacity: 0 }]);
  });

  it("full screen has one way out, and its tabs show counts as chips after a space", async () => {
    motion(true);
    layout();
    core({
      routes: {
        "POST /api/chat": (init) => streamed([reply[0]!, { type: "data-deliverable", id: D, data: { id: D } }, ...reply.slice(1)], init),
        "GET /api/projects/p1/deliverables": () => Response.json({ deliverables: [entry()] }),
        [`GET ${d}`]: () => Response.json(sheet({ open_comments: 1 })),
        [`GET ${d}/changes?status=pending`]: () => Response.json({ changes: [] }),
        [`GET ${d}/changes?status=stale`]: () => Response.json({ changes: [] }),
        [`GET ${d}/comments`]: () => Response.json({ comments: [] }),
      },
    });
    const { user, panel } = await openFromCard();
    expect(screen.getByRole("button", { name: texts.close.ar })).toBeInTheDocument();
    // beside the canvas it says Full screen (never Leave full screen while it is not)
    expect(screen.queryByRole("button", { name: texts.sheetLeaveFullScreen.ar })).toBeNull();
    await user.click(screen.getByRole("button", { name: texts.sheetFullScreen.ar }));
    // one exit: Close; no Leave full screen stacked under it
    expect(screen.queryByRole("button", { name: texts.sheetLeaveFullScreen.ar })).toBeNull();
    expect(screen.queryByRole("button", { name: texts.sheetFullScreen.ar })).toBeNull();
    const leave = screen.getByRole("button", { name: texts.close.ar });
    const tab = screen.getByRole("tab", { name: new RegExp(`^${texts.reviewComments.ar}`) });
    expect(tab.textContent).toBe(`${texts.reviewComments.ar} 1`);
    expect(tab.querySelector("[data-count]")).toHaveTextContent(/^1$/);
    await user.keyboard("{Escape}"); // Esc still closes it
    await waitFor(() => expect(panel()).toBeNull());
    expect(leave).not.toBeInTheDocument();
  });

  it("with reduced motion it opens and closes at once", async () => {
    const played = motion(true);
    layout();
    aCore();
    const { user, open, panel } = await openFromCard();
    await user.keyboard("{Escape}");
    await waitFor(() => expect(panel()).toBeNull());
    expect(played).toHaveLength(0);
    await waitFor(() => expect(open).toHaveFocus());
  });
});
