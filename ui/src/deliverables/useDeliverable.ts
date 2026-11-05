// One open Deliverable: its view, its pending and stale changes and its comment threads, loaded from the core and
// loaded again when the project's live stream says it changed (or after the stream comes back). The live stream is an
// argument, so Plan 7's live store can stand in for the shared one.
import { useCallback, useEffect, useRef, useState } from "react";
import { subscribeActivity } from "../activity";
import type { Text } from "../i18n";
import { deliverablesApi } from "./api";
import type { Change, Thread, View } from "./types";

export type Subscribe = typeof subscribeActivity;

export type DeliverableState = {
  view: View | null;
  /** Pending changes, oldest first; the Update from Project Records among them when there is one. */
  changes: Change[];
  /** Changes that no longer apply: what they were made against moved before they were accepted. */
  stale: Change[];
  comments: Thread[];
  /** The core's refusal when the view could not be loaded. */
  error: Text | null;
  reload(): Promise<void>;
};

export function useDeliverable(projectId: string, deliverableId: string, subscribe: Subscribe = subscribeActivity) {
  const [state, setState] = useState<Omit<DeliverableState, "reload">>({
    view: null,
    changes: [],
    stale: [],
    comments: [],
    error: null,
  });
  const latest = useRef(0); // only the newest load is shown, however the answers arrive

  const reload = useCallback(async () => {
    const n = ++latest.current;
    const api = deliverablesApi;
    const [view, changes, stale, comments] = await Promise.all([
      api.view(projectId, deliverableId),
      api.changes(projectId, deliverableId, "pending"),
      api.changes(projectId, deliverableId, "stale"),
      api.comments(projectId, deliverableId),
    ]);
    if (n !== latest.current) return;
    setState((now) => ({
      view: view.ok ? view.data : now.view,
      changes: changes.ok ? changes.data.changes : now.changes,
      stale: stale.ok ? stale.data.changes : now.stale,
      comments: comments.ok ? comments.data.comments : now.comments,
      error: view.ok ? null : view.error,
    }));
  }, [projectId, deliverableId]);

  useEffect(() => {
    setState({ view: null, changes: [], stale: [], comments: [], error: null });
    void reload();
    return subscribe(
      projectId,
      (event) => {
        if (event.type === "deliverable" && event.deliverable.id === deliverableId) void reload();
      },
      () => void reload(), // events may have been missed while the stream was down
    );
  }, [projectId, deliverableId, reload, subscribe]);

  return { ...state, reload } satisfies DeliverableState;
}
