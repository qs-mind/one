// Where a clicked number shows its source. Left unset, the sheet opens the source card at the number (SourcePopover);
// the tender's document place sets it, and shows the source in a panel under the sheet instead (U5).
import { createContext } from "react";
import type { NumberCell, Source } from "../../deliverables/types";

export type NumberAsked = { cell: NumberCell; label: string; sources: Record<string, Source> };

export const NumberTarget = createContext<((asked: NumberAsked) => void) | null>(null);

/** A one-line row's height in the open document, px at 100 %. Left unset it is 32; the tender's document place sets
 * it from its dense scope's `--sheet-row-h` (U5). */
export const DenseRowHeight = createContext<number | null>(null);
