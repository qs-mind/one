// Test data for the review screens, shaped like the core's answers (Plan 6 Task 7): «عينة» in names, sources of
// kind sample. Used by tests only; nothing here is real.
import { vi } from "vitest";
import type { Change, DeliverableInfo, DocumentView, SheetView, Thread, ViewColumn, ViewRow } from "./types";

export const P = "p1";
export const D = "d".repeat(32);
export const DOC = "c".repeat(32);
export const base = `/api/projects/${P}`;

export const columns: ViewColumn[] = [
  { key: "code", label: { en: "Item", ar: "البند" }, kind: "text", edit: false, frozen: true, wrap: false, width: 70, from: "code" },
  { key: "description", label: { en: "Description", ar: "بيان الأعمال" }, kind: "text", edit: true, frozen: false, wrap: true, width: 420, from: "field:description" },
  { key: "unit", label: { en: "Unit", ar: "الوحدة" }, kind: "text", edit: false, frozen: false, wrap: false, width: 60, from: "number:quantity.unit" },
  { key: "quantity", label: { en: "Qty", ar: "الكمية" }, kind: "number", edit: true, frozen: false, wrap: false, width: 90, from: "number:quantity" },
  { key: "rate", label: { en: "Rate", ar: "الفئة" }, kind: "number", edit: true, frozen: false, wrap: false, width: 110, from: "number:rate" },
  { key: "amount", label: { en: "Amount", ar: "الإجمالي" }, kind: "calc", edit: false, frozen: false, wrap: false, width: 130, from: "number:amount" },
];

export const n = (value: string, id: string | null, more: object = {}) => ({ value, number_id: id, source: id && "s1", dated: "2026-11-01", ...more });
export const calc = (value: string, id: string | null) => n(value, id, { currency: "EGP", source: id && "s3", calculated: true });

const item = (id: string, code: string, text: string, qty: string, rate: string, amount: string): ViewRow => ({
  id, kind: "item", item_id: `i-${id}`, item_version: 1, version: 1, code,
  cells: {
    description: { text },
    unit: { text: "m3" },
    quantity: n(qty, `q-${id}`, { unit: "m3" }),
    rate: n(rate, `r-${id}`, { unit: "m3", currency: "EGP" }),
    amount: calc(amount, `a-${id}`),
  },
});

export const rows: ViewRow[] = [
  { id: "p1", kind: "section", level: 1, item_id: "i1", title: "أعمال الخرسانة", version: 1, cells: { amount: calc("4859830.00", "s-1") } },
  item("p2", "03/01", "خرسانة عادية تحت الأساسات - عينة", "30", "2589.00", "77670.00"),
  item("p3", "03/02", "خرسانة مسلحة للأساسات - عينة", "120", "39850.50", "4782060.00"),
  item("p4", "03/04", "خرسانة مسلحة للأعمدة - عينة", "0", "100", "100.00"),
  { id: "p5", kind: "section", level: 1, item_id: "i5", title: "أعمال العزل", version: 1, cells: {} }, // nothing priced yet
];

export function sheet(more: Partial<SheetView> = {}): SheetView {
  return {
    id: D, kind: "sheet", variant: "boq", title: "جدول الكميات - عينة", language: "ar",
    status: "draft", code: null, same_provider: false, off_desk: false,
    version: 3, at: "2026-11-05T09:00:00.000000+00:00", revision: null, sample: true,
    columns, rows,
    total: calc("4859830.00", "n-total"),
    sources: {
      s1: { kind: "sample", title: "بيانات تجريبية - عينة", file_name: null, locator: {}, url: null, dated: null },
      s3: { kind: "calculation", title: "quantity * rate", locator: { calculation: "c1" } },
    },
    incomplete: {}, pending: 0, open_comments: 0, records_moved: false,
    ...more,
  };
}

