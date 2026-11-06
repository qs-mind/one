import type { SourceLocator } from "../project/types";
// A number's source opened from its card: the file opens as the document at its page, and once it shows, the quoted
// place in it is marked with the source mark (sources/mark.ts): a sheet row or line of the file's text. The card
// closes as the file opens, so the workspace marks it (Workspace.tsx) and says once when it cannot.
import type { Anchor, Opened } from "../project/types";
import { sourceKeys } from "../sources/targets";
import { workspaceApi } from "./api";

/** `opened`: the opening it belongs to, once the workspace has shown it. */
type Wanted = { key: string; opened: Opened | null; keys: string[]; figures: string[] };
let wanted: Wanted | null = null;

/** Opens the file of a source as the document, at its page; its place is marked once it shows. */
export function openSourceFile(fileId: string, locator: SourceLocator | null | undefined, figures: string[]) {
  wanted = { key: `file:${fileId}`, opened: null, keys: sourceKeys({ fileId, locator }), figures };
  workspaceApi.open(`file:${fileId}`, anchorOf(locator));
}

/** Where in the file to open: a PDF's page, or a spreadsheet's cell (its sheet, row `r<row>` and column letters). */
function anchorOf(locator: SourceLocator | null | undefined): Anchor {
  if (typeof locator?.page === "number") return { page: locator.page };
  const row = locator?.row ?? locator?.line; // a CSV's row is its line
  if (row === undefined) return {};
  const column = typeof locator?.column === "string" ? { column: locator.column } : {};
  return { ...(locator?.sheet !== undefined ? { sheet: String(locator.sheet) } : {}), row: `r${row}`, ...column };
}

/** The place to mark in `opened`, when this very opening came from a source card; null otherwise (Back to the same
 * file later marks nothing again). */
export function markFor(opened: Opened): { keys: string[]; figures: string[] } | null {
  if (!wanted || wanted.key !== opened.key || (wanted.opened && wanted.opened !== opened)) return null;
  wanted.opened = opened;
  return { keys: wanted.keys, figures: wanted.figures };
}
