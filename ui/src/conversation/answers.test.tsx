// What the engineer answers in the thread (contract 3.1, 3.2): the cards a running Brief waits on, a stage's
// sign-off block, work cut off; and what the thread says when work failed or a message got no answer.
import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { server, startFakeCore } from "@/api/fakeCore";
import { HOLD_MS } from "@/design/HoldButton";
import { DIRS, renderIn, resetPage, stubBrowser } from "@/design/test/harness";
import { cardOption, cards } from "@/texts/cards";
import { conversation } from "@/texts/conversation";
import { text } from "@/texts/useText";
import { planWithChange } from "./gallery/samples";
import type { CardData, TenderPlan, ThreadMessage } from "./parts";
import { Thread, type ThreadProps } from "./Thread";

startFakeCore();
let answered: { id: string; body: unknown }[];
beforeEach(() => {
  stubBrowser();
  answered = [];
  server.use(
    http.post("*/api/cards/:id", async ({ params, request }) => {
      answered.push({ id: String(params.id), body: await request.json() });
      return new HttpResponse(null, { status: 204 });
    }),
  );
});
afterEach(() => {
  vi.useRealTimers();
  resetPage();
});

globalThis.ResizeObserver ??= class {
  observe() {}
  unobserve() {}
  disconnect() {}
} as unknown as typeof ResizeObserver;

const hold = async (button: HTMLElement) => {
  fireEvent.pointerDown(button, { button: 0 });
  await act(() => vi.advanceTimersByTime(HOLD_MS));
  fireEvent.pointerUp(button);
};

const props = (over: Partial<ThreadProps> = {}): ThreadProps => ({
  messages: [],
  leadName: "Lead QS",
  plan: null,
  findings: [],
  onApprovePlan: vi.fn(),
  onDiscussPlan: vi.fn(),
  onPlanChange: vi.fn(),
  onDecide: vi.fn(),
  ...over,
});

const pair = (en: string) => ({ en, ar: `${en} - عينة` });
const dateCard: CardData = {
  kind: "question",
  title: pair("Lead QS asks (sample)"),
  detail: pair("The documents give no submission date (sample)"),
  options: ["sent", "no"],
  payload: { questions: [{ id: "submission_date", text: "Submission date (sample)", kind: "date" } as never] },
};
const capCard: CardData = {
  kind: "cap",
  title: pair("Spending Cap (sample)"),
  detail: pair("This work reached 80% of its cap (sample)"),
  options: ["continue", "raise", "report"],
  hold: { why: "paid", options: ["continue"] },
};
const reply = (parts: ThreadMessage["parts"], state = "waiting_engineer"): ThreadMessage => ({
  id: "b9-reply",
  role: "assistant",
  parts: [...parts, { type: "data-status", id: "b9", data: { state: state as never, step: pair("Pricing the concrete (sample)") } }],
});

/** P2's plan with its fourth stage ended, asking for sign-off. */
const ended: TenderPlan = {
  ...planWithChange,
  change: null,
  stages: planWithChange.stages.map((s, i) => (i === 3 ? { ...s, status: "waiting_engineer" } : s)),
};
const stage = ended.stages[3]!;

