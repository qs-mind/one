// Views the Lead QS showed that were wider than the chat, opened as a document (`view:<part id>`). They live as long as
// the page: after a reload the chat shows them again, and an open one gives way to Project files.
import type { ViewData } from "../chat/parts/view/types";
import type { DocKey } from "../project/types";
import { workspaceApi } from "./api";

const views = new Map<string, ViewData>();

/** Opens `view` (the chat part `id`) in the document area. */
export function openView(id: string, view: ViewData) {
  views.set(id, view);
  workspaceApi.open(`view:${id}` as DocKey);
}

export function viewOf(id: string): ViewData | undefined {
  return views.get(id);
}
