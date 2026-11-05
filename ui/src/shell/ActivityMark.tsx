// A chat's activity as one small mark: working, the three dots fading in turn (the only motion, and only while the
// work really runs); waiting for you, a Copper dot; failed, a Copper ring; done since you last looked, an Ink dot.
// Nothing blinks, glows or casts a shadow. With reduced motion the three dots stand still. The words beside the mark
// (or its `label`) say the same for a screen reader.
import { t, type texts } from "../i18n";
import { useReducedMotion } from "../ui/motion";
import { WorkDots } from "../ui/WorkDots";
import type { ActivityState } from "./chatActivity";

export const ACTIVITY_WORD: Record<ActivityState, keyof typeof texts> = {
  working: "activityWorking",
  waiting: "activityWaiting",
  failed: "activityFailed",
  done: "activityDone",
};

const dot = "inline-block size-[7px] shrink-0 rounded-full";

export function ActivityMark({ state, label }: { state: ActivityState; label?: string }) {
  const reduced = useReducedMotion();
  const a11y = label ? { role: "img", "aria-label": label } : { "aria-hidden": true };
  return (
    <span data-activity={state} className="inline-flex shrink-0 items-center" {...a11y}>
      {state === "working" &&
        (reduced ? (
          <span data-still="" className="inline-flex gap-[3px]">
            <span className="size-[3px] rounded-full bg-slate" />
            <span className="size-[3px] rounded-full bg-slate" />
            <span className="size-[3px] rounded-full bg-slate" />
          </span>
        ) : (
          <WorkDots />
        ))}
      {state === "waiting" && <span className={`${dot} bg-copper`} />}
      {state === "failed" && <span className={`${dot} border-[1.5px] border-copper`} />}
      {state === "done" && <span className={`${dot} bg-ink`} />}
    </span>
  );
}

/** The state in a word: «شغال», «مستنيك», «اتعطل», «خلص». */
export const activityWord = (state: ActivityState) => t(ACTIVITY_WORD[state]);
