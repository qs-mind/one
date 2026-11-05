// The first launch's ink check: a filled Ink circle whose Paper check draws itself (styles.css .fl-check). In a line
// that says a step worked, and, as SavedCheck, beside a settings select for a moment after a pick there saved, so the
// select itself confirms the save (the line under it still says "Saved" for screen readers).
import { useEffect, useRef, useState } from "react";

/** How long the check stays beside a select after a save. */
export const CHECK_SHOWN = 900;

export function InkCheck({ className = "size-5" }: { className?: string }) {
  return (
    <svg viewBox="0 0 20 20" aria-hidden="true" data-ink-check className={className}>
      <circle cx="10" cy="10" r="10" className="fill-ink" />
      <path d="M5.8 10.4l2.8 2.8 5.6-5.8" fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="fl-check stroke-paper" />
    </svg>
  );
}

/** The check for a moment each time `n` (the count of saves answered) moves on and the save worked. */
export function SavedCheck({ n, done, className = "" }: { n: number; done: boolean; className?: string }) {
  const [shown, setShown] = useState(false);
  const seen = useRef(n);
  useEffect(() => {
    if (n === seen.current) return;
    seen.current = n;
    setShown(done);
    if (!done) return;
    const timer = setTimeout(() => setShown(false), CHECK_SHOWN);
    return () => clearTimeout(timer);
  }, [n, done]);
  return shown ? <InkCheck key={n} className={`saved-check size-5 ${className}`} /> : null;
}
