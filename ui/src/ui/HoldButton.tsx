// Press-and-hold, for an answer that costs money or can't be taken back: it goes ahead only after a full hold of
// HOLD_MS, so it is never pressed by mistake. A thin line fills along the button from the side its words start on
// (the right in Arabic) while it is held; released early, the line runs back and nothing happens. Holding Enter or Space
// works the same, a key repeat does not start it again, and a right-click, the pointer leaving or the button losing
// focus all let go. Screen readers hear how it works from `hint` (aria-describedby).
//
// The fill is user-paced progress, so it is linear and takes the whole hold; the timer, not the animation, decides.
// With reduced motion there is no fill, and the hold is just as long: it is a safety delay, not motion.
import { type ReactNode, useEffect, useId, useRef } from "react";
import { reducedMotion } from "./motion";

export const HOLD_MS = 900;
/** How fast a released fill runs back. */
const BACK_MS = 200;

export function HoldButton({
  onHold,
  hint,
  children,
  disabled,
  className = "",
}: {
  onHold: () => void;
  /** How it works and why: "Press and hold to go ahead: this costs money." */
  hint: string;
  children: ReactNode;
  disabled?: boolean;
  className?: string;
}) {
  const hintId = useId();
  const fill = useRef<HTMLSpanElement>(null);
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const animation = useRef<Animation>(undefined);

  const stopFill = () => {
    animation.current?.cancel();
    animation.current = undefined;
  };

  useEffect(
    () => () => {
      clearTimeout(timer.current);
      stopFill();
    },
    [],
  );

  function start() {
    if (disabled || timer.current !== undefined) return;
    timer.current = setTimeout(() => {
      timer.current = undefined;
      stopFill();
      onHold();
    }, HOLD_MS);
    const line = fill.current;
    if (!line || reducedMotion() || typeof line.animate !== "function") return;
    stopFill();
    animation.current = line.animate([{ transform: "scaleX(0)" }, { transform: "scaleX(1)" }], {
      duration: HOLD_MS,
      easing: "linear",
      fill: "forwards",
    });
  }

  function release() {
    if (timer.current === undefined) return;
    clearTimeout(timer.current);
    timer.current = undefined;
    const running = animation.current;
    if (!running || typeof running.updatePlaybackRate !== "function") return stopFill();
    running.updatePlaybackRate(-HOLD_MS / BACK_MS); // runs back from where it is
    running.onfinish = () => running === animation.current && stopFill();
  }

  const isHoldKey = (key: string) => key === "Enter" || key === " ";

  return (
    <>
      <button
        type="button"
        disabled={disabled}
        aria-describedby={hintId}
        data-hold
        onPointerDown={(event) => event.button === 0 && start()}
        onPointerUp={release}
        onPointerLeave={release}
        onPointerCancel={release}
        onBlur={release}
        onContextMenu={release}
        onKeyDown={(event) => {
          if (!isHoldKey(event.key)) return;
          event.preventDefault(); // never the button's own click: only a full hold goes ahead
          if (!event.repeat) start();
        }}
        onKeyUp={(event) => isHoldKey(event.key) && release()}
        className={`relative overflow-hidden select-none ${className}`}
      >
        {children}
        <span ref={fill} aria-hidden="true" className="hold-fill opacity-70" />
      </button>
      <span id={hintId} className="sr-only">
        {hint}
      </span>
    </>
  );
}
