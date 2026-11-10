import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DIRS, renderIn, resetPage, stubBrowser } from "@/design/test/harness";
import { conversation } from "@/texts/conversation";
import { conversationGallery as g } from "@/texts/design/conversation";
import { text } from "@/texts/useText";
import { findings, planProposed, planWithChange, raised, sampleThread } from "./gallery/samples";
import type { ThreadMessage } from "./parts";
import { Thread, type ThreadProps } from "./Thread";

beforeEach(stubBrowser);
afterEach(resetPage);

// jsdom has no ResizeObserver; use-stick-to-bottom watches the content's size with one.
globalThis.ResizeObserver ??= class {
  observe() {}
  unobserve() {}
  disconnect() {}
} as unknown as typeof ResizeObserver;

function props(over: Partial<ThreadProps> = {}): ThreadProps {
  return {
    messages: [],
    leadName: "Lead QS",
    plan: null,
    findings: [],
    onApprovePlan: vi.fn(),
    onDiscussPlan: vi.fn(),
    onPlanChange: vi.fn(),
    onDecide: vi.fn(),
    ...over,
  };
}

describe.each(DIRS)("Thread (%s)", (dir) => {
  const lang = dir === "rtl" ? "ar" : "en";

  it("says it is empty, inviting a message or a folder", () => {
    renderIn(dir, <Thread {...props()} />);
    expect(screen.getByText(text(conversation.emptyBody, lang))).toBeInTheDocument();
  });

  it("draws the engineer, the Lead and what each reply placed, in order, then the live line", async () => {
    const decide = vi.fn();
    const { container } = renderIn(
      dir,
      <Thread {...props({ messages: sampleThread(lang), plan: planProposed, findings, onDecide: decide })} />,
    );
    const log = screen.getByRole("log", { name: text(conversation.threadLabel, lang) });
    // ONE's own question is not the engineer's bubble.
    expect(within(log).getByText(text(conversation.byOne, lang))).toBeInTheDocument();
    expect(container.querySelectorAll('[data-from="user"]')).toHaveLength(2); // the question and the steer
    expect(container.querySelector(`[data-plan="${planProposed.id}"]`)).not.toBeNull();
    expect(container.querySelector(`[data-decision="${raised.id}"]`)).not.toBeNull();
    const order = [...container.querySelectorAll("[data-decision], [data-plan], [data-from]")].map(
      (el) => el.getAttribute("data-decision") ?? el.getAttribute("data-plan") ?? el.getAttribute("data-from"),
    );
    expect(order.slice(0, 5)).toEqual(["assistant", raised.id, "user", "assistant", planProposed.id]);
    const reading = text(g.reading, lang);
    expect(screen.getAllByRole("button").some((b) => b.textContent?.includes(reading))).toBe(true);
    await userEvent.click(screen.getByRole("button", { name: raised.options![0][lang] }));
    expect(decide).toHaveBeenCalledWith(raised.id, 0);
  });

  it("makes only the last copy of a part live; an earlier one is a line", () => {
    const thread = sampleThread(lang);
    const again: ThreadMessage = {
      id: "b3-reply",
      role: "assistant",
      parts: [{ type: "data-plan", id: planProposed.id, data: { plan_id: planProposed.id, version: 1 } }],
    };
    const { container } = renderIn(dir, <Thread {...props({ messages: [...thread, again], plan: planProposed })} />);
    expect(container.querySelectorAll("[data-plan]")).toHaveLength(1);
    expect(screen.getByText(text(conversation.laterPart, lang))).toBeInTheDocument();
  });

  it("draws what waits with no part in the thread at its end, from the state alone", () => {
    const { container } = renderIn(dir, <Thread {...props({ plan: planWithChange, findings })} />);
    expect(container.querySelector(`[data-change="${planWithChange.change!.id}"]`)).not.toBeNull();
    expect(container.querySelector(`[data-decision="${raised.id}"]`)).not.toBeNull();
    expect(screen.queryByText(text(conversation.emptyBody, lang))).not.toBeInTheDocument();
  });
});
