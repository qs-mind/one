// The viewer registry (Plan 7's contract in ui/src/canvas/types.ts): the component that shows a Deliverable of each
// kind, in a canvas frame or full screen. It loads its own data. Kinds with no viewer yet (markup, board, page)
// have none, and the canvas shows their poster.
import type { ComponentType } from "react";
import type { DeliverableInfo, ViewerProps } from "../canvas/types";
import { DeliverableViewer } from "../deliverables/DeliverableViewer";

export function viewerFor(kind: DeliverableInfo["kind"]): ComponentType<ViewerProps> | null {
  return kind === "sheet" || kind === "document" ? DeliverableViewer : null;
}
