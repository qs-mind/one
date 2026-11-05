// Fake project sources: for tests (given lists, recorded saves, events a test emits) and for the dev-only sample
// mode (?sample=1), where every title says it is a sample and the screen shows the "Sample data" label.
import type { SheetView } from "../deliverables/types";
import type {
  ActivityEvent,
  AgentInfo,
  ClientBoqInfo,
  DeliverableInfo,
  FileInfo,
  FilePiece,
  FrameKey,
  Placed,
  ProjectSources,
  ProjectStatus,
  Team,
  View,
} from "./types";

export type FakeOptions = {
  files?: FileInfo[];
  deliverables?: DeliverableInfo[];
  team?: Team;
  status?: ProjectStatus;
  layout?: { frames: Placed[]; view: View | null };
  /** Page counts by file id; a file not listed has no pages. */
  pages?: Record<string, number>;
  text?: Record<string, FilePiece[]>;
  /** The imported client BOQs, and each one's read-only Sheet view by file id. */
  clientBoqs?: ClientBoqInfo[];
  clientBoqViews?: Record<string, SheetView>;
};

export type FakeSources = ProjectSources & {
  /** Hands an event to every live listener. */
  emit(event: ActivityEvent): void;
  /** Tells every live listener that the stream came back. */
  reconnect(): void;
  saved: {
    frames: { frames: Placed[]; removed: FrameKey[]; keepalive: boolean }[];
    views: { view: View; keepalive: boolean }[];
  };
  uploads: File[];
};

export function fakeSources(options: FakeOptions): FakeSources {
  const files = [...(options.files ?? [])];
  const frames = new Map((options.layout?.frames ?? []).map((f) => [f.key, f]));
  let view = options.layout?.view ?? null;
  const listeners = new Set<{ onEvent: (event: ActivityEvent) => void; onReconnect?: () => void }>();
  const saved: FakeSources["saved"] = { frames: [], views: [] };
  const uploads: File[] = [];

  return {
    files: async () => [...files],
    deliverables: async () => [...(options.deliverables ?? [])],
    team: async () => options.team ?? { desks: [], agents: [] },
    status: async () => options.status ?? {},
    layout: async () => ({ frames: [...frames.values()], view, client_boqs: [...(options.clientBoqs ?? [])] }),
    async saveFrames(changed, removed, keepalive = false) {
      saved.frames.push({ frames: changed, removed, keepalive });
      for (const key of removed) frames.delete(key);
      for (const f of changed) frames.set(f.key, f);
    },
    async saveView(next, keepalive = false) {
      saved.views.push({ view: next, keepalive });
      view = next;
    },
    activity(onEvent, signal, onReconnect) {
      if (signal.aborted) return;
      const entry = { onEvent, onReconnect };
      listeners.add(entry);
      signal.addEventListener("abort", () => listeners.delete(entry), { once: true });
    },
    pageImage: async (fileId, page, width) => `data:image/png;fake,${fileId}/${page}/${width}`,
    pages: async (fileId) => options.pages?.[fileId] ?? 0,
    fileText: async (fileId, page) =>
      (options.text?.[fileId] ?? []).filter((p) => page === undefined || p.locator.page === page),
    async clientBoq(fileId) {
      const found = options.clientBoqViews?.[fileId];
      if (!found) throw new Error(`no client BOQ ${fileId}`);
      return found;
    },
    async upload(file) {
      uploads.push(file);
      const info: FileInfo = { id: `upload${uploads.length}`, name: file.name, status: "stored", note: null, replaces: null };
      files.unshift(info);
      return info;
    },
    emit(event) {
      for (const l of [...listeners]) l.onEvent(event);
    },
    reconnect() {
      for (const l of [...listeners]) l.onReconnect?.();
    },
    saved,
    uploads,
  };
}

// The dev sample mode ------------------------------------------------------------------------------------------

const at = "2026-11-05T09:00:00+00:00";

