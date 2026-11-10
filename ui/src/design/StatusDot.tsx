// A 10px dot for a state. Still (no loop); the word beside it says the state.
import { cn } from "@/design/lib/utils";
import { stateDot, type StageState } from "@/design/now-waiting";

export function StatusDot({ state, className }: { state: StageState; className?: string }) {
  return (
    <span
      aria-hidden
      data-state-fill={state}
      className={cn("inline-block size-2.5 shrink-0 rounded-full", stateDot[state], className)}
    />
  );
}
