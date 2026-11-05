// The Sheet viewer against the core's contract (Plan 6 Task 7), with fetch mocked: no core, no network.
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createRef, useState } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { deliverablesApi, dispositionName } from "../../deliverables/api";
import type { Change, Explained, SheetView, Thread, ViewColumn, ViewRow } from "../../deliverables/types";
import { fill, setLanguage, texts } from "../../i18n";
import { workspaceApi } from "../../workspace/api";
import { SheetViewer, type SheetHandle } from "./SheetViewer";

const P = "p1";
const D = "d".repeat(32);
const base = `/api/projects/${P}`;

// Sample data, as the core's samples build it: «عينة» in names, sources of kind sample.
const columns: ViewColumn[] = [
  { key: "description", label: { en: "Description", ar: "بيان الأعمال" }, kind: "text", edit: true, frozen: false, wrap: true, width: 420 },
  { key: "code", label: { en: "Item", ar: "البند" }, kind: "text", edit: false, frozen: true, wrap: false, width: 70 },
  { key: "unit", label: { en: "Unit", ar: "الوحدة" }, kind: "text", edit: false, frozen: false, wrap: false, width: 60 },
  { key: "quantity", label: { en: "Qty", ar: "الكمية" }, kind: "number", edit: true, frozen: false, wrap: false, width: 90 },
  { key: "rate", label: { en: "Rate", ar: "الفئة" }, kind: "number", edit: true, frozen: false, wrap: false, width: 110 },
  { key: "amount", label: { en: "Amount", ar: "الإجمالي" }, kind: "calc", edit: false, frozen: false, wrap: false, width: 130 },
];
// Screen order: the frozen code column first (on the right in RTL), then the others in the core's order.
const col = (key: string) => ["code", "description", "unit", "quantity", "rate", "amount"].indexOf(key) + 1;

const n = (value: string, id: string, more: object = {}) => ({ value, number_id: id, source: "s1", dated: "2026-11-01", ...more });
const calc = (value: string, id: string) => n(value, id, { currency: "EGP", source: "s3", calculated: true });

const rows: ViewRow[] = [
  { id: "p1", kind: "section", level: 1, item_id: "i1", title: "أعمال الحفر", version: 1, cells: { amount: calc("77770.00", "n-s1") } },
  {
    id: "p2", kind: "item", item_id: "i2", item_version: 3, version: 1, code: "1-1",
    cells: {
      description: { text: "بالمتر المكعب حفر في أي نوع من التربة - عينة" },
      unit: { text: "m3" },
      quantity: n("5555", "n-q1", { unit: "m3" }),
      rate: n("14", "n-r1", { unit: "m3", currency: "EGP" }),
      amount: calc("77770.00", "n-a1"),
    },
  },
  { id: "p3", kind: "section", level: 1, item_id: "i3", title: "أعمال الخرسانة", version: 1, cells: { amount: calc("4782060.00", "n-s2") } },
  {
    id: "p4", kind: "item", item_id: "i4", item_version: 2, version: 1, code: "03/02",
    cells: {
      description: { text: "خرسانة مسلحة للأساسات - عينة" },
      unit: { text: "m3" },
      quantity: n("120", "n-q2", { unit: "m3" }),
      rate: n("39850.50", "n-rate", { unit: "m3", currency: "EGP" }),
      amount: calc("4782060.00", "n-amount"),
    },
  },
  {
    id: "p5", kind: "item", item_id: "i5", item_version: 1, version: 1, code: "03/03",
    cells: {
      description: { text: "خرسانة عادية تحت الأساسات - عينة" },
      unit: { text: "م2" },
      quantity: { text: "فئة فقط" },
      rate: n("250", "n-r3", { unit: "م2", currency: "EGP" }),
    },
  },
];

function sheet(more: Partial<SheetView> = {}): SheetView {
  return {
    id: D, kind: "sheet", variant: "boq", title: "جدول الكميات - عينة", language: "ar",
    status: "draft", code: null, same_provider: false, off_desk: false,
    version: 1, at: "2026-11-05T09:00:00.000000+00:00", revision: null, sample: true,
    columns, rows,
    total: calc("4859830.00", "n-total"),
    sources: {
      s1: { kind: "sample", title: "بيانات تجريبية - عينة", file_name: "عرض سعر - عينة.pdf", locator: { page: 3 }, url: null, dated: null },
      s3: { kind: "calculation", title: "quantity * rate", locator: { calculation: "c1" } },
    },
    incomplete: { amount: 1 }, pending: 0, open_comments: 0, records_moved: false,
    ...more,
  };
}

