import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { listening, P2, publish, server, startFakeCore } from "@/api/fakeCore";
import { paths } from "@/app/paths";
import type { DeliverableInfo, Explained, SheetView } from "@/deliverables/types";
import { renderIn, resetPage, stubBrowser } from "@/design/test/harness";
import { setCurrentProject } from "@/records/project";
import { Tender } from "./Tender";

startFakeCore();

// The tender's documents, as today's routes send them; names and values are sample data.
const D = "d".repeat(32);
const info: DeliverableInfo = {
  id: D, kind: "sheet", title: "جدول الكميات المسعّر - عينة", language: "ar", status: "draft", code: null,
  same_provider: false, revision: null,
} as DeliverableInfo;
const num = (value: string, id: string) => ({ value, number_id: id, source: "s1", dated: "2026-11-02", currency: "EGP" });
const sheet: SheetView = {
  id: D, kind: "sheet", variant: "boq", title: info.title, language: "ar", status: "draft", code: null,
  same_provider: false, off_desk: false, version: 1, at: "2026-11-05T09:00:00.000000+00:00", revision: null, sample: true,
  columns: [
    { key: "code", label: { en: "Item", ar: "البند" }, kind: "text", edit: false, frozen: true, wrap: false, width: 70 },
    { key: "description", label: { en: "Description", ar: "الوصف" }, kind: "text", edit: false, frozen: false, wrap: true, width: 300 },
    { key: "rate", label: { en: "Rate", ar: "السعر" }, kind: "number", edit: false, frozen: false, wrap: false, width: 110 },
  ],
  rows: ["3/01", "3/02", "3/03"].map((code, i) => ({
    id: `r${i}`, kind: "item", item_id: `i${i}`, item_version: 1, version: 1, code,
    cells: { description: { text: "خرسانة مسلحة - عينة" }, rate: num(String(4200 + i * 1000), `n${i}`) },
  })),
  total: null,
  sources: { s1: { kind: "sample", title: "عرض مورد - عينة", locator: { page: 2 }, url: null, dated: "2026-11-02" } },
  incomplete: {}, pending: 0, open_comments: 0, records_moved: false,
} as unknown as SheetView;
const explained = (id: string): Explained => ({
  number: {
    id, item: { id: "i1", code: "3/02", kind: "rate" }, name: "rate", value: "5200", unit: null, currency: "EGP",
    dated: "2026-11-02", recorded_at: "2026-11-02T08:00:00+00:00", recorded_by: "Lead QS", current: true, replaced_by: null, reason: null,
  },
  source: { id: "s1", kind: "sample", title: "Supplier quote (sample)", file_id: null, locator: { page: 2 }, url: null, dated: "2026-11-02" },
  calculation: null,
});

let unhandled: string[];
server.events.on("request:unhandled", ({ request }) => unhandled.push(`${request.method} ${new URL(request.url).pathname}`));
beforeEach(() => {
  stubBrowser();
  unhandled = [];
  const base = "*/api/projects/:id";
  server.use(
    http.post(`${base}/open`, ({ params }) => HttpResponse.json({ id: params.id, name: "مبنى إداري - عينة", created_at: "2026-11-01T09:00:00Z", open: true })),
    http.get("*/api/chat/:id/messages", () => HttpResponse.json({ messages: [] })),
    http.get("*/api/chat/:id/stream", () => new HttpResponse(null, { status: 204 })),
    http.get(`${base}/deliverables`, () => HttpResponse.json({ deliverables: [info] })),
    http.get(`${base}/deliverables/:d`, () => HttpResponse.json(sheet)),
    http.get(`${base}/deliverables/:d/changes`, () => HttpResponse.json({ changes: [] })),
    http.get(`${base}/deliverables/:d/comments`, () => HttpResponse.json({ comments: [] })),
    http.get(`${base}/numbers/:n/explain`, ({ params }) => HttpResponse.json(explained(String(params.n)))),
    http.get(`${base}/deliverables/:d/fill-plans`, () => HttpResponse.json({ plans: [] })),
    http.get(`${base}/files`, () => HttpResponse.json({ files: [] })),
    // a file's own reads: this test file holds no file contents
    http.get(`${base}/files/:f/:part`, () => HttpResponse.json({ error: { en: "Not here", ar: "مش هنا" } }, { status: 404 })),
    http.get(`${base}/map`, () =>
      HttpResponse.json({ status: { waiting: 0, reading: 0, total: 0, line: { en: "", ar: "" } }, groups: [], files: [], next_cursor: null }),
    ),
    http.get(`${base}/map/:part`, ({ params }) => HttpResponse.json({ [String(params.part)]: [], next_cursor: null })),
  );
});
afterEach(() => {
  resetPage();
  setCurrentProject(undefined);
  expect(unhandled).toEqual([]);
});

