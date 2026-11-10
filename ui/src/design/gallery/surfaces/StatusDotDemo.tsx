import type { StageState } from "@/design/now-waiting";
import { StatusDot } from "@/design/StatusDot";
import { common } from "@/texts/common";
import { surfaces } from "@/texts/design/surfaces";
import { useText } from "@/texts/useText";
import { Demo, State } from "../parts";

const WORDS = {
  done: common.done,
  now: common.now,
  waiting: surfaces.stateWaiting,
  pending: surfaces.statePending,
} satisfies Record<StageState, { en: string; ar: string }>;

export function StatusDotDemo() {
  const t = useText();
  return (
    <Demo id="status-dot" title="StatusDot">
      {(Object.keys(WORDS) as StageState[]).map((state) => (
        <State key={state} name={state}>
          <span className="flex items-center gap-2">
            <StatusDot state={state} />
            {t(WORDS[state])}
          </span>
        </State>
      ))}
    </Demo>
  );
}