function deliverable(fields: Partial<DeliverableInfo> & Pick<DeliverableInfo, "id" | "kind" | "title">): DeliverableInfo {
  return {
    language: "ar",
    status: "draft",
    code: null,
    same_provider: false,
    revision: null,
    desk: null,
    off_desk: false,
    progress: null,
    open_comments: 0,
    updated_at: at,
    pending: 0,
    total: null,
    sample: true,
    ...fields,
  };
}

const pricingDesk = { en: "Pricing Desk (sample)", ar: "قسم التسعير - عينة" };

function agent(fields: Partial<AgentInfo> & Pick<AgentInfo, "id" | "kind" | "role">): AgentInfo {
  return {
    desk_id: null,
    model: "claude-sonnet-5",
    state: "working",
    line: null,
    brief_id: "sample-brief",
    focus: null,
    at,
    ...fields,
  };
}

/** A small tender, every name marked as a sample. Only for the dev sample mode, which labels the screen. */
export function sampleSources(): FakeSources {
  const days = 13;
  const submission = new Date(Date.now() + days * 86_400_000).toISOString().slice(0, 10);
  return fakeSources({
    files: [
      { id: "spec", name: "المواصفات الفنية - عينة.pdf", status: "read", note: null, replaces: null },
      { id: "boq", name: "مقايسة العميل - عينة.xlsx", status: "read", note: null, replaces: null },
      { id: "dwg", name: "لوحات معمارية A-101 - عينة.pdf", status: "partly_read", note: null, replaces: null },
      { id: "quote", name: "عرض سعر حديد - عينة.pdf", status: "read", note: null, replaces: null },
    ],
    pages: { spec: 18, dwg: 6, quote: 2 },
    text: {
      spec: [{ locator: { page: 1 }, text: "القسم ٣: الخرسانة المسلحة - نص عينة" }],
      boq: [{ locator: { sheet: "BOQ", row: 12 }, text: "3/02 خرسانة مسلحة للأعمدة - عينة" }],
    },
    deliverables: [
      deliverable({
        id: "takeoff",
        kind: "sheet",
        title: "ملخص الحصر - عينة",
        status: "signed_off",
        code: "A",
        revision: 1,
        progress: { done: 64, total: 64 },
      }),
      deliverable({
        id: "pricing",
        kind: "sheet",
        title: "تسعير المقايسة - عينة",
        status: "checked",
        code: "B",
        desk: pricingDesk,
        progress: { done: 180, total: 420 },
        open_comments: 1,
      }),
      deliverable({
        id: "quotes",
        kind: "sheet",
        title: "مقارنة عروض الموردين - عينة",
        desk: pricingDesk,
        progress: { done: 3, total: 5 },
      }),
      deliverable({ id: "letter", kind: "document", title: "خطاب العطاء - مسودة عينة" }),
    ],
    team: {
      desks: [{ id: "pricing-sample", name: pricingDesk, stage: "temporary" }],
      agents: [
        agent({
          id: "est",
          kind: "specialist",
          role: { en: "Estimator (sample)", ar: "مهندس التسعير - عينة" },
          desk_id: "pricing-sample",
          line: { en: "Pricing item 3/02 (sample)", ar: "بيسعّر البند 3/02 - عينة" },
          focus: { frame: "deliverable:pricing", anchor: null },
        }),
        agent({
          id: "chk",
          kind: "checker",
          role: { en: "Checking QS (sample)", ar: "مهندس المراجعة - عينة" },
          state: "thinking",
          focus: { frame: "deliverable:pricing", anchor: null },
        }),
        agent({
          id: "proc",
          kind: "specialist",
          role: { en: "Procurement QS (sample)", ar: "مهندس التوريد - عينة" },
          desk_id: "pricing-sample",
          focus: { frame: "deliverable:quotes", anchor: null },
        }),
      ],
    },
    status: {
      stage: { en: "Tender (sample)", ar: "مناقصة - عينة" },
      submission_date: submission,
      days_left: days,
      boq_value: { value: "48200000.00", currency: "EGP", deliverable_id: "pricing", revision: null, status: "checked" },
      open_comments: 1,
      waiting: 2,
    },
  });
}
