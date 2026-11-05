// The open document in the workspace (Task 5): each kind shown with the viewers ONE already has, outside the canvas.
// Fake sources for the project; fetch mocked for the Deliverable's own loading and Project Records.
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createRef, type Ref } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { change, columns, core, D, DOC, entry, json, letter, sheet, viewRoutes } from "../deliverables/fixtures";
import { count, fill, setLanguage, texts } from "../i18n";
import { fakeSources, type FakeOptions } from "../project/fake";
import type { Opened, ViewerHandle } from "../project/types";
import { setCurrentProject } from "../records/project";
import { workspaceApi } from "./api";
import { DocumentView } from "./DocumentView";

// jsdom has no scrolling; the grid scrolls its active cell into view.
Element.prototype.scrollIntoView ??= () => {};

const col = (key: string) => columns.findIndex((c) => c.key === key) + 1;
function cellOf(code: string, key: string): HTMLElement {
  const row = screen.getAllByRole("row").find((r) => within(r).queryByText(code));
  if (!row) throw new Error(`no row ${code}`);
  return row.querySelector<HTMLElement>(`[role="gridcell"][aria-colindex="${col(key)}"]`)!;
}

function show(opened: Opened, options: FakeOptions = {}, ref?: Ref<ViewerHandle>) {
  const sources = fakeSources(options);
  render(
    <div style={{ width: 1200, height: 800 }}>
      <DocumentView projectId="p1" sources={sources} opened={opened} ref={ref} />
    </div>,
  );
  return sources;
}

beforeEach(() => setLanguage("ar"));
afterEach(() => {
  vi.restoreAllMocks();
  setCurrentProject(undefined);
});

