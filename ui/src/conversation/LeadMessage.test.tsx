import { act, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AppProviders } from "@/design/AppProviders";
import { DIRS, hasTarget44, renderIn, resetPage, stubBrowser } from "@/design/test/harness";
import { conversation } from "@/texts/conversation";
import { conversationGallery as g } from "@/texts/design/conversation";
import { text } from "@/texts/useText";
import { raised } from "./gallery/samples";
import { LeadMessage } from "./LeadMessage";
import { LiveLine } from "./LiveLine";

beforeEach(stubBrowser);
afterEach(resetPage);

describe.each(DIRS)("LeadMessage (%s)", (dir) => {
  const lang = dir === "rtl" ? "ar" : "en";
  const reply = text(g.leadRead, lang);
  const lines = reply.split("\n");

  it("shows the first four lines and keeps the rest under Details", async () => {
    renderIn(dir, <LeadMessage name="Lead QS" text={reply} />);
    expect(screen.getByText("Lead QS")).toBeInTheDocument();
    expect(screen.getByText(lines[0]!, { exact: false })).toBeInTheDocument();
    expect(screen.queryByText(lines[5]!, { exact: false })).not.toBeInTheDocument();
    const details = screen.getByRole("button", { name: text(conversation.details, lang) });
    expect(hasTarget44(details)).toBe(true);
    await userEvent.click(details);
    expect(screen.getByText(lines[5]!, { exact: false })).toBeInTheDocument();
  });

  it("draws the reply in its own direction, never auto", () => {
    const { container } = renderIn(dir, <LeadMessage name="Lead QS" text={reply} />);
    expect(container.querySelector('[dir="auto"]')).toBeNull();
    expect(container.querySelector(`[dir="${lang === "ar" ? "rtl" : "ltr"}"]`)).not.toBeNull();
  });

  it("has no Details for a short reply, and opens a source when its link is pressed", async () => {
    const open = vi.fn();
    renderIn(dir, <LeadMessage name="Lead QS" text={text(g.leadShort, lang)} sources={raised.sources} onOpenSource={open} />);
    expect(screen.queryByRole("button", { name: text(conversation.details, lang) })).not.toBeInTheDocument();
    const label = text(conversation.sourceItem, lang, { title: raised.sources[0]!.title, item: "7/03" });
    await userEvent.click(screen.getByRole("button", { name: label }));
    expect(open).toHaveBeenCalledWith(raised.sources[0]);
  });
});

describe.each(DIRS)("LiveLine (%s)", (dir) => {
  const lang = dir === "rtl" ? "ar" : "en";
  const progress = { agent: g.agent, text: g.reading };
  const log = [
    { agent: g.leadAgent, text: g.stepFiles, done: true },
    { agent: g.agent, text: g.stepConditions, done: false },
  ];

  it("is one line of who and what, and nothing when no work runs", () => {
    const { container, rerender } = renderIn(dir, <LiveLine progress={progress} log={log} />);
    const line = screen.getByRole("button");
    expect(line).toHaveTextContent(text(g.agent, lang));
    expect(line).toHaveTextContent(text(g.reading, lang));
    rerender(<AppProviders><LiveLine progress={null} /></AppProviders>);
    expect(container.querySelector("button")).toBeNull();
  });

  it("tells a screen reader only when the worker changes", () => {
    const { rerender } = renderIn(dir, <LiveLine progress={progress} />);
    const status = screen.getByRole("status");
    const first = status.textContent;
    expect(first).toContain(text(g.agent, lang));
    act(() => rerender(<AppProviders><LiveLine progress={{ ...progress, text: g.readingLater }} /></AppProviders>));
    expect(screen.getByRole("status").textContent).toBe(first);
    act(() => rerender(<AppProviders><LiveLine progress={{ agent: g.leadAgent, text: g.stepPlan }} /></AppProviders>));
    expect(screen.getByRole("status").textContent).toContain(text(g.leadAgent, lang));
  });

  it("opens the work log, each worker's steps under its name", async () => {
    renderIn(dir, <LiveLine progress={progress} log={log} />);
    await userEvent.click(screen.getByRole("button"));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(text(conversation.workLog, lang))).toBeInTheDocument();
    expect(within(dialog).getByText(text(g.stepFiles, lang))).toBeInTheDocument();
    expect(within(dialog).getByLabelText(text(conversation.stepRunning, lang))).toBeInTheDocument();
  });
});
