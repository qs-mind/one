// What every first-launch step shares: its heading, and the row of its buttons with a line of words beside them.
import type { ReactNode } from "react";

export function StepHead({ title, lead }: { title: string; lead: string }) {
  return (
    <div className="flex flex-col gap-2">
      <h1 className="text-3xl font-bold max-sm:text-2xl">{title}</h1>
      <p className="text-lg text-muted-foreground">{lead}</p>
    </div>
  );
}

/** The step's buttons at the end side; `note` says what holds the step, or a plain fact, at the start side. */
export function StepActions({ note, strong = false, children }: { note?: ReactNode; strong?: boolean; children: ReactNode }) {
  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-3">
      <p aria-live="polite" className={strong ? "flex-[1_1_16rem] text-xs font-bold" : "flex-[1_1_16rem] text-xs text-muted-foreground"}>
        {note}
      </p>
      <div className="ms-auto flex items-center gap-3">{children}</div>
    </div>
  );
}
