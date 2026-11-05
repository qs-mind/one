// A bar filled by real counts only («212 of 480 files»): scaleX of an Ink fill growing from the side the words start
// on (the right in Arabic), easing 300 ms to each new count. Its first render shows the share it has, never counting
// up from zero. Without a real count (no total, not a number) there is no bar: never a sweep, never a made-up share.
// It is for the eye; the line beside it says the numbers.
import { useReducedMotion } from "./motion";

export function ProgressBar({ done, total, className = "h-1.5" }: { done: number; total: number; className?: string }) {
  const still = useReducedMotion();
  const real = Number.isFinite(done) && Number.isFinite(total) && done >= 0 && total > 0;
  if (!real) return null;
  const share = Math.min(1, done / total);
  return (
    <div aria-hidden="true" className={`overflow-hidden rounded-full bg-stone ${className}`}>
      <div data-progress-fill data-still={still || undefined} className="progress-fill h-full bg-ink" style={{ transform: `scaleX(${share})` }} />
    </div>
  );
}
