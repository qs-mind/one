import type { StageState } from "@/design/now-waiting";
import { StageBar } from "@/design/StageBar";
import { surfaces } from "@/texts/design/surfaces";
import { useText } from "@/texts/useText";
import { Demo, State } from "../parts";

const PLAN: { state: StageState; weight: number }[] = [
  { state: "done", weight: 1 },
  { state: "now", weight: 1 },
  { state: "pending", weight: 2 },
  { state: "pending", weight: 2 },
  { state: "pending", weight: 3 },
  { state: "pending", weight: 1 },
  { state: "pending", weight: 1 },
];
const ROW = (done: number, wait: boolean): { state: StageState }[] =>
  Array.from({ length: 7 }, (_, i) => ({ state: i < done ? "done" : i === done ? (wait ? "waiting" : "now") : "pending" }));

export function StageBarDemo() {
  const t = useText();
  const label = (step: number, name: { en: string; ar: string }) => t(surfaces.stageLabel, { step, total: 7, name: t(name) });
  return (
    <Demo id="stage-bar" title="StageBar">
      <State name={t(surfaces.planTitle)} className="flex w-full max-w-md flex-col gap-2">
        <StageBar stages={PLAN} label={label(2, surfaces.stageQueries)} />
      </State>
      <State name={t(surfaces.stateWaiting)} className="flex flex-col gap-2">
        <StageBar className="w-40" stages={ROW(1, true)} label={label(2, surfaces.stageQueries)} />
      </State>
      <State name={t(surfaces.stageReview)} className="flex flex-col gap-2">
        <StageBar className="w-40" stages={ROW(5, false)} label={label(6, surfaces.stageReview)} />
      </State>
    </Demo>
  );
}
