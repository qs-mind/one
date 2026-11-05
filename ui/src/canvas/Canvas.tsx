// The Project Canvas. A stub with its final props until Plan 7 Task 4 draws the React Flow pane: a labelled empty
// region, so the shell (Task 6) can be built against it.
import type { ReactNode } from "react";
import { t, useLanguage } from "../i18n";
import type { ProjectSources } from "./types";

export type CanvasProps = {
  projectId: string;
  sources: ProjectSources;
  /** "Open full screen" on a Deliverable frame. */
  onOpenFull(deliverableId: string): void;
  /** Drawn over the pane, inside it (the live cursors). */
  children?: ReactNode;
};

export function Canvas({ children }: CanvasProps) {
  useLanguage();
  return (
    <section aria-label={t("canvas")} dir="ltr" className="relative h-full w-full bg-stone">
      {children}
    </section>
  );
}