function change(id: string, more: Partial<Change> = {}): Change {
  return {
    id, deliverable_id: D,
    op: { op: "set_number", row: "p4", name: "rate", value: "40000", unit: "m3", currency: "EGP", expect: "n-rate" },
    reason: null, author: "engineer", comment_id: null, status: "pending",
    created_at: "2026-11-05T09:01:00.000000+00:00", decided_at: null, decided_by: null, version_n: null,
    before: n("39850.50", "n-rate", { unit: "m3", currency: "EGP" }),
    after: { value: "40000", unit: "m3", currency: "EGP", number_id: "", source: "", dated: null },
    follows: [{ row: "p4", column: "amount", before: calc("4782060.00", "n-amount"), after: calc("4800000.00", "") }],
    ...more,
  };
}

type Route = (url: string, init: RequestInit) => Response | Promise<Response>;
function core(routes: Record<string, Route>) {
  const fetch = vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = String(input);
    const route = routes[`${init.method ?? "GET"} ${url.split("?")[0]}`];
    return route ? route(url, init) : new Response("not found", { status: 404 });
  });
  vi.stubGlobal("fetch", fetch);
  return fetch;
}
const bodies = (fetch: ReturnType<typeof core>, method: string, path: string) =>
  fetch.mock.calls
    .filter(([u, init]) => String(u).split("?")[0] === path && (init?.method ?? "GET") === method)
    .map(([, init]) => JSON.parse(String(init!.body)) as unknown);

// The owner's part (Task 10's useDeliverable does this for real): refetch the view and changes after an edit.
function Live({ initial, ...more }: { initial: SheetView; comments?: Thread[] }) {
  const [view, setView] = useState(initial);
  const [changes, setChanges] = useState<Change[]>([]);
  async function reload() {
    const v = await deliverablesApi.view(P, D);
    if (v.ok) setView(v.data as SheetView);
    const c = await deliverablesApi.changes(P, D, "pending");
    if (c.ok) setChanges(c.data.changes);
  }
  return <SheetViewer projectId={P} view={view} changes={changes} onChanged={() => void reload()} {...more} />;
}

/** The grid cell of the row whose code (or section title) is `code`, in column `key`. */
function cellOf(code: string, key: string): HTMLElement {
  const row = screen.getAllByRole("row").find((r) => within(r).queryByText(code));
  if (!row) throw new Error(`no row ${code}`);
  return row.querySelector<HTMLElement>(`[role="gridcell"][aria-colindex="${col(key)}"]`)!;
}

// jsdom has no scrolling; the grid scrolls its active cell into view.
Element.prototype.scrollIntoView ??= () => {};

beforeEach(() => setLanguage("ar"));

