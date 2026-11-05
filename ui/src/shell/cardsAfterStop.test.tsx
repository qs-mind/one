// A card no one waits on any more: after Stop it folds at once as withdrawn, with no live button; the Continue line of
// an unfinished Brief shows only in its own chat, compact, and «Leave it» asks the core, so it stays gone.
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { setLanguage, texts } from "../i18n";
import { setCurrentProject } from "../records/project";
import { App } from "./App";
import { calls, core, P1, reply, running, streamed } from "./testing";

vi.mock("../workspace/Workspace", async () => ({ Workspace: (await import("./testing")).WorkspaceStandIn, DocumentHead: () => null }));

const box = () => screen.findByRole("textbox", { name: texts.message.ar });

const card = {
  kind: "outside",
  title: { en: "Send the sample email?", ar: "أبعت الإيميل - عينة؟" },
  detail: { en: "It goes outside ONE.", ar: "ده هيخرج برّه ONE." },
  options: ["yes", "no"],
  status: "pending",
};
const asking = { type: "data-card", id: "c1", data: card };
const waiting = { type: "data-status", id: "b1", data: { state: "waiting_engineer", step: null } };

beforeEach(() => {
  setLanguage("ar");
  setCurrentProject(undefined);
});

describe("after Stop", () => {
  it("the waiting card folds at once as withdrawn, and the chat reads the Brief's end from the core", async () => {
    const stored = [
      { id: "q-b1", role: "user", parts: [{ type: "text", text: "ابعت - عينة" }] },
      {
        id: "m1", // the reply's id, as the stream started it
        role: "assistant",
        parts: [
          { type: "data-card", id: "c1", data: { ...card, status: "withdrawn" } },
          { type: "data-status", id: "b1", data: { state: "stopped", step: null } },
        ],
      },
    ];
    let stoppedYet = false;
    const fetch = core({
      routes: {
        "POST /api/chat": (init) => streamed([...reply.slice(0, 4), running, asking, waiting], init, false),
        "POST /api/briefs/b1/stop": () => {
          stoppedYet = true;
          return Response.json({ state: "stopped" });
        },
        "GET /api/chat/general/messages": () => Response.json({ messages: stoppedYet ? stored : [] }),
      },
    });
    const user = userEvent.setup();
    render(<App />);
    await user.type(await box(), "ابعت - عينة{enter}");
    const shown = (await screen.findByText(card.detail.ar)).closest("section")!;
    expect(within(shown).getByRole("button", { name: texts.allowOnce.ar })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: texts.stop.ar }));
    await waitFor(() => expect(shown).toHaveAttribute("data-answered"));
    expect(within(shown).queryByRole("button", { name: texts.allowOnce.ar })).not.toBeInTheDocument();
    expect(within(shown).getByText(texts.withdrawn.ar)).toBeInTheDocument();
    expect(document.querySelector("[data-waiting]")).toBeNull(); // nothing for the chat to scroll back to
    await waitFor(() => expect(calls(fetch, "GET", "/api/chat/general/messages").length).toBeGreaterThan(1));
  });
});

describe("Continue an unfinished Brief", () => {
  const unfinished = [
    {
      id: "b7",
      chat_id: "p1",
      project_name: P1.name,
      step: { en: "waiting for your answer: Import the BOQ, sheet BOQ?", ar: "مستني ردّك: أستورد المقايسة، شيت BOQ؟" },
      state: "waiting_engineer",
    },
  ];

  it("shows only in the chat whose Brief it is, as one line", async () => {
    core({ routes: { "GET /api/briefs/unfinished": () => Response.json({ briefs: unfinished }) } });
    render(<App />); // the General chat
    await box();
    await new Promise((done) => setTimeout(done, 50));
    expect(document.querySelector("[data-continue-brief]")).toBeNull();
  });

  it("in its own chat: one line with no doubled stop, and Leave tells the core", async () => {
    setCurrentProject(P1);
    const fetch = core({
      routes: {
        "GET /api/briefs/unfinished": () => Response.json({ briefs: unfinished }),
        "POST /api/briefs/b7/leave": () => new Response(null, { status: 204 }),
      },
    });
    const user = userEvent.setup();
    render(<App />);
    const line = await screen.findByText("التكليف ده وقف عند: مستني ردّك: أستورد المقايسة، شيت BOQ؟");
    expect(line.textContent).not.toMatch(/؟\./);
    const row = line.closest("section")!;
    expect(row.querySelectorAll("p")).toHaveLength(1); // compact: the line and its buttons
    await user.click(within(row).getByRole("button", { name: texts.leave.ar }));
    await waitFor(() => expect(calls(fetch, "POST", "/api/briefs/b7/leave")).toHaveLength(1));
    await waitFor(() => expect(document.querySelector("[data-continue-brief]")).toBeNull());
  });
});

// C8: each card keeps its place in time among the reply's words, as the core sends the parts.
describe("a reply's parts", () => {
  it("a card asked before the Lead QS spoke shows before its words, one asked after shows after them", async () => {
    const settled = { ...card, title: { en: "First - sample", ar: "الأول - عينة" }, status: "settled", choice: "yes" };
    const stored = [
      { id: "q-b1", role: "user", parts: [{ type: "text", text: "ابعت - عينة" }] },
      {
        id: "r-b1",
        role: "assistant",
        parts: [
          { type: "data-card", id: "c0", data: settled },
          { type: "text", text: "الكلام بعد الكارت الأول - عينة" },
          asking,
        ],
      },
    ];
    core({ routes: { "GET /api/chat/general/messages": () => Response.json({ messages: stored }) } });
    render(<App />);
    const words = await screen.findByText("الكلام بعد الكارت الأول - عينة");
    const first = screen.getByText("الأول - عينة");
    const second = screen.getByText(card.title.ar);
    expect(first.compareDocumentPosition(words) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(words.compareDocumentPosition(second) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.getByText(`ردّك: ${texts.didAllowOnce.ar}`)).toBeInTheDocument(); // the answer given, in words
  });
});
