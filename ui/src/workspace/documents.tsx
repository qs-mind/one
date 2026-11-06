// The documents of the open project and its open document, for the whole screen: the switcher, the palette and the
// team list read the lists; the open document is restored when the project opens, saved as it changes (flushed on a
// project switch and on pagehide), and closed when its document goes (a live event or a reload no longer lists it).
// The live team (project/live/activity.ts) runs while the project is open.
import { createContext, useContext, useEffect, useState, useSyncExternalStore } from "react";
import type { DeliverableInfo } from "../deliverables/types";
import { fill, t } from "../i18n";
import { startActivity } from "../project/live/activity";
import { beforeClose } from "../records/project";
import type { ClientBoqInfo, DeskInfo, DocKey, FileInfo, ProjectSources } from "../project/types";
import { subscribeMoved, subscribeOpened, workspaceApi } from "./api";
import { createWorkspaceSaver } from "./persist";
import { viewOf } from "./views";

export type Documents = {
  deliverables: readonly DeliverableInfo[];
  clientBoqs: readonly ClientBoqInfo[];
  files: readonly FileInfo[];
  desks: readonly DeskInfo[];
  /** The file list could not be read: `files` is then empty, not known to be. */
  filesFailed?: boolean;
};

/** The lists as read; null for one that could not be read (its documents are not taken for gone). */
type Lists = { deliverables: DeliverableInfo[] | null; files: FileInfo[] | null; clientBoqs: ClientBoqInfo[] | null; desks: DeskInfo[] | null };

const documentsOf = (lists: Lists): Documents => ({
  deliverables: lists.deliverables ?? [],
  files: lists.files ?? [],
  clientBoqs: lists.clientBoqs ?? [],
  desks: lists.desks ?? [],
  ...(lists.files ? {} : { filesFailed: true }),
});

// Files on their way into the open project (chosen or dropped on Project files, while they upload): the chat stops
// asking for them as soon as they go, when the drop area starts showing them being added.
let uploading = 0;
const uploadListeners = new Set<() => void>();

/** Marks an upload begun; the function it answers marks it ended. */
export function startUpload(): () => void {
  let ended = false;
  const tell = () => {
    for (const listener of [...uploadListeners]) listener();
  };
  uploading += 1;
  tell();
  return () => {
    if (ended) return;
    ended = true;
    uploading -= 1;
    tell();
  };
}

/** Whether files are uploading now. */
export function useUploading(): boolean {
  return useSyncExternalStore(
    (listener) => {
      uploadListeners.add(listener);
      return () => void uploadListeners.delete(listener);
    },
    () => uploading > 0,
  );
}

const split = (key: string) => [key.slice(0, key.indexOf(":")), key.slice(key.indexOf(":") + 1)] as const;

function exists(lists: Lists, key: DocKey): boolean {
  const [kind, id] = split(key);
  if (kind === "files") return id === "all";
  if (kind === "deliverable") return !lists.deliverables || lists.deliverables.some((d) => d.id === id);
  if (kind === "file") return !lists.files || lists.files.some((f) => f.id === id);
  if (kind === "clientboq") return !lists.clientBoqs || lists.clientBoqs.some((b) => b.file_id === id);
  if (kind === "view") return viewOf(id) !== undefined;
  return false;
}

/** A document's name in the page language, or null when `key` is not a document of these lists. */
export function titleOf(docs: Documents, key: string): string | null {
  const [kind, id] = split(key);
  if (kind === "files") return id === "all" ? t("projectFiles") : null;
  if (kind === "deliverable") return docs.deliverables.find((d) => d.id === id)?.title ?? null;
  if (kind === "file") return docs.files.find((f) => f.id === id)?.name ?? null;
  if (kind === "clientboq") {
    const boq = docs.clientBoqs.find((b) => b.file_id === id);
    return boq ? fill(t("clientBoqTitle"), { name: boq.name }) : null;
  }
  if (kind === "view") return viewOf(id)?.title ?? null;
  return null;
}