function open(path: string) {
  const routes = ["/tender/:id", "/tender/:id/doc/:docId", "/tender/:id/room", "/tender/:id/member/:memberId"];
  const router = createMemoryRouter(
    routes.map((p) => ({ path: p, element: <Tender /> })),
    { initialEntries: [path] },
  );
  renderIn("ltr", <RouterProvider router={router} />);
  return router;
}

describe("what opens beside the thread", () => {
  it("lists the documents in the side column, each opening in the document's place", async () => {
    const router = open(paths.tender(P2));
    const list = within(await screen.findByRole("region", { name: "Documents" }));
    const links = await list.findAllByRole("link");
    expect(links.map((a) => a.getAttribute("href"))).toEqual([
      paths.doc(P2, `deliverable:${D}`),
      paths.doc(P2, "view:project-map"),
      paths.doc(P2, "files:all"),
    ]);
    await userEvent.click(list.getByRole("link", { name: "Project files" }));
    expect(router.state.location.pathname).toBe(paths.doc(P2, "files:all"));
    // the kept Project files read the tender the place opened, not "open a project first"
    await screen.findByRole("region", { name: "Open document" });
    await waitFor(() => expect(document.querySelector('[data-region="document"]')?.textContent).not.toBe(""));
    expect(screen.queryByText("Open a project or create one first")).toBeNull();
  });

  it("lists a Deliverable the team writes while the tender is open, with no reload", async () => {
    let held = [info];
    server.use(http.get("*/api/projects/:id/deliverables", () => HttpResponse.json({ deliverables: held })));
    open(paths.tender(P2));
    const list = within(await screen.findByRole("region", { name: "Documents" }));
    await list.findByRole("link", { name: info.title });
    await waitFor(() => expect(listening(P2)).toBeGreaterThan(0));
    const fresh = { ...info, id: "e".repeat(32), title: "تحليل الأسعار - عينة" } as DeliverableInfo;
    held = [info, fresh];
    act(() => publish(P2, { type: "deliverable", deliverable: fresh }));
    expect(await list.findByRole("link", { name: fresh.title })).toHaveAttribute("href", paths.doc(P2, `deliverable:${fresh.id}`));
  });

  it("opens a source of the thread as its file beside the thread", async () => {
    const router = open(paths.tender(P2));
    const finding = await waitFor(() => {
      const card = document.querySelector<HTMLElement>('[data-decision="5a000000000000000000000000009002"]');
      expect(card).not.toBeNull();
      return card!;
    });
    await userEvent.click(within(finding).getByRole("button", { name: /جدول الكميات - عينة/ }));
    expect(router.state.location.pathname).toBe(paths.doc(P2, "file:5a0000000000000000000000000000f3"));
  });
});

describe("a sheet in the document's place", () => {
  it("draws dense rows and shows a clicked number's source under the sheet", async () => {
    open(paths.doc(P2, `deliverable:${D}`));
    const grid = await screen.findByRole("grid");
    // the head row, then the three rows, as the grid lays them out ("repeat(1, 36px)36px …")
    const rows = () =>
      grid.style.gridTemplateRows.replace(/repeat\((\d+), (\d+px)\)/g, (_, n: string, h: string) => ` ${h}`.repeat(Number(n))).match(/\d+px/g);
    await waitFor(() => expect(rows()).toEqual(["36px", "36px", "36px", "36px"]));
    const row = screen.getAllByRole("row").find((r) => within(r).queryByText("3/02"))!;
    await userEvent.click(row.querySelector<HTMLElement>('[role="gridcell"][aria-colindex="3"]')!);
    const panel = await screen.findByRole("region", { name: "Where the number comes from" });
    expect(panel.closest('[data-region="document"]')).not.toBeNull();
    expect(await within(panel).findByText(/Source:/)).toHaveTextContent("Supplier quote (sample)");
    expect(screen.queryByRole("dialog")).toBeNull(); // not the floating source card
  });
});
