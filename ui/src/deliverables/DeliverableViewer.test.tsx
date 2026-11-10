// The Deliverable viewer, the viewer registry, the card and the Project Index against the core's contract (Plan 6
// Task 7) and Plan 7's viewer contract, with fetch and the live stream mocked: no core, no network.
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createRef } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ViewerHandle } from "../project/types";
import { setLanguage, texts } from "../i18n";
import { viewerFor } from "../viewers/registry";
import { DeliverableViewer } from "./DeliverableViewer";
import { base, change, columns, core, D, DOC, entry, fakeLive, json, letter, sheet, thread, viewRoutes } from "./fixtures";
import type { FillPlanInfo } from "./types";

// jsdom has no scrolling; the grid scrolls its active cell into view.
Element.prototype.scrollIntoView ??= () => {};

const col = (key: string) => columns.findIndex((c) => c.key === key) + 1;
function cellOf(code: string, key: string): HTMLElement {
  const row = screen.getAllByRole("row").find((r) => within(r).queryByText(code));
  if (!row) throw new Error(`no row ${code}`);
  return row.querySelector<HTMLElement>(`[role="gridcell"][aria-colindex="${col(key)}"]`)!;
}

beforeEach(() => setLanguage("ar"));

describe("viewerFor", () => {
  it("has a viewer for a Sheet and a Document, and none for markup, a board or a page", () => {
    expect(viewerFor("sheet")).toBe(DeliverableViewer);
    expect(viewerFor("document")).toBe(DeliverableViewer);
    expect(viewerFor("markup")).toBeNull();
    expect(viewerFor("board")).toBeNull();
    expect(viewerFor("page")).toBeNull();
  });

  it("loads its own data; locate finds a cell relative to its root and gives null for an unknown row", async () => {
    core(viewRoutes(sheet()));
    const live = fakeLive();
    const Viewer = viewerFor("sheet")!;
    const ref = createRef<ViewerHandle>();
    render(<Viewer projectId="p1" deliverableId={D} mode="workspace" ref={ref} {...({ subscribe: live.subscribe } as object)} />);
    await screen.findByText("03/02");
    // the grid's ref is attached a tick after its first rows draw, so wait for it under a loaded test run
    await waitFor(() => expect(ref.current!.locate({ row: "p3", column: "rate" })).toBeInstanceOf(DOMRect));
    expect(ref.current!.locate({ row: "nope", column: "rate" })).toBeNull();
  });

  it("locate brings the block into view; with scroll false it only measures", async () => {
    core(viewRoutes(letter()));
    const ref = createRef<ViewerHandle>();
    render(<DeliverableViewer projectId="p1" deliverableId={DOC} mode="workspace" ref={ref} subscribe={fakeLive().subscribe} />);
    await waitFor(() => expect(document.querySelector('[data-block-id="b2"]')).not.toBeNull());
    const scrolled = vi.spyOn(Element.prototype, "scrollIntoView");
    expect(ref.current!.locate({ row: "b2" }, { scroll: false })).toBeInstanceOf(DOMRect);
    expect(scrolled).not.toHaveBeenCalled();
    ref.current!.locate({ row: "b2" });
    expect(scrolled).toHaveBeenCalledOnce();
    scrolled.mockRestore();
  });

  it("reports a selection with its label once, even when the owner passes a new callback each render", async () => {
    core(viewRoutes(sheet()));
    const live = fakeLive();
    const seen: [unknown, string | null][] = [];
    const { rerender } = render(
      <DeliverableViewer projectId="p1" deliverableId={D} mode="workspace" subscribe={live.subscribe} onSelection={(a, l) => seen.push([a, l])} />,
    );
    await screen.findByText("03/02");
    fireEvent.mouseDown(cellOf("03/01", "rate"), { button: 0 });
    fireEvent.mouseOver(cellOf("03/04", "rate"), { buttons: 1 });
    fireEvent.mouseUp(window);
    expect(seen.at(-1)).toEqual([{ row: "p2", column: "rate" }, "البنود 03/01–03/04"]);
    const count = seen.length;
    rerender(<DeliverableViewer projectId="p1" deliverableId={D} mode="workspace" subscribe={live.subscribe} onSelection={(a, l) => seen.push([a, l])} />);
    expect(seen).toHaveLength(count);
  });

  it("a live event for this Deliverable loads it again; one for another does not", async () => {
    const versions = [sheet({ version: 3 }), sheet({ version: 4, total: { value: "5000000.00", currency: "EGP", number_id: "n2", source: "s3", dated: null, calculated: true } })];
    let views = 0;
    const routes = viewRoutes(sheet());
    core({ ...routes, [`GET ${base}/deliverables/${D}`]: () => json(versions[Math.min(views++, 1)]) });
    const live = fakeLive();
    render(<DeliverableViewer projectId="p1" deliverableId={D} mode="workspace" subscribe={live.subscribe} />);
    await screen.findByText("03/02");
    act(() => live.emit({ type: "deliverable", deliverable: entry({ id: "other" }) }));
    expect(views).toBe(1);
    act(() => live.emit({ type: "deliverable", deliverable: entry() }));
    await waitFor(() => expect(views).toBe(2));
    expect(await screen.findByText(/5,000,000\.00/)).toBeInTheDocument();
  });

  it("an empty section shows its total as —, never 0", async () => {
    core(viewRoutes(sheet()));
    render(<DeliverableViewer projectId="p1" deliverableId={D} mode="workspace" subscribe={fakeLive().subscribe} />);
    await screen.findByText("أعمال العزل");
    expect(within(cellOf("أعمال العزل", "amount")).getByText("—")).toBeInTheDocument();
  });

  it("full screen adds Changes, Comments, Versions and Close-out, with the exports", async () => {
    core({
      ...viewRoutes(sheet({ pending: 1, open_comments: 1 }), { pending: [change("c1")], comments: [thread("r1")] }),
      [`GET ${base}/deliverables/${D}/closeout`]: () => json({ pending: 1, open: [], blocking: [], check: null, can_sign_off: false, reasons: [{ en: "1 pending.", ar: "واحد مستني." }] }),
    });
    const user = userEvent.setup();
    render(<DeliverableViewer projectId="p1" deliverableId={D} mode="full" subscribe={fakeLive().subscribe} />);
    const tabs = await screen.findByRole("tablist", { name: texts.reviewPanels.ar });
    expect(within(tabs).getAllByRole("tab")).toHaveLength(4);
    expect(screen.getByRole("group", { name: texts.exportMenu.ar })).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: texts.reviewAcceptMine.ar })).toBeInTheDocument();
    await user.click(within(tabs).getAllByRole("tab")[1]!);
    expect(screen.getByText("راجع الفئة - عينة")).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: texts.reviewCloseOut.ar }));
    expect(await screen.findByText("واحد مستني.")).toBeInTheDocument();
    expect(screen.getByRole("tabpanel")).toHaveAttribute("dir", "rtl");
  });

  it("full screen finds the Sheet's newest Fill Plan, live, and opens its preview; the plan's id is never shown", async () => {
    const F = "e".repeat(32);
    const plans: FillPlanInfo[] = [];
    const fetch = core({
      ...viewRoutes(sheet()),
      [`GET ${base}/deliverables/${D}/fill-plans`]: () => json({ plans }),
      [`GET ${base}/fill-plans/${F}/preview`]: () => json({ error: { en: "Sign off first.", ar: "اعتمد الأول." }, field: null }, 409),
    });
    const live = fakeLive();
    const user = userEvent.setup();
    render(<DeliverableViewer projectId="p1" deliverableId={D} mode="full" subscribe={live.subscribe} />);
    await screen.findByRole("tablist", { name: texts.reviewPanels.ar });
    await waitFor(() => expect(fetch.mock.calls.some(([u]) => String(u).endsWith("/fill-plans"))).toBe(true));
    expect(screen.queryByRole("button", { name: texts.exportClientFile.ar })).toBeNull();

    // the Lead QS saves a plan: the core announces the Deliverable, and the board finds it
    plans.push(
      { id: F, file_name: "مقايسة العميل - عينة.xlsx", created_at: "2026-11-05T10:00:00.000000+00:00", status: "needs_signoff" },
      { id: "a".repeat(32), file_name: "قديم - عينة.xlsx", created_at: "2026-11-05T09:00:00.000000+00:00", status: "needs_signoff" },
    );
    act(() => live.emit({ type: "deliverable", deliverable: entry() }));
    const button = await screen.findByRole("button", { name: texts.exportClientFile.ar });
    expect(screen.getByText("مقايسة العميل - عينة.xlsx")).toBeInTheDocument();
    expect(screen.queryByText("قديم - عينة.xlsx")).toBeNull();
    expect(document.body.textContent).not.toContain(F);
    await user.click(button);
    expect(await screen.findByRole("region", { name: texts.fillPreview.ar })).toBeInTheDocument();
    expect(await screen.findByRole("alert")).toHaveTextContent("اعتمد الأول.");
  });

  it("a Document never asks for Fill Plans", async () => {
    const fetch = core({ ...viewRoutes(sheet()), ...viewRoutes(letter()) });
    render(<DeliverableViewer projectId="p1" deliverableId={DOC} mode="full" subscribe={fakeLive().subscribe} />);
    await screen.findByRole("tablist", { name: texts.reviewPanels.ar });
    expect(fetch.mock.calls.some(([u]) => String(u).includes("fill-plans"))).toBe(false);
  });
});

