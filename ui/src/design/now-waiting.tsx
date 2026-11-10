// The only file that names a copper utility. "Now" and "waiting for you" reach copper through these, nothing else.
import type { ComponentProps } from "react";
import { cn } from "@/design/lib/utils";

export type StageState = "done" | "now" | "waiting" | "pending";

/** Fill of a stage segment. */
export const stateFill: Record<StageState, string> = {
  done: "bg-foreground",
  now: "bg-now",
  waiting: "bg-now",
  pending: "bg-line",
};

/** Look of a status dot: filled, or hollow when pending. */
export const stateDot: Record<StageState, string> = {
  done: "bg-foreground",
  now: "bg-now",
  waiting: "bg-now",
  pending: "border-[1.5px] border-muted-foreground",
};

/** The word "now", or the number of the current stage, beside a 700 title. */
export function NowWord({ className, ...props }: ComponentProps<"span">) {
  return <span className={cn("text-xs text-now", className)} {...props} />;
}

/** The label line of a block that waits for the engineer, inside a thread. */
export function WaitingLabel({ className, ...props }: ComponentProps<"div">) {
  return <div className={cn("text-xs text-waiting", className)} {...props} />;
}

/** A short inline word that asks the engineer to look, such as an unsure reading's "check it". */
export function WaitingWord({ className, ...props }: ComponentProps<"span">) {
  return <span className={cn("text-xs text-waiting", className)} {...props} />;
}
