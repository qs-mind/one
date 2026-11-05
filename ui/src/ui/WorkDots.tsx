// Three dots fading in turn (styles.css .work-dots), opacity only: the sign of a job that really runs but has no count
// to show (a step in the work log, a check, a save, the Lead QS reading a folder). Shown only while it runs; with
// reduced motion there are none, and the words beside them say it runs.
import { useReducedMotion } from "./motion";

export function WorkDots() {
  const reduced = useReducedMotion();
  if (reduced) return null;
  return (
    <span data-dots aria-hidden="true" className="work-dots">
      <span />
      <span />
      <span />
    </span>
  );
}
