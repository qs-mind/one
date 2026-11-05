// Typed calls for every Deliverables route of the core (Plan 6 Task 7), plus Plan 3's explain, all under /api.
// A call never throws: it answers the data, or the core's refusal ({error: {en, ar}, field}) in plain words.
import { texts, type Text } from "../i18n";
import type {
  Change,
  CloseOut,
  Compare,
  CommentAnchor,
  DeliverableInfo,
  Explained,
  FillPlanInfo,
  FillPreview,
  Op,
  Thread,
  Versions,
  View,
} from "./types";

export type Answer<T> = { ok: true; data: T } | { ok: false; error: Text; field: string | null; status: number };
export type FileBytes = { bytes: Uint8Array; name: string; type: string };

const base = (p: string) => `/api/projects/${encodeURIComponent(p)}`;
const id = encodeURIComponent;

async function refusal(response: Response | undefined): Promise<Answer<never>> {
  const body = (await response?.json().catch(() => undefined)) as { error?: Partial<Text>; field?: unknown } | undefined;
  const line = body?.error;
  const error = typeof line?.en === "string" && typeof line.ar === "string" ? (line as Text) : texts.sheetNoAnswer;
  return { ok: false, error, field: typeof body?.field === "string" ? body.field : null, status: response?.status ?? 0 };
}

async function call<T>(url: string, method = "GET", body?: unknown): Promise<Answer<T>> {
  const response = await fetch(url, {
    method,
    ...(body === undefined ? {} : { headers: { "content-type": "application/json" }, body: JSON.stringify(body) }),
  }).catch(() => undefined);
  if (!response?.ok) return refusal(response);
  return { ok: true, data: (await response.json()) as T };
}

/** The file name from Content-Disposition, preferring the RFC 5987 UTF-8 form (Arabic names). */
export function dispositionName(header: string | null, fallback: string): string {
  const utf8 = /filename\*\s*=\s*UTF-8''([^;]+)/i.exec(header ?? "");
  if (utf8) {
    try {
      return decodeURIComponent(utf8[1]!.trim());
    } catch {
      // a broken escape: fall through to the plain name
    }
  }
  const plain = /filename\s*=\s*"?([^";]+)"?/i.exec(header ?? "");
  return plain ? plain[1]!.trim() : fallback;
}

async function bytes(url: string, fallback: string): Promise<Answer<FileBytes>> {
  const response = await fetch(url).catch(() => undefined);
  if (!response?.ok) return refusal(response);
  return {
    ok: true,
    data: {
      bytes: new Uint8Array(await response.arrayBuffer()),
      name: dispositionName(response.headers.get("content-disposition"), fallback),
      type: response.headers.get("content-type") ?? "application/octet-stream",
    },
  };
}

const query = (values: Record<string, string | number | null | undefined>) => {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(values)) if (v !== undefined && v !== null) q.set(k, String(v));
  const s = q.toString();
  return s ? `?${s}` : "";
};

export const deliverablesApi = {
  list: (p: string) => call<{ deliverables: DeliverableInfo[] }>(`${base(p)}/deliverables`),
  view: (p: string, d: string, at: { version?: number; revision?: number } = {}) =>
    call<View>(`${base(p)}/deliverables/${id(d)}${query(at)}`),
  changes: (p: string, d: string, status?: "pending" | "stale") =>
    call<{ changes: Change[] }>(`${base(p)}/deliverables/${id(d)}/changes${query({ status })}`),
  propose: (p: string, d: string, ops: Op[], reason: string | null = null) =>
    call<{ changes: Change[] }>(`${base(p)}/deliverables/${id(d)}/changes`, "POST", { ops, reason }),
  accept: (p: string, d: string, which: { ids: string[] } | { mine: true }) =>
    call<{ version: number | null; accepted: string[]; stale: string[] }>(
      `${base(p)}/deliverables/${id(d)}/changes/accept`,
      "POST",
      which,
    ),
  reject: (p: string, d: string, ids: string[]) =>
    call<{ rejected: string[] }>(`${base(p)}/deliverables/${id(d)}/changes/reject`, "POST", { ids }),
  versions: (p: string, d: string) => call<Versions>(`${base(p)}/deliverables/${id(d)}/versions`),
  /** from and to are "v:<n>" (a Saved version) or "r:<n>" (a Revision). */
  compare: (p: string, d: string, from: string, to: string) =>
    call<Compare>(`${base(p)}/deliverables/${id(d)}/compare${query({ from, to })}`),
  comments: (p: string, d: string, status?: "open") =>
    call<{ comments: Thread[] }>(`${base(p)}/deliverables/${id(d)}/comments${query({ status })}`),
  comment: (p: string, d: string, anchor: CommentAnchor, body: string, code: "C" | null = null) =>
    call<Thread>(`${base(p)}/deliverables/${id(d)}/comments`, "POST", { anchor, body, code }),
  reply: (p: string, c: string, body: string) => call<Thread>(`${base(p)}/comments/${id(c)}/replies`, "POST", { body }),
  close: (p: string, c: string) => call<Thread>(`${base(p)}/comments/${id(c)}/close`, "POST"),
  reopen: (p: string, c: string) => call<Thread>(`${base(p)}/comments/${id(c)}/reopen`, "POST"),
  fixText: (p: string, c: string, lang: "ar" | "en") =>
    call<{ text: string }>(`${base(p)}/comments/${id(c)}/fix${query({ lang })}`, "POST"),
  closeout: (p: string, d: string) => call<CloseOut>(`${base(p)}/deliverables/${id(d)}/closeout`),
  issueRevision: (p: string, d: string) => call<{ no: number }>(`${base(p)}/deliverables/${id(d)}/revisions`, "POST"),
  signOff: (p: string, d: string) => call<{ revision: number }>(`${base(p)}/deliverables/${id(d)}/signoff`, "POST"),
  exportFile: (p: string, d: string, format: "xlsx" | "docx" | "pdf", revision?: number) =>
    bytes(`${base(p)}/deliverables/${id(d)}/export${query({ format, revision })}`, `deliverable.${format}`),
  reviewReport: (p: string, d: string, revision: number) =>
    bytes(`${base(p)}/deliverables/${id(d)}/review-report${query({ revision, format: "pdf" })}`, "review.pdf"),
  fillPlans: (p: string, d: string) => call<{ plans: FillPlanInfo[] }>(`${base(p)}/deliverables/${id(d)}/fill-plans`),
  fillPreview: (p: string, f: string) => call<FillPreview>(`${base(p)}/fill-plans/${id(f)}/preview`),
  acceptMismatches: (p: string, f: string, rows: number[]) =>
    call<FillPreview>(`${base(p)}/fill-plans/${id(f)}/accept-mismatches`, "POST", { rows }),
  fillFile: (p: string, f: string) => bytes(`${base(p)}/fill-plans/${id(f)}/file`, "client.xlsx"),
  explain: (p: string, number: string, page = 1) =>
    call<Explained>(`${base(p)}/numbers/${id(number)}/explain${query({ page })}`),
};