describe("SheetViewer", () => {
  it("the code column is frozen and the grid is rtl for an Arabic Deliverable in an English screen", () => {
    setLanguage("en");
    render(<SheetViewer projectId={P} view={sheet()} />);
    const grid = screen.getByRole("grid");
    expect(grid).toHaveAttribute("dir", "rtl");
    const headers = within(grid).getAllByRole("columnheader");
    expect(headers[0]).toHaveTextContent("البند"); // column labels in the Deliverable's language
    expect(headers[0]).toHaveClass("rdg-cell-frozen-start"); // start is the right edge in RTL
    expect(cellOf("03/02", "code")).toHaveClass("rdg-cell-frozen-start");
    expect(screen.getByRole("heading", { name: "جدول الكميات - عينة" })).toHaveAttribute("dir", "auto");
  });

  it("shows exact numbers formatted from their strings, the text that stands for a missing one, and the total", () => {
    render(<SheetViewer projectId={P} view={sheet()} />);
    expect(cellOf("03/02", "rate")).toHaveTextContent("39,850.50");
    expect(cellOf("03/02", "amount")).toHaveTextContent("4,782,060.00");
    expect(cellOf("03/02", "quantity")).toHaveTextContent(/^120$/);
    expect(cellOf("03/03", "quantity")).toHaveTextContent("فئة فقط");
    expect(cellOf("03/02", "rate").querySelector("bdi")).toHaveAttribute("dir", "ltr");
    expect(cellOf("أعمال الخرسانة", "amount")).toHaveTextContent("4,782,060.00");
    expect(screen.getByRole("button", { name: "4,859,830.00" })).toBeInTheDocument();
    expect(screen.getByText(texts.sheetTotal.ar)).toBeInTheDocument();
  });

  it("the total the core sends rolls to its new value when an edit changes it; still on first render and on another Deliverable", () => {
    const animate = vi.fn(() => ({ finished: new Promise(() => {}), finish() {}, cancel() {} }));
    Object.defineProperty(Element.prototype, "animate", { configurable: true, writable: true, value: animate });
    try {
      const { rerender } = render(<SheetViewer projectId={P} view={sheet()} />);
      expect(animate).not.toHaveBeenCalled();
      rerender(<SheetViewer projectId={P} view={sheet({ version: 2, total: calc("4877770.00", "n-total-2") })} />);
      expect(animate).toHaveBeenCalled(); // the digits that changed roll
      const total = screen.getByRole("button", { name: "4,877,770.00" });
      expect(total.querySelector(".sr-only")).toHaveTextContent("4,877,770.00");
      animate.mockClear();
      rerender(<SheetViewer projectId={P} view={sheet({ id: "e".repeat(32), total: calc("120.00", "n-other") })} />);
      expect(animate).not.toHaveBeenCalled(); // another Deliverable's total is not a change
      expect(screen.getByRole("button", { name: "120.00" })).toBeInTheDocument();
    } finally {
      delete (Element.prototype as { animate?: unknown }).animate;
    }
  });

  it("the sample banner and the status chip have text labels in both languages", () => {
    const view = sheet({ status: "checked", code: "B", same_provider: true, off_desk: true, version: 7, pending: 3, revision: { no: 2, version: 5, signed_off: false } });
    const { rerender } = render(<SheetViewer projectId={P} view={view} />);
    expect(screen.getByRole("note")).toHaveTextContent(texts.sheetSample.ar);
    for (const line of ["مُراجَع: كود B", texts.statusSameProvider.ar, texts.statusOffDesk.ar, "نسخة 7", "إصدار 2", "3 تعديلات مقترحة"])
      expect(screen.getByText(line)).toBeInTheDocument();
    act(() => setLanguage("en"));
    rerender(<SheetViewer projectId={P} view={view} />);
    expect(screen.getByRole("note")).toHaveTextContent(texts.sheetSample.en);
    for (const line of ["Checked: Code B", "Same-provider check", "Off-Desk", "Version 7", "Rev 2", "3 suggested changes"])
      expect(screen.getByText(line)).toBeInTheDocument();
    rerender(<SheetViewer projectId={P} view={sheet({ sample: false, status: "signed_off" })} />);
    expect(screen.queryByRole("note")).toBeNull();
    expect(screen.getByText("Signed off")).toBeInTheDocument();
  });

  it("an edit posts a change and shows old struck, new and ✓ ✗", async () => {
    const user = userEvent.setup();
    const pending = change("c1");
    const fetch = core({
      [`POST ${base}/deliverables/${D}/changes`]: () => Response.json({ changes: [pending] }, { status: 201 }),
      [`GET ${base}/deliverables/${D}`]: () => Response.json(sheet({ pending: 1 })),
      [`GET ${base}/deliverables/${D}/changes`]: () => Response.json({ changes: [pending] }),
    });
    render(<Live initial={sheet()} />);
    await user.dblClick(cellOf("03/02", "rate"));
    const editor = within(cellOf("03/02", "rate")).getByRole("textbox");
    expect(editor).toHaveValue("39850.50"); // the exact string, never 39850.5
    expect(screen.queryByRole("dialog")).toBeNull(); // the source of the clicked number gives way to the editor
    await user.clear(editor);
    await user.type(editor, "٤٠٠٠٠{Enter}");
    await waitFor(() => expect(screen.getByText("تعديل واحد مقترح")).toBeInTheDocument());
    expect(bodies(fetch, "POST", `${base}/deliverables/${D}/changes`)).toEqual([
      { ops: [{ op: "set_number", row: "p4", name: "rate", value: "40000", unit: "m3", currency: "EGP", expect: "n-rate" }], reason: null },
    ]);
    const rate = cellOf("03/02", "rate");
    expect(rate.querySelector("del")).toHaveTextContent("39,850.50");
    expect(rate.querySelector("ins")).toHaveTextContent("40,000.00");
    expect(within(rate).getByRole("button", { name: texts.sheetAccept.ar })).toBeInTheDocument();
    expect(within(rate).getByRole("button", { name: texts.sheetReject.ar })).toBeInTheDocument();
    const amount = cellOf("03/02", "amount"); // what the QS Calc Engine would write, shown before accepting
    expect(amount.querySelector("del")).toHaveTextContent("4,782,060.00");
    expect(amount.querySelector("ins")).toHaveTextContent("4,800,000.00");
    expect(amount).toHaveTextContent(texts.sheetRecalculated.ar);
    expect(within(amount).queryByRole("button")).toBeNull();
  });

  it("full mode fills the board: the room the columns leave goes to the description, and the grid is as tall as its rows", () => {
    core({});
    // the board's width is read once at first, then on each resize (none here)
    vi.stubGlobal(
      "ResizeObserver",
      class {
        observe() {}
        disconnect() {}
      },
    );
    const width = vi.spyOn(HTMLElement.prototype, "clientWidth", "get").mockReturnValue(1400);
    try {
      const { container } = render(<SheetViewer projectId={P} view={sheet()} mode="full" />);
      const columns = () => (container.querySelector<HTMLElement>(".rdg")?.style.gridTemplateColumns ?? "");
      // 952 px of columns (each 12 px wider than set) in 1400: the description takes the rest but for a scroll bar
      expect(columns()).toContain(`${420 + 12 + (1400 - 952 - 16)}px`);
      const box = container.querySelector<HTMLElement>(".rdg")!.parentElement!.parentElement!;
      expect(box.style.height).not.toBe("");
      expect(box).toHaveClass("flex-[0_1_auto]");
    } finally {
      width.mockRestore();
      vi.unstubAllGlobals();
    }
    // outside the board the columns keep their own widths
    const { container } = render(<SheetViewer projectId={P} view={sheet()} />);
    expect(container.querySelector<HTMLElement>(".rdg")?.style.gridTemplateColumns).toContain("432px");
  });

  it("a long item code shows whole: its column is as wide as the longest code (tender day: «…01-01» on every row)", () => {
    core({});
    const long = rows.map((r) => (r.id === "p4" ? { ...r, code: "02-01-001-B" } : r));
    const { container } = render(<SheetViewer projectId={P} view={sheet({ rows: long })} />);
    const widths = (container.querySelector<HTMLElement>(".rdg")?.style.gridTemplateColumns ?? "").match(/\d+(?=px)/g)!.map(Number);
    // jsdom measures 7 px a character: 11 characters, the cell's 24 px padding, and the 12 px the screen adds
    expect(widths[0]).toBeGreaterThanOrEqual(11 * 7 + 24);
  });

  it("full mode on a narrow board: the description gives room back, so the Amount column and the total stay in sight", () => {
    core({});
    vi.stubGlobal(
      "ResizeObserver",
      class {
        observe() {}
        disconnect() {}
      },
    );
    const width = vi.spyOn(HTMLElement.prototype, "clientWidth", "get").mockReturnValue(900);
    try {
      const { container } = render(<SheetViewer projectId={P} view={sheet()} mode="full" />);
      const widths = (container.querySelector<HTMLElement>(".rdg")?.style.gridTemplateColumns ?? "").match(/\d+(?=px)/g)!.map(Number);
      expect(widths.reduce((a, b) => a + b, 0)).toBeLessThanOrEqual(900 - 16);
      expect(widths[1]).toBeGreaterThanOrEqual(240); // the description stays readable
    } finally {
      width.mockRestore();
      vi.unstubAllGlobals();
    }
  });

  it("read only (the client's BOQ): nothing opens an editor or posts a change, each number opens its file", async () => {
    const user = userEvent.setup();
    const fetch = core({});
    const openFile = vi.spyOn(workspaceApi, "open").mockImplementation(() => {});
    const client = sheet({
      variant: "client_boq",
      sample: false,
      total: null,
      sources: { s1: { kind: "boq", title: "BOQ", file_name: "مقايسة العميل - عينة.xlsx", file_id: "f1", locator: { sheet: "BOQ", row: 5, column: "E" }, url: null, dated: null } },
    });
    render(<SheetViewer projectId={P} view={client} readOnly />);
    expect(screen.getByText(texts.clientBoqReadOnly.ar)).toBeInTheDocument();
    expect(screen.queryByText(texts.statusDraft.ar)).toBeNull();
    await user.dblClick(cellOf("03/02", "rate"));
    expect(within(cellOf("03/02", "rate")).queryByRole("textbox")).toBeNull();
    await user.dblClick(cellOf("03/02", "description"));
    expect(within(cellOf("03/02", "description")).queryByRole("textbox")).toBeNull();
    expect(fetch.mock.calls.filter(([, init]) => init?.method === "POST")).toEqual([]);
    await user.click(cellOf("03/02", "rate"));
    const dialog = await screen.findByRole("dialog", { name: texts.sheetSource.ar });
    expect(dialog).toHaveTextContent("مقايسة العميل - عينة.xlsx");
    await user.click(within(dialog).getByRole("button", { name: texts.sourceOpenFile.ar }));
    expect(openFile).toHaveBeenCalledWith("file:f1", {});
    openFile.mockRestore();
  });

  it("a computed amount never opens an editor", async () => {
    const user = userEvent.setup();
    render(<SheetViewer projectId={P} view={sheet()} />);
    await user.dblClick(cellOf("03/02", "amount"));
    expect(within(cellOf("03/02", "amount")).queryByRole("textbox")).toBeNull();
    expect(cellOf("03/02", "amount")).toHaveAttribute("aria-readonly", "true");
  });

  it("the grid is one Tab stop: the buttons in its cells (fold, ✓ ✗, the total) are reached on the active cell only", async () => {
    const user = userEvent.setup();
    const { container } = render(<SheetViewer projectId={P} view={sheet({ pending: 1 })} changes={[change("c1")]} />);
    const grid = container.querySelector<HTMLElement>(".rdg")!;
    const tabbable = () => [...grid.querySelectorAll<HTMLElement>("button, [tabindex]")].filter((el) => el.tabIndex >= 0);
    expect(grid.querySelectorAll("button").length).toBeGreaterThan(2); // folds, ✓ ✗ and the total are there
    expect(tabbable().filter((el) => el.matches("button"))).toEqual([]);
    // on the active cell its button is the next Tab stop, and only its
    await user.click(cellOf("03/02", "rate"));
    expect(tabbable().filter((el) => el.matches("button")).map((el) => el.getAttribute("aria-label"))).toEqual([texts.sheetAccept.ar, texts.sheetReject.ar]);
  });

  it("✓ accepts and ✗ rejects that change only", async () => {
    const user = userEvent.setup();
    const onChanged = vi.fn();
    const fetch = core({
      [`POST ${base}/deliverables/${D}/changes/accept`]: () => Response.json({ version: 2, accepted: ["c1"], stale: [] }),
      [`POST ${base}/deliverables/${D}/changes/reject`]: () => Response.json({ rejected: ["c2"] }),
    });
    const quantity = change("c2", {
      op: { op: "set_number", row: "p2", name: "quantity", value: "6000", unit: "m3", expect: "n-q1" },
      author: "lead_qs",
      before: n("5555", "n-q1", { unit: "m3" }),
      after: { value: "6000", unit: "m3", number_id: "", source: "", dated: null },
      follows: [],
    });
    render(<SheetViewer projectId={P} view={sheet({ pending: 2 })} changes={[change("c1"), quantity]} onChanged={onChanged} />);
    await user.click(within(cellOf("03/02", "rate")).getByRole("button", { name: texts.sheetAccept.ar }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(1));
    expect(bodies(fetch, "POST", `${base}/deliverables/${D}/changes/accept`)).toEqual([{ ids: ["c1"] }]);
    expect(cellOf("03/02", "rate").querySelector("del")).toBeNull();
    expect(cellOf("1-1", "quantity").querySelector("del")).toHaveTextContent("5,555");
    await user.click(within(cellOf("1-1", "quantity")).getByRole("button", { name: texts.sheetReject.ar }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(2));
    expect(bodies(fetch, "POST", `${base}/deliverables/${D}/changes/reject`)).toEqual([{ ids: ["c2"] }]);
    expect(cellOf("1-1", "quantity").querySelector("del")).toBeNull();
    expect(screen.queryByRole("dialog")).toBeNull(); // ✓ and ✗ are not clicks on the number
  });

  it("an update from Project Records paints each moved cell", () => {
    const records = change("c9", {
      op: {
        op: "update_from_records",
        cells: [{ row: "p2", column: "rate", before: n("14", "n-r1"), after: n("15", "n-r9"), why: { corrected: "عرض جديد - عينة" } }],
      },
      author: "calc_engine",
      before: null, after: null, follows: [],
    });
    render(<SheetViewer projectId={P} view={sheet()} changes={[records]} />);
    expect(cellOf("1-1", "rate").querySelector("del")).toHaveTextContent("14");
    expect(cellOf("1-1", "rate").querySelector("ins")).toHaveTextContent("15");
  });

  it("the source popover shows the source and date, and the formula for an amount", async () => {
    const user = userEvent.setup();
    const explained = (id: string, calculation: Explained["calculation"], recorded_by = "estimator"): Explained => ({
      number: { id, item: { id: "i4", code: "03/02", kind: "boq_item" }, name: "x", value: "0", unit: null, currency: "EGP", dated: "2026-11-01", recorded_at: "2026-11-01T08:00:00+00:00", recorded_by, current: true, replaced_by: null, reason: null },
      source: { id: "s", kind: calculation ? "calculation" : "sample", title: calculation ? "quantity * rate" : "بيانات تجريبية - عينة", file_id: null, locator: {}, url: null, dated: null },
      calculation,
    });
    const fetch = core({
      [`GET ${base}/numbers/n-rate/explain`]: () => Response.json(explained("n-rate", null)),
      [`GET ${base}/numbers/n-amount/explain`]: () =>
        Response.json(
          explained("n-amount", {
            id: "c1", formula: "quantity * rate", unit: "EGP", stale: false, page: 1, pages: 1,
            inputs: [
              { name: "quantity", seq: null, number: "n-q2", value: "120", unit: "m3", dated: "2026-11-01", source: { kind: "sample", title: "كميات - عينة" }, calculated: false },
              { name: "rate", seq: null, number: "n-rate", value: "39850.50", unit: "EGP/m3", dated: "2026-11-01", source: { kind: "sample", title: "بيانات تجريبية - عينة" }, calculated: false },
            ],
            steps: [{ n: 1, text: "quantity * rate", op: "*", value: "4782060.00", unit: "EGP" }],
          }, "calc_engine"),
        ),
    });
    render(<SheetViewer projectId={P} view={sheet()} />);
    await user.click(cellOf("03/02", "rate"));
    let dialog = await screen.findByRole("dialog", { name: texts.sheetSource.ar });
    expect(dialog).toHaveTextContent("بيانات تجريبية - عينة");
    expect(dialog).toHaveTextContent("عرض سعر - عينة.pdf");
    expect(dialog).toHaveTextContent("صفحة 3");
    expect(dialog).toHaveTextContent("بتاريخ 1 نوفمبر 2026");
    await waitFor(() => expect(dialog).toHaveTextContent(fill(texts.sheetEnteredBy.ar, { who: "estimator" })));
    expect(dialog.parentElement).toBe(document.body); // in the top layer: no frame or box cuts it
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();

    await user.click(cellOf("03/02", "amount"));
    dialog = await screen.findByRole("dialog");
    await waitFor(() => expect(dialog).toHaveTextContent("الكمية × الفئة = 4,782,060.00 ج.م.")); // in words
    expect(dialog).toHaveTextContent(texts.sheetFormula.ar);
    expect(dialog).toHaveTextContent("39,850.50 ج.م./m3");
    expect(dialog).toHaveTextContent("كميات - عينة");
    expect(dialog).toHaveTextContent(texts.enteredByCalc.ar);
    expect(fetch.mock.calls.map(([u]) => String(u))).toContain(`${base}/numbers/n-amount/explain?page=1`);
  });

  it("a number focused from the keyboard draws its source line to its file's row on the canvas, and opens labelled", async () => {
    const user = userEvent.setup();
    core({});
    const quote = { kind: "quote", title: "عرض سعر - عينة", file_id: "f1", locator: { sheet: "Quote", row: 7 }, url: null, dated: null };
    render(<SheetViewer projectId={P} view={sheet({ sources: { ...sheet().sources, s1: quote } })} />);
    const row = document.createElement("li"); // the quote's row, as its file's frame on the canvas shows it
    row.setAttribute("data-source-at", "file:f1#sheet=Quote&row=7");
    document.body.append(row);
    const boxes = vi.spyOn(Element.prototype, "getBoundingClientRect").mockImplementation(function (this: Element) {
      if (this === row) return new DOMRect(40, 500, 300, 30);
      if (this.matches('[role="gridcell"]')) return new DOMRect(600, 100, 110, 30);
      return new DOMRect(0, 0, 0, 0);
    });
    await user.click(cellOf("03/02", "unit"));
    await user.keyboard("{ArrowLeft}{ArrowLeft}");
    const line = () => document.querySelector('svg[data-source-overlay] [data-source="line"]');
    await waitFor(() => expect(line()).not.toBeNull());
    await user.keyboard(" ");
    const dialog = await screen.findByRole("dialog", { name: texts.sheetSource.ar });
    expect(dialog).toHaveTextContent("الفئة"); // what the number is, in the card's header
    boxes.mockRestore();
    row.remove();
  });

  it("Space opens a number's source from the keyboard, and Esc gives the focus back", async () => {
    const user = userEvent.setup();
    core({});
    render(<SheetViewer projectId={P} view={sheet()} />);
    await user.click(cellOf("03/02", "unit"));
    await user.keyboard("{ArrowLeft}{ArrowLeft} ");
    const dialog = await screen.findByRole("dialog", { name: texts.sheetSource.ar });
    expect(dialog).toHaveFocus();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(cellOf("03/02", "rate")).toHaveFocus();
  });

  it("a long Arabic description gets a taller row, so it is never cut", () => {
    const long = "بالمتر المكعب توريد وصب خرسانة مسلحة للأساسات والسملات - عينة ".repeat(8);
    const view = sheet({ rows: rows.map((r) => (r.id === "p4" ? { ...r, cells: { ...r.cells, description: { text: long } } } : r)) });
    render(<SheetViewer projectId={P} view={view} />);
    const heights = [...screen.getByRole("grid").style.gridTemplateRows.matchAll(/(\d+)px/g)].map((m) => Number(m[1]));
    expect(Math.max(...heights)).toBeGreaterThan(100);
  });

  it("Shift+arrows extend the range, mirrored in RTL, and Shift+click extends it too", async () => {
    const user = userEvent.setup();
    const onSelection = vi.fn();
    render(<SheetViewer projectId={P} view={sheet()} onSelection={onSelection} />);
    await user.click(cellOf("03/02", "unit"));
    await user.keyboard("{ArrowLeft}"); // the quantity: left is the next column in RTL
    await user.keyboard("{Shift>}{ArrowLeft}{ArrowDown}{/Shift}");
    const selected = () =>
      screen.getAllByRole("gridcell").filter((c) => c.querySelector("[data-selected]")).map((c) => c.getAttribute("aria-colindex"));
    expect(selected()).toEqual([String(col("quantity")), String(col("rate")), String(col("quantity")), String(col("rate"))]);
    expect(onSelection).toHaveBeenLastCalledWith({ from: { row: "p4", column: "quantity" }, to: { row: "p5", column: "rate" } });
    await user.keyboard("{Shift>}");
    await user.click(cellOf("1-1", "description"));
    await user.keyboard("{/Shift}");
    expect(onSelection).toHaveBeenLastCalledWith({ from: { row: "p2", column: "description" }, to: { row: "p4", column: "quantity" } });
  });

  it("dragging with the mouse selects a range", () => {
    const onSelection = vi.fn();
    render(<SheetViewer projectId={P} view={sheet()} onSelection={onSelection} />);
    fireEvent.mouseDown(cellOf("1-1", "unit"), { button: 0 });
    fireEvent.mouseOver(within(cellOf("03/02", "rate")).getByText("39,850.50"), { buttons: 1 });
    fireEvent.mouseUp(window);
    fireEvent.mouseOver(cellOf("03/03", "rate"), { buttons: 0 }); // the button is up: the range stays
    expect(onSelection).toHaveBeenLastCalledWith({ from: { row: "p2", column: "unit" }, to: { row: "p4", column: "rate" } });
  });

  it("copies the range as TSV and an RTL HTML table", async () => {
    const user = userEvent.setup();
    render(<SheetViewer projectId={P} view={sheet()} />);
    await user.click(cellOf("03/02", "unit"));
    await user.keyboard("{ArrowLeft}{Shift>}{ArrowLeft}{ArrowLeft}{ArrowDown}{/Shift}");
    const data = new Map<string, string>();
    fireEvent.copy(cellOf("03/02", "quantity"), { clipboardData: { setData: (k: string, v: string) => data.set(k, v) } });
    expect(data.get("text/plain")).toBe("120\t39850.50\t4782060.00\r\nفئة فقط\t250\t"); // exact strings, as Excel takes them
    expect(data.get("text/html")).toContain('<table dir="rtl">');
  });

  it("a paste over the amount column sends one change with the rest and names the refused cells", async () => {
    const user = userEvent.setup();
    const fetch = core({ [`POST ${base}/deliverables/${D}/changes`]: () => Response.json({ changes: [] }, { status: 201 }) });
    render(<SheetViewer projectId={P} view={sheet()} />);
    await user.click(cellOf("03/02", "unit"));
    await user.keyboard("{ArrowLeft}{ArrowLeft}");
    fireEvent.paste(cellOf("03/02", "rate"), { clipboardData: { getData: () => "40000\t1\r\n٣٩٨٥١٫٠٠\t2\r\n" } });
    await waitFor(() => expect(bodies(fetch, "POST", `${base}/deliverables/${D}/changes`)).toHaveLength(1));
    expect(bodies(fetch, "POST", `${base}/deliverables/${D}/changes`)[0]).toEqual({
      ops: [
        { op: "set_number", row: "p4", name: "rate", value: "40000", unit: "m3", currency: "EGP", expect: "n-rate" },
        { op: "set_number", row: "p5", name: "rate", value: "39851.00", unit: "م2", currency: "EGP", expect: "n-r3" },
      ],
      reason: null,
    });
    expect(screen.getByRole("alert")).toHaveTextContent(
      `ماتلصقش في 03/02 الإجمالي، 03/03 الإجمالي: ${texts.sheetAmountComputed.ar}`,
    );
  });

  it("a refused change says why in the core's words", async () => {
    const user = userEvent.setup();
    const line = { en: "Send the number as text.", ar: "ابعت الرقم كنص." };
    core({ [`POST ${base}/deliverables/${D}/changes`]: () => Response.json({ error: line, field: "ops[0].value" }, { status: 422 }) });
    render(<SheetViewer projectId={P} view={sheet()} />);
    await user.click(cellOf("03/02", "unit"));
    await user.keyboard("{ArrowLeft}{ArrowLeft}");
    fireEvent.paste(cellOf("03/02", "rate"), { clipboardData: { getData: () => "5" } });
    expect(await screen.findByRole("alert")).toHaveTextContent(line.ar);
  });

  it("collapsing a section hides its items and is remembered", async () => {
    const user = userEvent.setup();
    const { unmount } = render(<SheetViewer projectId={P} view={sheet()} />);
    const fold = within(cellOf("أعمال الحفر", "code")).getByRole("button", { name: `${texts.sheetCollapse.ar}: أعمال الحفر` });
    expect(fold).toHaveAttribute("aria-expanded", "true");
    expect(fold).toHaveTextContent("▾");
    await user.click(fold);
    expect(screen.queryByText("1-1")).toBeNull();
    expect(screen.getByText("03/02")).toBeInTheDocument();
    const open = within(cellOf("أعمال الحفر", "code")).getByRole("button", { name: `${texts.sheetExpand.ar}: أعمال الحفر` });
    expect(open).toHaveTextContent("◂"); // points along the reading direction
    unmount();
    render(<SheetViewer projectId={P} view={sheet()} />);
    expect(screen.queryByText("1-1")).toBeNull();
  });

  it("open comments mark their cells, One's notes differently, each with a text label", () => {
    const thread = (id: string, kind: "note" | "review", anchor: Thread["anchor"]): Thread => ({
      id, deliverable_id: D, parent_id: null, kind, anchor, anchor_now: anchor, body: "راجع - عينة", author: "engineer",
      code: null, check_id: null, status: "open", version_n: 1, created_at: "", closed_at: null, closed_by: null, fix_asked_at: null, replies: [],
    });
    render(
      <SheetViewer
        projectId={P}
        view={sheet()}
        comments={[
          thread("t1", "review", { type: "range", from: { row: "p4", column: "quantity" }, to: { row: "p4", column: "rate" } }),
          thread("t2", "note", { type: "cell", row: "p4", column: "rate" }),
          { ...thread("t3", "review", { type: "cell", row: "p2", column: "rate" }), status: "closed" },
        ]}
      />,
    );
    expect(within(cellOf("03/02", "quantity")).getByText(texts.reviewComment.ar)).toHaveClass("sr-only");
    expect(within(cellOf("03/02", "rate")).getByText(texts.reviewNote.ar)).toBeInTheDocument();
    expect(within(cellOf("1-1", "rate")).queryByText(texts.reviewComment.ar)).toBeNull();
  });

  it("locate finds a cell's box in the viewer, and null for an unknown row", () => {
    const ref = createRef<SheetHandle>();
    render(<SheetViewer projectId={P} view={sheet()} ref={ref} />);
    expect(ref.current!.locate({ row: "p4", column: "rate" })).toBeInstanceOf(DOMRect);
    expect(ref.current!.locate({ row: "p4" })).toBeInstanceOf(DOMRect);
    expect(ref.current!.locate({ row: "nope", column: "rate" })).toBeNull();
    expect(ref.current!.locate({ row: "p4", column: "nope" })).toBeNull();
  });

  it("the full-screen toggle says which way it goes", async () => {
    const user = userEvent.setup();
    const toggle = vi.fn();
    const { rerender } = render(<SheetViewer projectId={P} view={sheet()} onToggleFullScreen={toggle} />);
    await user.click(screen.getByRole("button", { name: texts.sheetFullScreen.ar }));
    expect(toggle).toHaveBeenCalled();
    rerender(<SheetViewer projectId={P} view={sheet()} mode="full" onToggleFullScreen={toggle} />);
    expect(screen.getByRole("button", { name: texts.sheetLeaveFullScreen.ar })).toHaveAttribute("aria-pressed", "true");
  });
});

describe("deliverables api", () => {
  it("reads an Arabic file name from Content-Disposition", () => {
    expect(dispositionName(`attachment; filename="x.xlsx"; filename*=UTF-8''%D9%85%D8%B3%D9%88%D8%AF%D8%A9.xlsx`, "f")).toBe("مسودة.xlsx");
    expect(dispositionName('attachment; filename="BOQ.pdf"', "f")).toBe("BOQ.pdf");
    expect(dispositionName(null, "f.pdf")).toBe("f.pdf");
  });

  it("answers the core's refusal, or a plain line when the core is away", async () => {
    core({});
    expect(await deliverablesApi.list(P)).toMatchObject({ ok: false, error: texts.sheetNoAnswer, status: 404 });
    vi.stubGlobal("fetch", vi.fn(async () => Promise.reject(new Error("down"))));
    expect(await deliverablesApi.view(P, D)).toMatchObject({ ok: false, error: texts.sheetNoAnswer, status: 0 });
  });
});