describe("texts", () => {
  it("every new label exists in both languages", () => {
    const keys: (keyof typeof texts)[] = [
      "deliverableSheet", "deliverableDocument", "deliverableOther", "deliverableOpen", "deliverableType", "deliverableTitle",
      "deliverableStatus", "deliverableNoRevision", "deliverableFailed", "deliverableNoViewer", "deliverableLoading",
      "reviewPanels", "reviewNoChanges", "reviewStaleWhy", "reviewAcceptWithUpdate", "reviewFieldChanged", "reviewMore",
      "reviewAccepted", "reviewNothingAccepted", "reviewRejected", "reviewOpAddRow", "reviewOpAddSection", "reviewOpRemoveRow",
      "reviewOpMoveRow", "reviewOpColumns", "reviewOpInsertBlock", "reviewOpRemoveBlock", "reviewOpMoveBlock", "placeItem",
      "placeItems", "placeCell", "placeWhole", "placeParagraph", "placeQuote", "placeMoved", "reviewCommentOn",
      "reviewCommentAdd", "reviewCommentText", "reviewReplyText", "reviewNoComments", "reviewFixSent", "reviewFilter",
      "reviewCodeC", "reviewFrom", "reviewTo", "reviewBy", "reviewIssued", "reviewAdded", "reviewRemoved",
      "reviewMovedRow", "reviewNoDifference", "reviewCanSignOff", "reviewRevisionIssued", "exportSaved", "exportDownloaded",
      "exportCancelled", "exportFailed", "fillSkippedMerged", "fillSkipped", "fillMismatches", "fillOurs", "fillTheirs",
      "fillMarkedRight", "fillMismatchesFirst", "fillUnmappedItems", "fillNoPlan",
    ];
    for (const key of keys) {
      expect(texts[key].en.trim(), key).not.toBe("");
      expect(texts[key].ar.trim(), key).not.toBe("");
      expect(texts[key].ar, key).not.toBe(texts[key].en);
    }
  });
});
