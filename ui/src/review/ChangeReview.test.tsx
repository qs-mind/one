// The BOQ change review on the review board: accept or reject each change or all of them, Undo after an accept,
// the new value in Copper over the old one struck in Slate, the rows with no change dimmed while reviewing, each
// change's reason and source, and J/K (or the arrows) with A and R. With fetch mocked: no core, no network.
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DeliverableViewer } from "../deliverables/DeliverableViewer";
import { base, bodies, change, core, D, fakeLive, json, sheet, viewRoutes } from "../deliverables/fixtures";
import type { Change } from "../deliverables/types";
import { setLanguage, texts } from "../i18n";
import { DUR, EASE } from "../ui/motion";

Element.prototype.scrollIntoView ??= () => {};

const d = `${base}/deliverables/${D}`;
const accept = `${d}/changes/accept`;
const reject = `${d}/changes/reject`;

// c1: the rate of 03/02 (an agent's, with a source and a reason); c2: the description of 03/01 (the engineer's)
const sourced = change("c1", {
  author: "Estimator",
  reason: "عرض سعر أحدث - عينة",
  op: { op: "set_number", row: "p3", name: "rate", value: "40000", unit: "m3", currency: "EGP", source_id: "s9", expect: "r-p3" },
  after: { value: "40000", unit: "m3", currency: "EGP", number_id: null, source: "s9", dated: "2026-11-04" },
  sources: { s9: { kind: "sample", title: "عرض مورد الخرسانة - عينة", file_name: null, locator: {}, url: null, dated: "2026-11-04" } },
});
const typed = change("c2", {
  op: { op: "set_field", row: "p2", key: "description", value: "خرسانة عادية - عينة معدلة", expect: 1 },
  before: { text: "خرسانة عادية تحت الأساسات - عينة" },
  after: { text: "خرسانة عادية - عينة معدلة" },
  follows: [],
});

function motion(reduced: boolean) {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: reduced && query.includes("reduce"),
    media: query,
    addEventListener() {},
    removeEventListener() {},
  }));
  const animation = { pause: vi.fn(), play: vi.fn(), cancel: vi.fn(), finish: vi.fn(), finished: Promise.resolve() };
  const animate = vi.fn(() => animation as unknown as Animation);
  Object.defineProperty(Element.prototype, "animate", { configurable: true, writable: true, value: animate });
  return animate;
}

function board(pending: Change[] = [sourced, typed], more: Record<string, (url: string, init: RequestInit) => Response> = {}) {
  const fetch = core({ ...viewRoutes(sheet({ pending: pending.length }), { pending }), ...more });
  const live = fakeLive();
  render(<DeliverableViewer projectId="p1" deliverableId={D} mode="full" subscribe={live.subscribe} />);
  return fetch;
}

const panel = () => screen.getByRole("tabpanel");
const changeItems = () => within(panel()).getAllByRole("option");
const rowOf = (code: string) => screen.getAllByRole("row").find((r) => within(r).queryByText(code))!;

beforeEach(() => {
  setLanguage("ar");
  motion(false);
});
afterEach(() => vi.useRealTimers());

