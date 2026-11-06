import type { SourceLocator } from "../project/types";
// Where a number's source shows on screen. An element that shows a source carries `data-source-at` with one or more
// keys (space-separated):
//   number:<number id>                 a ledger number as a sheet cell or a document reference shows it
//   file:<file id>                     a file's frame on the canvas (its `data-frame` counts too)
//   file:<file id>#page=3              a PDF page; #sheet=BOQ&row=41, #row=12, #line=7: a piece of a file's text
//   source:<source id>                 a source chip
// Values in a key are URI-encoded, so a sheet name with a space stays one key.

export const TARGET = "data-source-at";

/** What the core says about where a number came from. Only what it really has: any part may be missing. */
export type SourcePlace = {
  numberId?: string | null;
  sourceId?: string | null;
  fileId?: string | null;
  locator?: SourceLocator | null;
};

const PLACES = ["page", "sheet", "row", "line"] as const;

/** A file's key, with the place in it when the locator names one: `file:f1#sheet=BOQ&row=41`. */
export function fileKey(fileId: string, locator?: SourceLocator | null): string {
  const at = PLACES.filter((k) => locator?.[k] !== undefined && locator[k] !== "").map(
    (k) => `${k}=${encodeURIComponent(String(locator![k]))}`,
  );
  return `file:${fileId}${at.length ? `#${at.join("&")}` : ""}`;
}

/** The keys a number's source may show under, the most exact first. `number` adds the ledger number itself as it
 * stands in a sheet or document (for a number quoted in the chat or a card); a viewer leaves it out for its own
 * cells. Empty for a number with no source. */
export function sourceKeys(place: SourcePlace | null | undefined, { number = false } = {}): string[] {
  if (!place) return [];
  const keys: string[] = [];
  if (place.fileId) {
    const exact = fileKey(place.fileId, place.locator);
    keys.push(exact);
    if (exact !== `file:${place.fileId}`) keys.push(`file:${place.fileId}`);
  }
  if (place.sourceId) keys.push(`source:${place.sourceId}`);
  if (number && place.numberId) keys.push(`number:${place.numberId}`);
  return keys;
}

const quoted = (value: string) => `"${value.replace(/["\\]/g, "\\$&")}"`;

/** Every element showing `key`, in page order. A file's frame counts for its plain key. */
export function elementsFor(key: string): HTMLElement[] {
  const found = [...document.querySelectorAll<HTMLElement>(`[${TARGET}~=${quoted(key)}]`)];
  if (/^file:[^#]+$/.test(key)) found.push(...document.querySelectorAll<HTMLElement>(`[data-frame=${quoted(key)}]`));
  return found;
}

/** The first element for `keys` (most exact key first) that `accept` takes, never `from` itself or one around or
 * inside it. */
export function findTarget(keys: string[], from: Element | null, accept: (el: HTMLElement) => boolean = () => true) {
  for (const key of keys)
    for (const el of elementsFor(key)) {
      if (from && (el === from || el.contains(from) || from.contains(el))) continue;
      if (accept(el)) return el;
    }
  return null;
}