export function letter(more: Partial<DocumentView> = {}): DocumentView {
  return {
    id: DOC, kind: "document", variant: "letter", title: "خطاب العطاء - عينة", language: "ar",
    status: "draft", code: null, same_provider: false, off_desk: false,
    version: 2, at: "2026-11-05T09:00:00.000000+00:00", revision: null, sample: true,
    blocks: [
      { id: "b1", version: 1, node: { type: "h1", children: [{ text: "خطاب تقديم العطاء - عينة" }] } },
      { id: "b2", version: 1, node: { type: "p", children: [{ text: "الأسعار سارية حالياً لمدة ٣٠ يوماً" }] } },
    ],
    refs: {}, untraced: [], sources: {}, pending: 0, open_comments: 0, records_moved: false, progress: null,
    ...more,
  };
}

export function change(id: string, more: Partial<Change> = {}): Change {
  return {
    id, deliverable_id: D,
    op: { op: "set_number", row: "p3", name: "rate", value: "40000", unit: "m3", currency: "EGP", expect: "r-p3" },
    reason: null, author: "engineer", comment_id: null, status: "pending",
    created_at: "2026-11-05T09:01:00.000000+00:00", decided_at: null, decided_by: null, version_n: null,
    before: n("39850.50", "r-p3", { unit: "m3", currency: "EGP" }),
    after: { value: "40000", unit: "m3", currency: "EGP", number_id: null, source: null, dated: null },
    follows: [{ row: "p3", column: "amount", before: calc("4782060.00", "a-p3"), after: calc("4800000.00", null) }],
    ...more,
  };
}

export function thread(id: string, more: Partial<Thread> = {}): Thread {
  const anchor = more.anchor ?? { type: "cell", row: "p3", column: "rate" };
  return {
    id, deliverable_id: D, parent_id: null, kind: "review", anchor, body: "راجع الفئة - عينة", author: "engineer",
    code: null, check_id: null, status: "open", version_n: 3,
    created_at: "2026-11-05T09:02:00.000000+00:00", closed_at: null, closed_by: null, fix_asked_at: null,
    anchor_now: anchor, replies: [],
    ...more,
  };
}

export function entry(more: Partial<DeliverableInfo> = {}): DeliverableInfo {
  return {
    id: D, kind: "sheet", title: "جدول الكميات - عينة", language: "ar", status: "draft", code: null,
    same_provider: false, revision: null, desk: null, off_desk: false, progress: { done: 2, total: 3 },
    open_comments: 1, updated_at: "2026-11-05T09:00:00.000000+00:00", pending: 2, sample: true,
    ...more,
  };
}

export const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

export type Route = (url: string, init: RequestInit) => Response | Promise<Response>;

/** A fetch that answers `"METHOD /path"` routes (query left out); anything else is a 404. */
export function core(routes: Record<string, Route>) {
  const fetch = vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = String(input);
    const route = routes[`${init.method ?? "GET"} ${url.split("?")[0]}`];
    return route ? route(url, init) : new Response("not found", { status: 404 });
  });
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

/** The JSON bodies sent with `method` to `path`. */
export const bodies = (fetch: ReturnType<typeof core>, method: string, path: string) =>
  fetch.mock.calls
    .filter(([u, init]) => String(u).split("?")[0] === path && (init?.method ?? "GET") === method)
    .map(([, init]) => (init?.body ? (JSON.parse(String(init.body)) as unknown) : undefined));

/** The routes a Deliverable's viewer loads: its view, its changes (pending and stale) and its comments. */
export function viewRoutes(view: SheetView | DocumentView, more: { pending?: Change[]; stale?: Change[]; comments?: Thread[] } = {}) {
  const d = `${base}/deliverables/${view.id}`;
  return {
    [`GET ${d}`]: () => json(view),
    [`GET ${d}/changes`]: (url: string) =>
      json({ changes: url.includes("status=stale") ? (more.stale ?? []) : (more.pending ?? []) }),
    [`GET ${d}/comments`]: () => json({ comments: more.comments ?? [] }),
  } satisfies Record<string, Route>;
}

/** A live stream the test controls: `emit` sends one event to every listener of the project. */
export function fakeLive() {
  const listeners = new Set<(event: unknown) => void>();
  const subscribe = vi.fn((_project: string, listener: (event: never) => void) => {
    const l = listener as (event: unknown) => void;
    listeners.add(l);
    return () => void listeners.delete(l);
  });
  return { subscribe, emit: (event: unknown) => listeners.forEach((l) => l(event)) };
}