describe("BOQ change review", () => {
  it("a changed cell shows the new value in Copper over the old one struck through in Slate", async () => {
    board();
    await screen.findByText("03/02");
    const rate = within(rowOf("03/02")).getByText("40,000.00").closest("ins")!;
    expect(rate).toHaveClass("text-copper");
    const old = within(rowOf("03/02")).getByText("39,850.50").closest("del")!;
    expect(old).toHaveClass("text-slate");
    // new over old: the new value comes first
    expect(rate.compareDocumentPosition(old) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    // the panel shows it the same way
    const first = changeItems()[0]!;
    expect(within(first).getByText("40,000.00").closest("ins")).toHaveClass("text-copper");
    expect(within(first).getByText("39,850.50").closest("del")).toHaveClass("text-slate");
  });

  it("each change shows its reason and its source; the source opens its card", async () => {
    const user = userEvent.setup();
    board();
    await screen.findByText("03/02");
    const [first, second] = changeItems();
    expect(within(first!).getByText("عرض سعر أحدث - عينة")).toBeInTheDocument();
    const chip = within(first!).getByRole("button", { name: new RegExp("عرض مورد الخرسانة - عينة") });
    await user.click(chip);
    expect(await screen.findByRole("dialog", { name: texts.sheetSource.ar })).toHaveTextContent("عرض مورد الخرسانة - عينة");
    // the engineer's own text change has no number, so no source
    expect(within(second!).queryByRole("button", { name: new RegExp(texts.sheetSource.ar) })).toBeNull();
  });

  it("rows with no change dim while reviewing, and only then", async () => {
    const user = userEvent.setup();
    board();
    await screen.findByText("03/02");
    expect(rowOf("03/04")).toHaveClass("review-dim"); // unchanged
    expect(rowOf("03/02")).not.toHaveClass("review-dim");
    expect(rowOf("03/01")).not.toHaveClass("review-dim");
    await user.click(screen.getByRole("tab", { name: texts.reviewComments.ar }));
    expect(rowOf("03/04")).not.toHaveClass("review-dim");
  });

  it("nothing dims with no pending change, or in a frame", async () => {
    board([]);
    await screen.findByText("03/02");
    expect(rowOf("03/04")).not.toHaveClass("review-dim");
  });

  it("accepts one change, shows «اتقبل · تراجع», and Undo takes it back to the version before", async () => {
    const user = userEvent.setup();
    const fetch = board([sourced, typed], {
      [`POST ${accept}`]: () => json({ version: 4, accepted: ["c1"], stale: [], undo: "tok", window_ms: 6000 }),
      "POST /api/undo/tok": () => new Response(null, { status: 204 }),
    });
    await screen.findByText("03/02");
    await user.click(within(changeItems()[0]!).getByRole("button", { name: texts.sheetAccept.ar }));
    expect(bodies(fetch, "POST", accept)).toEqual([{ ids: ["c1"] }]);
    const notice = await screen.findByText(texts.reviewAcceptedShort.ar);
    const views = () => fetch.mock.calls.filter(([u, i]) => String(u).split("?")[0] === d && (i?.method ?? "GET") === "GET").length;
    const before = views();
    await user.click(within(notice.closest('[role="status"]') as HTMLElement).getByRole("button", { name: texts.undo.ar }));
    expect(fetch.mock.calls.some(([u, i]) => String(u) === "/api/undo/tok" && i?.method === "POST")).toBe(true);
    await waitFor(() => expect(views()).toBeGreaterThan(before)); // the view is loaded again: the version before
    await waitFor(() => expect(screen.queryByText(texts.reviewAcceptedShort.ar)).toBeNull());
  });

  it("rejects one change, and accepts or rejects all of them", async () => {
    const user = userEvent.setup();
    const fetch = board([sourced, typed], {
      [`POST ${accept}`]: () => json({ version: 4, accepted: ["c1", "c2"], stale: [], undo: "tok", window_ms: 6000 }),
      [`POST ${reject}`]: () => json({ rejected: ["c2"] }),
    });
    await screen.findByText("03/02");
    await user.click(within(changeItems()[1]!).getByRole("button", { name: texts.sheetReject.ar }));
    expect(bodies(fetch, "POST", reject)).toEqual([{ ids: ["c2"] }]);
    await user.click(screen.getByRole("button", { name: texts.reviewAcceptAll.ar }));
    expect(bodies(fetch, "POST", accept)).toEqual([{ ids: ["c1", "c2"] }]);
    await user.click(screen.getByRole("button", { name: texts.reviewRejectAll.ar }));
    expect(bodies(fetch, "POST", reject)).toEqual([{ ids: ["c2"] }, { ids: ["c1", "c2"] }]);
  });

  it("J/K and the arrows move between changes, A accepts and R rejects, by key position (the Arabic layout too)", async () => {
    const user = userEvent.setup();
    const fetch = board([sourced, typed], {
      [`POST ${accept}`]: () => json({ version: 4, accepted: ["c2"], stale: [], undo: "tok", window_ms: 6000 }),
      [`POST ${reject}`]: () => json({ rejected: ["c1"] }),
    });
    await screen.findByText("03/02");
    const [first, second] = changeItems();
    act(() => first!.focus());
    expect(first).toHaveAttribute("aria-selected", "true");
    // J on an Arabic keyboard types «ت»: the key's place decides
    await user.keyboard("[KeyJ]");
    expect(second).toHaveAttribute("aria-selected", "true");
    expect(second).toHaveFocus();
    await user.keyboard("{ArrowUp}");
    expect(first).toHaveFocus();
    await user.keyboard("{ArrowDown}");
    expect(second).toHaveFocus();
    await user.keyboard("[KeyK]");
    expect(first).toHaveFocus();
    await user.keyboard("[KeyR]");
    expect(bodies(fetch, "POST", reject)).toEqual([{ ids: ["c1"] }]);
    await user.keyboard("[KeyJ][KeyA]");
    expect(bodies(fetch, "POST", accept)).toEqual([{ ids: ["c2"] }]);
    // a keyboard accept leaves the focus in the list, so the review goes on
    await screen.findByText(texts.reviewAcceptedShort.ar);
    expect(panel().contains(document.activeElement)).toBe(true);
  });

  it("moving to a change reveals it in 220 ms with the calm ease; reduced motion shows it at once", async () => {
    const animate = motion(false);
    const user = userEvent.setup();
    board();
    await screen.findByText("03/02");
    act(() => changeItems()[0]!.focus());
    animate.mockClear();
    await user.keyboard("[KeyJ]");
    expect(animate).toHaveBeenCalledWith(expect.anything(), { duration: DUR.base, easing: EASE });
    expect(DUR.base).toBe(220);

    const still = motion(true);
    await user.keyboard("[KeyK]");
    expect(still).not.toHaveBeenCalled();
  });
});