describe("DocumentView", () => {
  it("a sheet Deliverable shows the Sheet viewer and its review tabs, with no Close and no title header", async () => {
    core(viewRoutes(sheet()));
    const ref = createRef<ViewerHandle>();
    show({ key: `deliverable:${D}`, anchor: null }, { deliverables: [entry()] }, ref);
    await screen.findByText("03/02");
    expect(screen.getByRole("tab", { name: texts.reviewChanges.ar })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: texts.close.ar })).toBeNull();
    // the workspace names the document: the viewer only says its title
    expect(screen.getByRole("heading", { name: sheet().title })).toHaveClass("sr-only");
    await waitFor(() => expect(ref.current!.locate({ row: "p3", column: "rate" })).toBeInstanceOf(DOMRect));
  });

  it("the top bar says the title, state, Revision and sample: the viewer's own row and sample notice are gone", async () => {
    const revision = { no: 2, version: 3, signed_off: false };
    core({ ...viewRoutes(sheet({ revision })), ...viewRoutes(letter({ revision })) });
    const sources = fakeSources({ deliverables: [entry({ revision: 2 }), entry({ id: DOC, kind: "document", revision: 2 })] });
    const { rerender } = render(<DocumentView projectId="p1" sources={sources} opened={{ key: `deliverable:${D}`, anchor: null }} />);
    await screen.findByText("03/02");
    const header = () => screen.getByRole("heading", { level: 2, hidden: true }).closest("header")!;
    expect(header()).toHaveClass("sr-only"); // nothing the bar does not say: no row («نسخة 1» was all it held)
    expect(header()).not.toHaveTextContent(fill(texts.reviewVersion.ar, { n: 3 }));
    expect(header()).not.toHaveTextContent(texts.statusDraft.ar);
    expect(header()).not.toHaveTextContent(fill(texts.reviewRev.ar, { n: 2 }));
    expect(screen.queryByText(texts.sheetSample.ar)).toBeNull(); // said once, in the switcher's facts
    rerender(<DocumentView projectId="p1" sources={sources} opened={{ key: `deliverable:${DOC}`, anchor: null }} />);
    await screen.findByRole("heading", { name: letter().title, hidden: true });
    expect(header()).toHaveClass("sr-only");
    expect(header()).not.toHaveTextContent(fill(texts.reviewVersion.ar, { n: letter().version }));
    expect(screen.queryByText(texts.sheetSample.ar)).toBeNull();
  });

  it("the viewer's row shows when it carries something the bar does not: what waits for review", async () => {
    core(viewRoutes(sheet({ pending: 1 }), { pending: [change("c1")] }));
    show({ key: `deliverable:${D}`, anchor: null }, { deliverables: [entry()] });
    await screen.findByText("03/02");
    const header = screen.getByRole("heading", { level: 2, hidden: true }).closest("header")!;
    expect(header).not.toHaveClass("sr-only");
    expect(header).toHaveTextContent(count("sheetPending", 1));
    expect(header).not.toHaveTextContent(fill(texts.reviewVersion.ar, { n: 3 }));
  });

  it("an empty review is only its tab row, with no Accept or Reject; another tab opens it", async () => {
    core(viewRoutes(sheet({ pending: 0 })));
    show({ key: `deliverable:${D}`, anchor: null }, { deliverables: [entry({ pending: 0 })] });
    await screen.findByText("03/02");
    const panel = () => document.querySelector("[data-review-panel]")!;
    await waitFor(() => expect(panel()).toHaveAttribute("data-review-panel", "folded"));
    expect(screen.getByRole("tab", { name: texts.reviewChanges.ar })).toBeInTheDocument(); // the one line
    expect(screen.getByRole("tabpanel", { hidden: true })).not.toBeVisible();
    expect(screen.queryByRole("button", { name: texts.reviewAcceptAll.ar })).toBeNull();
    expect(screen.queryByRole("button", { name: texts.reviewAcceptMine.ar })).toBeNull();
    expect(screen.queryByRole("button", { name: texts.reviewRejectAll.ar })).toBeNull();
    expect(document.querySelector("[data-review-panel]")!.previousElementSibling).toHaveClass("flex-1"); // the sheet's
    await userEvent.click(screen.getByRole("tab", { name: new RegExp(`^${texts.reviewComments.ar}`) }));
    expect(panel()).toHaveAttribute("data-review-panel", "open");
    expect(screen.getByRole("tabpanel")).toBeVisible();
  });

  it("a review with a change waiting is open, with its Accept all", async () => {
    core(viewRoutes(sheet({ pending: 1 }), { pending: [change("c1")] }));
    show({ key: `deliverable:${D}`, anchor: null }, { deliverables: [entry()] });
    await screen.findByText("03/02");
    expect(await screen.findByRole("button", { name: texts.reviewAcceptAll.ar })).toBeInTheDocument();
    expect(document.querySelector("[data-review-panel]")).toHaveAttribute("data-review-panel", "open");
  });

  it("a file loads the wider page image when its room grows", async () => {
    const observers = new Set<() => void>(); // the page switch watches its own size too
    const resized = () => observers.forEach((callback) => callback());
    vi.stubGlobal(
      "ResizeObserver",
      class {
        constructor(private callback: () => void) {}
        observe() {
          observers.add(this.callback);
        }
        unobserve() {}
        disconnect() {
          observers.delete(this.callback);
        }
      },
    );
    let width = 400;
    vi.spyOn(HTMLElement.prototype, "clientWidth", "get").mockImplementation(() => width);
    vi.stubGlobal("devicePixelRatio", 1);
    const sources = show({ key: "file:f1", anchor: null }, { pages: { f1: 2 } });
    const image = vi.spyOn(sources, "pageImage");
    expect(await screen.findByRole("img")).toHaveAttribute("src", "data:image/png;fake,f1/1/600");
    width = 1000; // the chat folded
    resized();
    await waitFor(() => expect(screen.getByRole("img")).toHaveAttribute("src", "data:image/png;fake,f1/1/1400"));
    expect(image).toHaveBeenLastCalledWith("f1", 1, 1400);
    vi.unstubAllGlobals();
  });

  it("a file opens at the anchor's page, with its page buttons", async () => {
    const ref = createRef<ViewerHandle>();
    const sources = show({ key: "file:f1", anchor: { page: 3 } }, { pages: { f1: 18 } }, ref);
    const image = vi.spyOn(sources, "pageImage");
    const page3 = await screen.findByRole("img", { name: fill(texts.sheetPageOf.ar, { page: 3, pages: 18 }) });
    expect(page3.getAttribute("src")).toMatch(/^data:image\/png;fake,f1\/3\//);
    fireEvent.click(screen.getByRole("button", { name: texts.sheetNextPage.ar }));
    expect(await screen.findByRole("img", { name: fill(texts.sheetPageOf.ar, { page: 4, pages: 18 }) })).toBeInTheDocument();
    expect(image).toHaveBeenLastCalledWith("f1", 4, expect.any(Number));
    expect(screen.getByRole("radio", { name: texts.pageViewText.ar })).toBeInTheDocument();
    expect(ref.current!.locate({ page: 4 })).toBeNull(); // a file has no viewer handle of its own
  });

  it("a client BOQ is read only: no cell opens an editor", async () => {
    const user = userEvent.setup();
    const fetch = core({});
    const client = sheet({ id: "f2", variant: "client_boq", sample: false, total: null });
    show({ key: "clientboq:f2", anchor: null }, { clientBoqViews: { f2: client } });
    await screen.findByText("03/02");
    expect(screen.getByText(texts.clientBoqReadOnly.ar)).toBeInTheDocument();
    await user.dblClick(cellOf("03/02", "rate"));
    expect(within(cellOf("03/02", "rate")).queryByRole("textbox")).toBeNull();
    await user.dblClick(cellOf("03/02", "description"));
    expect(within(cellOf("03/02", "description")).queryByRole("textbox")).toBeNull();
    expect(fetch.mock.calls.filter(([, init]) => init?.method === "POST")).toEqual([]);
  });

  it("Project files lists the files, and a file opens in the workspace", async () => {
    const files = [
      { id: "f1", name: "المواصفات الفنية - عينة.pdf", status: "read", note: null, replaces: null },
      { id: "f2", name: "مقايسة العميل - عينة.xlsx", status: "read", note: null, replaces: null },
    ];
    core({ "GET /api/projects/p1/files": () => json({ files }) });
    setCurrentProject({ id: "p1", name: "مدرسة - عينة", created_at: "2026-11-04T08:00:00.000000+00:00" });
    const open = vi.spyOn(workspaceApi, "open").mockImplementation(() => {});
    show({ key: "files:all", anchor: null });
    // named as the switcher names it
    expect(await screen.findByRole("region", { name: texts.projectFiles.ar })).toBeInTheDocument();
    const spec = await screen.findByRole("button", { name: new RegExp(files[0]!.name) });
    expect(screen.getByRole("button", { name: new RegExp(files[1]!.name) })).toBeInTheDocument();
    // the document has no panel chrome: no Close
    expect(screen.queryByRole("button", { name: texts.close.ar })).toBeNull();
    fireEvent.click(spec);
    expect(open).toHaveBeenCalledWith("file:f1");
  });

  it("a markup Deliverable says there is no view for its kind yet", async () => {
    core({});
    show({ key: "deliverable:m1", anchor: null }, { deliverables: [entry({ id: "m1", kind: "markup" })] });
    expect(await screen.findByText(texts.noViewer.ar)).toBeInTheDocument();
  });
});
