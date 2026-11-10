import { act, fireEvent, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { HOLD_MS } from "@/design/HoldButton";
import { DIRS, hasTarget44, renderIn, resetPage, stubBrowser } from "@/design/test/harness";
import { common } from "@/texts/common";
import { conversation } from "@/texts/conversation";
import { tender } from "@/texts/tender";
import { text } from "@/texts/useText";
import { type Decision, DecisionCard, fromFinding, oneAtATime } from "./DecisionCard";
import { findings, paidFinding, planProposed, planWithChange, queued, raised, settled } from "./gallery/samples";
import { PlanCard } from "./PlanCard";

beforeEach(stubBrowser);
afterEach(() => {
  vi.useRealTimers();
  resetPage();
});

const hold = async (button: HTMLElement) => {
  fireEvent.pointerDown(button, { button: 0 });
  await act(() => vi.advanceTimersByTime(HOLD_MS));
  fireEvent.pointerUp(button);
};

describe("fromFinding and oneAtATime", () => {
  it("asks only for raised, queued and settled Findings with two options", () => {
    expect(findings.map((f) => fromFinding(f, "en")?.state ?? null)).toEqual(
      findings.map((f) => ({ open: null, raised: "waiting", queued: "queued", settled: "settled" })[f.status]),
    );
  });

  it("keeps one decision waiting and queues the next behind it", () => {
    const first = fromFinding(raised, "en")!;
    const second: Decision = { ...first, id: "other" };
    expect(oneAtATime([first, second]).map((d) => d.state)).toEqual(["waiting", "queued"]);
  });
});

describe.each(DIRS)("DecisionCard (%s)", (dir) => {
  const lang = dir === "rtl" ? "ar" : "en";

  it("offers exactly the two options, the first the dark button", async () => {
    const choose = vi.fn();
    renderIn(dir, <DecisionCard decision={fromFinding(raised, lang)!} asker="Lead QS" onChoose={choose} />);
    expect(screen.getByText(text(conversation.needsYou, lang, { name: "Lead QS" }))).toBeInTheDocument();
    expect(screen.getByText(raised.opinion!)).toBeInTheDocument();
    const [first, second] = [raised.options![0][lang], raised.options![1][lang]].map((name) => screen.getByRole("button", { name }));
    expect(first!.className).toMatch(/bg-primary/);
    expect(second!.className).toMatch(/border-line/);
    expect([first, second].every((b) => hasTarget44(b!))).toBe(true);
    await userEvent.click(second!);
    expect(choose).toHaveBeenCalledWith(1);
  });

  it("holds an option that spends money: one click does nothing, a full hold chooses it", async () => {
    vi.useFakeTimers();
    const choose = vi.fn();
    const decision = { ...fromFinding(paidFinding, lang)!, hold: { why: "paid" as const, options: [0 as const] } };
    renderIn(dir, <DecisionCard decision={decision} asker="Lead QS" onChoose={choose} />);
    const paid = screen.getByRole("button", { name: paidFinding.options![0][lang] });
    fireEvent.click(paid, { detail: 1 });
    expect(choose).not.toHaveBeenCalled();
    expect(paid).toHaveAccessibleDescription(new RegExp(text(common.holdHelpReader, lang)));
    await hold(paid);
    expect(choose).toHaveBeenCalledWith(0);
  });

  it("is one line while another waits, and shows the answer once settled", () => {
    const { container } = renderIn(
      dir,
      <>
        <DecisionCard decision={fromFinding(queued, lang)!} asker="Lead QS" onChoose={() => {}} />
        <DecisionCard decision={fromFinding(settled, lang)!} asker="Lead QS" onChoose={() => {}} />
      </>,
    );
    expect(screen.getByText(text(conversation.queued, lang, { title: queued.title[lang] }))).toBeInTheDocument();
    expect(screen.getByText(text(conversation.chose, lang, { option: settled.options![settled.chosen!][lang] }))).toBeInTheDocument();
    expect(container.querySelectorAll("button")).toHaveLength(0);
  });
});

describe.each(DIRS)("PlanCard (%s)", (dir) => {
  const lang = dir === "rtl" ? "ar" : "en";
  const handlers = () => ({ onApprove: vi.fn(), onDiscuss: vi.fn(), onChange: vi.fn() });

  it("shows the stages bar, days, cost and time; Approve is a hold, Discuss a click", async () => {
    vi.useFakeTimers();
    const h = handlers();
    renderIn(dir, <PlanCard plan={planProposed} version={1} {...h} />);
    expect(screen.getByRole("img", { name: text(conversation.stageBarNone, lang) })).toBeInTheDocument();
    expect(screen.getByText(text(conversation.cost, lang, { cost: "2.40 USD" }), { exact: false })).toBeInTheDocument();
    const approve = screen.getByRole("button", { name: text(conversation.approve, lang) });
    fireEvent.click(approve, { detail: 1 });
    expect(h.onApprove).not.toHaveBeenCalled();
    await hold(approve);
    expect(h.onApprove).toHaveBeenCalledWith(1);
    fireEvent.click(screen.getByRole("button", { name: text(conversation.discuss, lang) }));
    expect(h.onDiscuss).toHaveBeenCalledTimes(1);
  });

  it("an approved plan with a Suggested change shows its reason and both answers", async () => {
    vi.useFakeTimers();
    const h = handlers();
    renderIn(dir, <PlanCard plan={planWithChange} version={planWithChange.version} {...h} />);
    const stage = planWithChange.stages[3]!.title[lang];
    expect(screen.getByRole("img", { name: text(conversation.stageBar, lang, { step: 4, total: 6, name: stage }) })).toBeInTheDocument();
    expect(screen.getByText(planWithChange.change!.reason)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: text(conversation.approve, lang) })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: text(conversation.rejectChange, lang) }));
    expect(h.onChange).toHaveBeenCalledWith(planWithChange.change!.id, false);
    const accept = screen.getByRole("button", { name: text(conversation.acceptChange, lang) });
    if (planWithChange.change!.paid) await hold(accept);
    else fireEvent.click(accept);
    expect(h.onChange).toHaveBeenCalledWith(planWithChange.change!.id, true);
  });

  it("shows where each submission date was read, opening it, and marks an unsure OCR read", async () => {
    const onOpenSource = vi.fn();
    renderIn(dir, <PlanCard plan={planWithChange} version={planWithChange.version} {...handlers()} onOpenSource={onOpenSource} />);
    // The plan's own date under its facts, then the change's before and after.
    const [, now, after] = [...document.querySelectorAll<HTMLElement>("[data-date-source]")];
    expect(now).toHaveTextContent(planWithChange.submission_source!.title);
    expect(after).toHaveTextContent(planWithChange.change!.submission_source!.title);
    expect(after).toHaveTextContent(text(tender.submissionUnsure, lang));
    expect(now).not.toHaveTextContent(text(tender.submissionUnsure, lang));
    await userEvent.click(after!.querySelector("button")!);
    expect(onOpenSource).toHaveBeenCalledWith(planWithChange.change!.submission_source);
  });

  it("shows no date source when the core gives none", () => {
    renderIn(dir, <PlanCard plan={{ ...planProposed, submission_source: null }} version={1} {...handlers()} />);
    expect(document.querySelector("[data-date-source]")).toBeNull();
  });

  it("a part that names an older version is one line; no plan yet draws nothing", () => {
    const { container, unmount } = renderIn(dir, <PlanCard plan={{ ...planProposed, version: 2 }} version={1} {...handlers()} />);
    expect(container).toHaveTextContent(text(conversation.replaced, lang, { n: 2 }));
    expect(container.querySelector("button")).toBeNull();
    unmount();
    const empty = renderIn(dir, <PlanCard plan={null} version={1} {...handlers()} />);
    expect(empty.container.querySelector("[data-plan]")).toBeNull();
  });
});
