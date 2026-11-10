// What the plan card draws from a plan's stages: their count, the days they span, each stage's share of the bar, and
// the stage that runs now. Days are whole calendar days, both ends counted, as the plan writes them (YYYY-MM-DD).
import type { StageState } from "@/design/now-waiting";
import type { TenderPlan } from "./parts";

type Stage = TenderPlan["stages"][number];

const DAY_MS = 86_400_000;
const dayOf = (day: string) => Date.parse(`${day}T00:00:00Z`) / DAY_MS;
const span = (starts: string, ends: string) => Math.max(1, dayOf(ends) - dayOf(starts) + 1);

const STATE: Record<Stage["status"], StageState> = {
  approved: "done",
  now: "now",
  waiting_engineer: "waiting",
  pending: "pending",
};

export type PlanShape = {
  count: number;
  days: number;
  bar: { state: StageState; weight: number }[];
  /** The stage that runs or waits for sign-off, and its place (1-based); null when none does. */
  current: { step: number; stage: Stage } | null;
  allDone: boolean;
};

export function planShape(stages: readonly Stage[]): PlanShape {
  const first = stages.reduce((min, s) => (s.starts < min ? s.starts : min), stages[0]?.starts ?? "");
  const last = stages.reduce((max, s) => (s.ends > max ? s.ends : max), stages[0]?.ends ?? "");
  const index = stages.findIndex((s) => s.status === "now" || s.status === "waiting_engineer");
  return {
    count: stages.length,
    days: stages.length === 0 ? 0 : span(first, last),
    bar: stages.map((s) => ({ state: STATE[s.status], weight: span(s.starts, s.ends) })),
    current: index < 0 ? null : { step: index + 1, stage: stages[index]! },
    allDone: stages.length > 0 && stages.every((s) => s.status === "approved"),
  };
}
