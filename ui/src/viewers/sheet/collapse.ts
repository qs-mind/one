// Folding BOQ sections. The core sends a flat list with section rows; a folded section hides every row after it
// until the next section at its own level or above.
import type { ViewRow } from "../../deliverables/types";

export function visibleRows(rows: ViewRow[], collapsed: ReadonlySet<string>): ViewRow[] {
  const shown: ViewRow[] = [];
  let foldedAt: number | null = null; // the level of the folded section we are inside
  for (const row of rows) {
    const level = row.level ?? 1;
    if (foldedAt !== null) {
      if (row.kind === "section" && level <= foldedAt) foldedAt = null;
      else continue;
    }
    shown.push(row);
    if (row.kind === "section" && collapsed.has(row.id)) foldedAt = level;
  }
  return shown;
}

const key = (deliverableId: string) => `qsone.sheet.collapsed.${deliverableId}`;

/** The folded sections of a Deliverable, remembered on this computer; none when storage is blocked. */
export function loadCollapsed(deliverableId: string): Set<string> {
  try {
    const value = JSON.parse(localStorage.getItem(key(deliverableId)) ?? "[]") as unknown;
    return new Set(Array.isArray(value) ? value.filter((v): v is string => typeof v === "string") : []);
  } catch {
    return new Set();
  }
}

export function saveCollapsed(deliverableId: string, collapsed: ReadonlySet<string>): void {
  try {
    localStorage.setItem(key(deliverableId), JSON.stringify([...collapsed]));
  } catch {
    // private window or blocked storage: the folds last for this session only
  }
}