describe.each(DIRS)("answering in the thread (%s)", (dir) => {
  const lang = dir === "rtl" ? "ar" : "en";

  it("draws a question card and sends its typed answer to the card", async () => {
    const parts = [{ type: "data-card", id: "c1", data: dateCard }] as ThreadMessage["parts"];
    const { container } = renderIn(dir, <Thread {...props({ messages: [reply(parts)] })} />);
    expect(container.querySelector('[data-card="c1"]')).not.toBeNull();
    const send = screen.getByRole("button", { name: text(cardOption.send, lang) });
    expect(send).toBeDisabled();
    fireEvent.change(container.querySelector('input[type="date"]')!, { target: { value: "2026-11-20" } });
    await userEvent.click(send);
    await waitFor(() => expect(answered).toEqual([{ id: "c1", body: { choice: "sent", answers: { submission_date: "2026-11-20" } } }]));
    expect(await screen.findByText(text(cards.answered, lang, { choice: "2026-11-20" }))).toBeInTheDocument();
  });

  it("holds a paid answer: one click sends nothing, a hold does; the next card waits behind it", async () => {
    const parts = [
      { type: "data-card", id: "c2", data: capCard },
      { type: "data-card", id: "c3", data: { ...capCard, title: pair("Second card (sample)") } },
    ] as ThreadMessage["parts"];
    const { container } = renderIn(dir, <Thread {...props({ messages: [reply(parts)] })} />);
    expect(container.querySelector('[data-card="c3"]')).toBeNull();
    expect(screen.getByText(text(conversation.queued, lang, { title: pair("Second card (sample)")[lang] }))).toBeInTheDocument();
    const go = screen.getByRole("button", { name: text(cardOption.capContinue, lang) });
    fireEvent.click(go);
    expect(answered).toEqual([]);
    fireEvent.click(go); // the second activation of a hold: a screen reader's way to hold
    await waitFor(() => expect(answered).toEqual([{ id: "c2", body: { choice: "continue" } }]));
    await waitFor(() => expect(container.querySelector('[data-card="c3"]')).not.toBeNull());
  });

  it("draws a stage's sign-off block: a hold signs off the version on screen, notes turn to the box", async () => {
    const signOff = vi.fn();
    const notes = vi.fn();
    const parts = [{ type: "data-stage", id: stage.id, data: { stage_id: stage.id } }] as ThreadMessage["parts"];
    const { container } = renderIn(
      dir,
      <Thread {...props({ messages: [reply(parts, "done")], plan: ended, onSignOff: signOff, onNotes: notes })} />,
    );
    expect(container.querySelector(`[data-signoff="${stage.id}"]`)).not.toBeNull();
    expect(screen.getByText(text(stage.gate, lang))).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: text(cards.notes, lang) }));
    expect(notes).toHaveBeenCalled();
    vi.useFakeTimers();
    const sign = screen.getByRole("button", { name: text(cards.signOff, lang) });
    fireEvent.click(sign);
    expect(signOff).not.toHaveBeenCalled();
    await hold(sign);
    expect(signOff).toHaveBeenCalledWith(stage.id, ended.version);
  });

  it("draws a stage that waits with no part, and work cut off, at the end of the thread", async () => {
    const go = vi.fn();
    const leave = vi.fn();
    const { container } = renderIn(
      dir,
      <Thread {...props({ plan: ended, unfinished: ["b7"], onContinue: go, onLeave: leave })} />,
    );
    expect(container.querySelector(`[data-part="${stage.id}"] [data-signoff]`)).not.toBeNull();
    expect(container.querySelector('[data-part="b7"] [data-unfinished="b7"]')).not.toBeNull();
    await userEvent.click(screen.getByRole("button", { name: text(cards.continue, lang) }));
    await userEvent.click(screen.getByRole("button", { name: text(cards.leave, lang) }));
    expect(go).toHaveBeenCalledWith("b7");
    expect(leave).toHaveBeenCalledWith("b7");
  });

  it("says where failed work stopped, and why a message got no answer", () => {
    renderIn(dir, <Thread {...props({ messages: [reply([], "failed")], error: "The provider refused the key (sample)" })} />);
    expect(screen.getByText(`${text(cards.workFailed, lang)}: ${pair("Pricing the concrete (sample)")[lang]}`)).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("The provider refused the key (sample)");
  });

  it("builds the work log from the running reply's steps and the team's messages", async () => {
    const parts = [
      { type: "data-progress", id: "r1", data: { agent: pair("Lead QS"), text: pair("Read the BOQ (sample)") } },
      {
        type: "data-room",
        id: "m1",
        data: { id: "m1", from_id: "lead-qs", to_id: "team", text: "Start with the concrete (sample)", sources: [], at: "2026-11-10T08:00:00Z", raised: null },
      },
      { type: "data-progress", id: "r2", data: { agent: pair("Cost QS"), text: pair("Pricing (sample)") } },
    ] as ThreadMessage["parts"];
    const name = (id: string) => (id === "lead-qs" ? pair("Lead QS") : undefined);
    renderIn(dir, <Thread {...props({ messages: [reply(parts, "running")], memberName: name })} />);
    await userEvent.click(screen.getByRole("button", { name: new RegExp(pair("Pricing (sample)")[lang].replace(/[()]/g, ".")) }));
    expect(await screen.findByText(pair("Read the BOQ (sample)")[lang])).toBeInTheDocument();
    expect(screen.getByText("Start with the concrete (sample)")).toBeInTheDocument();
    expect(screen.getByText(text(cards.roomTo, lang, { name: text(cards.team, lang) }))).toBeInTheDocument();
    expect(screen.queryByText(text(conversation.logEmpty, lang))).not.toBeInTheDocument();
  });
});
