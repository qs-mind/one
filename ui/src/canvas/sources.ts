// The project's sources over /api: the only place that knows the routes of Plans 2, 4 and 6 and of this plan's core
// (Task 2). A 404 from a route a later plan adds answers empty, so the canvas shows only what is real.
import type { ComponentType } from "react";
import { subscribeActivity } from "../activity";
import { coreLine } from "../core";
import { deliverablesApi } from "../deliverables/api";
import type { Text } from "../i18n";
import { texts } from "../i18n";
import { uploadFile } from "../records/RecordsPanel";
import type { SheetView } from "../deliverables/types";
import type { ClientBoqInfo, DeliverableInfo, FileInfo, FilePiece, Placed, ProjectSources, Team, View, ViewerProps } from "./types";

/** A refused call, with the core's line in both languages. */
export class SourceError extends Error {
  constructor(readonly line: Text) {
    super(line.en);
  }
}

/** The screen keeps at most this many page images as object URLs and revokes the rest (decision 13). */
export const PAGE_IMAGES_KEPT = 64;

// Plan 6's viewer registry, found at build time so the build passes before the file exists.
type Registry = { viewerFor?: (kind: DeliverableInfo["kind"]) => ComponentType<ViewerProps> | null };
const registry = Object.values(import.meta.glob<Registry>("../viewers/registry.ts", { eager: true }))[0];

/** The live viewer for a Deliverable kind, or null (then the frame shows its poster). */
export function viewerFor(kind: DeliverableInfo["kind"]): ComponentType<ViewerProps> | null {
  return registry?.viewerFor?.(kind) ?? null;
}

async function json<T>(url: string, empty: T, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init).catch(() => undefined);
  if (response?.status === 404) return empty;
  if (!response?.ok) throw new SourceError(await coreLine(response, texts.canvasFailed));
  return (await response.json()) as T;
}

async function put(url: string, body: unknown, keepalive: boolean): Promise<void> {
  const response = await fetch(url, {
    method: "PUT",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
    keepalive,
  }).catch(() => undefined);
  if (response?.status === 404) return; // Task 2's routes are not there yet: nothing to keep the layout in
  if (!response?.ok) throw new SourceError(await coreLine(response, texts.canvasFailed));
}

export function httpSources(projectId: string): ProjectSources {
  const base = `/api/projects/${encodeURIComponent(projectId)}`;
  const file = (id: string) => `${base}/files/${encodeURIComponent(id)}`;
  const images = new Map<string, Promise<string>>(); // oldest first

  return {
    files: async () => (await json<{ files: FileInfo[] }>(`${base}/files`, { files: [] })).files,
    async deliverables() {
      const answer = await deliverablesApi.list(projectId);
      if (answer.ok) return answer.data.deliverables;
      if (answer.status === 404) return [];
      throw new SourceError(answer.error);
    },
    team: () => json<Team>(`${base}/team`, { desks: [], agents: [] }),
    status: () => json(`${base}/status`, {}),
    layout: () =>
      json<{ frames: Placed[]; view: View | null; client_boqs?: ClientBoqInfo[] }>(`${base}/canvas`, { frames: [], view: null }),
    saveFrames: (frames, removed, keepalive = false) => put(`${base}/canvas/frames`, { frames, removed }, keepalive),
    saveView: (view, keepalive = false) => put(`${base}/canvas/view`, view, keepalive),
    activity(onEvent, signal, onReconnect) {
      if (signal.aborted) return;
      const stop = subscribeActivity(projectId, onEvent, onReconnect);
      signal.addEventListener("abort", stop, { once: true });
    },
    pageImage(fileId, page, width) {
      const key = `${fileId}/${page}/${width}`;
      const kept = images.get(key);
      if (kept) {
        images.delete(key);
        images.set(key, kept); // now the newest
        return kept;
      }
      const made = (async () => {
        const response = await fetch(`${file(fileId)}/pages/${page}?width=${width}`).catch(() => undefined);
        if (!response?.ok) throw new SourceError(await coreLine(response, texts.pageNotShown));
        return URL.createObjectURL(await response.blob());
      })();
      made.catch(() => images.delete(key));
      images.set(key, made);
      while (images.size > PAGE_IMAGES_KEPT) {
        const [oldest, url] = images.entries().next().value!;
        images.delete(oldest);
        void url.then(URL.revokeObjectURL, () => {});
      }
      return made;
    },
    async pages(fileId) {
      const response = await fetch(`${file(fileId)}/pages`).catch(() => undefined);
      if (response?.status === 404 || response?.status === 409) return 0; // no route yet, or not a PDF
      if (!response?.ok) throw new SourceError(await coreLine(response, texts.canvasFailed));
      return ((await response.json()) as { pages: number }).pages;
    },
    async fileText(fileId, page) {
      const query = page === undefined ? "" : `?page=${page}`;
      return (await json<{ pieces: FilePiece[] }>(`${file(fileId)}/text${query}`, { pieces: [] })).pieces;
    },
    async clientBoq(fileId) {
      const response = await fetch(`${base}/client-boq/${encodeURIComponent(fileId)}`).catch(() => undefined);
      if (!response?.ok) throw new SourceError(await coreLine(response, texts.canvasFailed));
      return (await response.json()) as SheetView;
    },
    async upload(chosen) {
      const added = await uploadFile(projectId, chosen);
      if (!added.ok) throw new SourceError(added.line);
      return added.info;
    },
  };
}
