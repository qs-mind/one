// The Deliverable viewer, the viewer registry, the card and the Project Index against the core's contract (Plan 6
// Task 7) and Plan 7's viewer contract, with fetch and the live stream mocked: no core, no network.
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createRef } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ViewerHandle } from "../canvas/types";
import { fill, setLanguage, texts } from "../i18n";
import { viewerFor } from "../viewers/registry";
import { DeliverableCard } from "./DeliverableCard";
import { DeliverableViewer } from "./DeliverableViewer";
import { base, change, columns, core, D, entry, fakeLive, json, sheet, thread, viewRoutes } from "./fixtures";
import { ProjectIndex } from "./ProjectIndex";

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
    render(<Viewer projectId="p1" deliverableId={D} mode="frame" ref={ref} {...({ subscribe: live.subscribe } as object)} />);
    await screen.findByText("03/02");
    expect(ref.current!.locate({ row: "p3", column: "rate" })).toBeInstanceOf(DOMRect);
    expect(ref.current!.locate({ row: "nope", column: "rate" })).toBeNull();
    // the frame is the viewer only: no review panels, no exports
    expect(screen.queryByRole("tablist")).toBeNull();
    expect(screen.queryByRole("group", { name: texts.exportMenu.ar })).toBeNull();
  });

  it("reports a selection with its label once, even when the owner passes a new callback each render", async () => {
    core(viewRoutes(sheet()));
    const live = fakeLive();
    const seen: [unknown, string | null][] = [];
    const { rerender } = render(
      <DeliverableViewer projectId="p1" deliverableId={D} mode="frame" subscribe={live.subscribe} onSelection={(a, l) => seen.push([a, l])} />,
    );
    await screen.findByText("03/02");
    fireEvent.mouseDown(cellOf("03/01", "rate"), { button: 0 });
    fireEvent.mouseOver(cellOf("03/04", "rate"), { buttons: 1 });
    fireEvent.mouseUp(window);
    expect(seen.at(-1)).toEqual([{ row: "p2", column: "rate" }, "البنود 03/01–03/04"]);
    const count = seen.length;
    rerender(<DeliverableViewer projectId="p1" deliverableId={D} mode="frame" subscribe={live.subscribe} onSelection={(a, l) => seen.push([a, l])} />);
    expect(seen).toHaveLength(count);
  });

  it("a live event for this Deliverable loads it again; one for another does not", async () => {
    const versions = [sheet({ version: 3 }), sheet({ version: 4, total: { value: "5000000.00", currency: "EGP", number_id: "n2", source: "s3", dated: null, calculated: true } })];
    let views = 0;
    const routes = viewRoutes(sheet());
    core({ ...routes, [`GET ${base}/deliverables/${D}`]: () => json(versions[Math.min(views++, 1)]) });
    const live = fakeLive();
    render(<DeliverableViewer projectId="p1" deliverableId={D} mode="frame" subscribe={live.subscribe} />);
    await screen.findByText("03/02");
    act(() => live.emit({ type: "deliverable", deliverable: entry({ id: "other" }) }));
    expect(views).toBe(1);
    act(() => live.emit({ type: "deliverable", deliverable: entry() }));
    await waitFor(() => expect(views).toBe(2));
    expect(await screen.findByText(/5,000,000\.00/)).toBeInTheDocument();
  });

  it("an empty section shows its total as —, never 0", async () => {
    core(viewRoutes(sheet()));
    render(<DeliverableViewer projectId="p1" deliverableId={D} mode="frame" subscribe={fakeLive().subscribe} />);
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
});

describe("DeliverableCard", () => {
  it("shows the Deliverable from the list, updates live, and Open opens it", async () => {
    core({ [`GET ${base}/deliverables`]: () => json({ deliverables: [entry()] }) });
    const live = fakeLive();
    const onOpen = vi.fn();
    const user = userEvent.setup();
    render(<DeliverableCard projectId="p1" id={D} onOpen={onOpen} subscribe={live.subscribe} />);
    expect(await screen.findByText("جدول الكميات - عينة")).toBeInTheDocument();
    expect(screen.getByText(texts.deliverableNoRevision.ar)).toBeInTheDocument();
    expect(screen.getByText(texts.sampleData.ar)).toBeInTheDocument();
    act(() => live.emit({ type: "deliverable", deliverable: entry({ revision: 2 }) }));
    expect(screen.getByText(fill(texts.reviewRev.ar, { n: 2 }))).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: new RegExp(texts.deliverableOpen.ar) }));
    expect(onOpen).toHaveBeenCalledWith(D);
  });
});

describe("ProjectIndex", () => {
  it("lists the Deliverables newest first, live, and opens one", async () => {
    const older = entry({ id: "a", title: "خطاب - عينة", kind: "document", updated_at: "2026-11-04T09:00:00.000000+00:00" });
    core({ [`GET ${base}/deliverables`]: () => json({ deliverables: [older, entry()] }) });
    const live = fakeLive();
    const onOpen = vi.fn();
    const user = userEvent.setup();
    render(<ProjectIndex projectId="p1" onOpen={onOpen} subscribe={live.subscribe} />);
    await screen.findByText("خطاب - عينة");
    const titles = () => screen.getAllByRole("row").slice(1).map((r) => within(r).getAllByRole("cell")[0]!.textContent);
    expect(titles()).toEqual(["جدول الكميات - عينة", "خطاب - عينة"]);
    act(() => live.emit({ type: "deliverable", deliverable: { ...older, updated_at: "2026-11-05T10:00:00.000000+00:00" } }));
    expect(titles()).toEqual(["خطاب - عينة", "جدول الكميات - عينة"]);
    await user.click(screen.getByRole("button", { name: "خطاب - عينة" }));
    expect(onOpen).toHaveBeenCalledWith("a");
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
      "reviewCodeC", "reviewFrom", "reviewTo", "reviewBy", "reviewChangesCount", "reviewIssued", "reviewAdded", "reviewRemoved",
      "reviewMovedRow", "reviewNoDifference", "reviewCanSignOff", "reviewRevisionIssued", "exportSaved", "exportDownloaded",
      "exportCancelled", "exportFailed", "fillSkippedMerged", "fillSkipped", "fillMismatches", "fillOurs", "fillTheirs",
      "fillMarkedRight", "fillMismatchesFirst", "fillUnmappedRows", "fillUnmappedItems", "fillNoPlan",
    ];
    for (const key of keys) {
      expect(texts[key].en.trim(), key).not.toBe("");
      expect(texts[key].ar.trim(), key).not.toBe("");
      expect(texts[key].ar, key).not.toBe(texts[key].en);
    }
  });
});
