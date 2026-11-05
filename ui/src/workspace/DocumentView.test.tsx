// The open document in the workspace (Task 5): each kind shown with the viewers ONE already has, outside the canvas.
// Fake sources for the project; fetch mocked for the Deliverable's own loading and Project Records.
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createRef, type Ref } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { columns, core, D, entry, json, sheet, viewRoutes } from "../deliverables/fixtures";
import { fill, setLanguage, texts } from "../i18n";
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