export const DocumentsContext = createContext<Documents | null>(null);

/** The name of the document `key` names (an agent's focus), or null when it names none. */
export function useDocTitle(key: string | null): string | null {
  const docs = useContext(DocumentsContext);
  return docs && key ? titleOf(docs, key) : null;
}

/** The desks of the open project, for the team list. */
export function useDesks(): readonly DeskInfo[] {
  return useContext(DocumentsContext)?.desks ?? [];
}

const upsert = <T,>(list: T[] | null, item: T, same: (a: T) => boolean): T[] | null =>
  list && [item, ...list.filter((x) => !same(x))];

/** The documents of `sources`' project once read (null until then), with the open document restored, saved and
 * kept in line with them. */
export function useDocuments(sources: ProjectSources | undefined): Documents | null {
  const [state, setState] = useState<{ sources: ProjectSources; docs: Documents } | null>(null);

  useEffect(() => {
    if (!sources) return;
    const controller = new AbortController();
    const signal = controller.signal;
    const saver = createWorkspaceSaver(sources);
    let lists: Lists | null = null; // null until read: the restore below saves nothing

    const changed = () => {
      const opened = workspaceApi.current();
      if (lists && opened) saver.save(opened);
    };
    const offOpened = subscribeOpened(changed);
    const offMoved = subscribeMoved(changed); // a row selected, a page turned: saved as an opening is
    const offClose = beforeClose(() => saver.flush()); // the core closes the project only after this save
    const onHide = () => void saver.flush(true);
    window.addEventListener("pagehide", onHide);

    const show = (next: Lists) => {
      lists = next;
      setState({ sources, docs: documentsOf(next) });
      const open = workspaceApi.current();
      if (open && !exists(next, open.key)) workspaceApi.forget(open.key); // its document is gone: Project files
    };
    const read = () =>
      Promise.all([
        sources.deliverables().catch(() => null),
        sources.files().catch(() => null),
        sources.workspace().catch(() => null),
        sources.team().catch(() => null),
      ]);

    void read().then(([deliverables, files, saved, team]) => {
      if (signal.aborted) return;
      const next: Lists = { deliverables, files, clientBoqs: saved?.client_boqs ?? null, desks: team?.desks ?? null };
      workspaceApi.reset(saved?.open ? { key: saved.open, anchor: saved.anchor } : null, (key) => exists(lists ?? next, key));
      show(next);
      startActivity(sources, signal, team ?? undefined);
      sources.activity(
        (event) => {
          const now = lists!;
          if (event.type === "deliverable") show({ ...now, deliverables: upsert(now.deliverables, event.deliverable, (d) => d.id === event.deliverable.id) });
          else if (event.type === "file") {
            const { id, replaces } = event.file;
            // a new version of a file: it opens in the old one's place, rather than the old one gone to Project files
            if (replaces && replaces !== id) workspaceApi.replace(`file:${replaces}`, `file:${id}`);
            show({ ...now, files: upsert(now.files, event.file, (f) => f.id === id || f.id === replaces) });
          }
          else if (event.type === "client_boq")
            show({ ...now, clientBoqs: upsert(now.clientBoqs, event.client_boq, (b) => b.file_id === event.client_boq.file_id) });
          else if (event.type === "desk") show({ ...now, desks: upsert(now.desks, event.desk, (d) => d.id === event.desk.id) });
        },
        signal,
        () =>
          void read().then(([d, f, w, team]) => {
            if (signal.aborted) return;
            const now = lists!;
            // a list that could not be read again stays as it was
            show({ deliverables: d ?? now.deliverables, files: f ?? now.files, clientBoqs: w?.client_boqs ?? now.clientBoqs, desks: team?.desks ?? now.desks });
          }),
      );
    });

    return () => {
      controller.abort();
      offOpened();
      offMoved();
      offClose();
      window.removeEventListener("pagehide", onHide);
      void saver.flush();
    };
  }, [sources]);

  return state && state.sources === sources ? state.docs : null;
}
