// What every block of one view reads: its sources, its unsourced numbers, and how to open a number's source.
import { createContext, useContext } from "react";
import type { NumberCell, Source } from "../../../deliverables/types";

export type ViewEnv = {
  sources: Record<string, Source>;
  unsourced: readonly string[];
  /** Opens the number's source in the source popover; absent where no project is open. */
  openSource?: (cell: NumberCell, from: HTMLElement, focus: boolean) => void;
};

export const ViewEnvContext = createContext<ViewEnv>({ sources: {}, unsourced: [] });

export const useViewEnv = () => useContext(ViewEnvContext);
