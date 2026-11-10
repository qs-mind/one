// Press-and-hold, for anything paid or irreversible: it goes ahead only after a full hold of HOLD_MS, or, for a
// screen reader, voice control or switch access (one synthetic click, no held key), after two activations within
// ARM_MS. The timer decides, not the band. Released early, the band runs back, nothing happens and the hint opens.
// Enter and Space hold the same way; a key repeat does not restart; blur, leaving, cancel and the context menu release.
import { type KeyboardEvent, type MouseEvent, type ReactNode, useEffect, useId, useRef, useState } from "react";
import { cn } from "@/design/lib/utils";
import { Button } from "@/design/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/design/ui/tooltip";
import { common } from "@/texts/common";
import { useText } from "@/texts/useText";

export const HOLD_MS = 900;
export const ARM_MS = 5000;
/** How fast a released band runs back. */
const BACK_MS = 200;
/** How long the hint stays open after an early release. */
const HINT_MS = 2000;

type HoldButtonProps = {
  onHold: () => void;
  /** Why it is held, in words: "الموافقة تبدأ شغل مدفوع". */
  hint: string;
  /** The label: "وافق وابدأ". */
  children: ReactNode;
  disabled?: boolean;
  /** Passed to Button: the label may break onto more lines. */
  wrap?: boolean;
  className?: string;
};

const reducedMotion = () =>
  typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const isHoldKey = (key: string) => key === "Enter" || key === " ";

export function HoldButton({ onHold, hint, children, disabled, wrap, className }: HoldButtonProps) {
  const t = useText();
  const helpId = useId();
  const band = useRef<HTMLSpanElement>(null);
  const holdTimer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const armTimer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const hintTimer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const animation = useRef<Animation>(undefined);
  const armedRef = useRef(false);
  const [holding, setHolding] = useState(false);
  const [armed, setArmed] = useState(false);
  const [open, setOpen] = useState(false);
  const [pinned, setPinned] = useState(false);

  const stopBand = () => {
    animation.current?.cancel();
    animation.current = undefined;
  };

  useEffect(
    () => () => {
      clearTimeout(holdTimer.current);
      clearTimeout(armTimer.current);
      clearTimeout(hintTimer.current);
      stopBand();
    },
    [],
  );

  function setArm(next: boolean) {
    clearTimeout(armTimer.current);
    armedRef.current = next;
    setArmed(next);
    if (next) armTimer.current = setTimeout(() => setArm(false), ARM_MS);
  }

  function goAhead() {
    setArm(false);
    onHold();
  }

  function start() {
    if (disabled || holdTimer.current !== undefined) return;
    setHolding(true);
    holdTimer.current = setTimeout(() => {
      holdTimer.current = undefined;
      setHolding(false);
      stopBand();
      goAhead();
    }, HOLD_MS);
    const line = band.current;
    if (!line || reducedMotion() || typeof line.animate !== "function") return;
    stopBand();
    animation.current = line.animate([{ width: "0%" }, { width: "100%" }], {
      duration: HOLD_MS,
      easing: "linear",
      fill: "forwards",
    });
  }

  function release() {
    if (holdTimer.current === undefined) return;
    clearTimeout(holdTimer.current);
    holdTimer.current = undefined;
    setHolding(false);
    // Early: show why it did not go ahead.
    clearTimeout(hintTimer.current);
    setPinned(true);
    hintTimer.current = setTimeout(() => setPinned(false), HINT_MS);
    const running = animation.current;
    if (!running) return;
    running.playbackRate = -HOLD_MS / BACK_MS; // runs back from where it is
    running.onfinish = () => running === animation.current && stopBand();
  }

  function onClick(event: MouseEvent<HTMLButtonElement>) {
    // A pointer click (detail ≥ 1) is a release, already handled. A synthetic one arms, then confirms.
    if (disabled || event.detail !== 0 || holdTimer.current !== undefined) return;
    if (armedRef.current) goAhead();
    else setArm(true);
  }

  function onKeyDown(event: KeyboardEvent<HTMLButtonElement>) {
    if (!isHoldKey(event.key)) return;
    event.preventDefault(); // never the key's own click: only a full hold goes ahead
    if (!event.repeat) start();
  }

  function onKeyUp(event: KeyboardEvent<HTMLButtonElement>) {
    if (!isHoldKey(event.key)) return;
    event.preventDefault(); // Space clicks on key up
    release();
  }

  const pressAgain = t(common.pressAgain);
  return (
    <>
      <Tooltip open={open || pinned} onOpenChange={setOpen}>
        <TooltipTrigger
          render={
            <Button
              wrap={wrap}
              disabled={disabled}
              aria-describedby={helpId}
              data-hold=""
              data-holding={holding || undefined}
              data-armed={armed || undefined}
              onPointerDown={(event) => event.button === 0 && start()}
              onPointerUp={release}
              onPointerLeave={release}
              onPointerCancel={release}
              onBlur={release}
              onContextMenu={release}
              onKeyDown={onKeyDown}
              onKeyUp={onKeyUp}
              onClick={onClick}
              className={cn("relative overflow-hidden active:bg-primary data-holding:bg-primary!", className)}
            />
          }
        >
          <span
            ref={band}
            aria-hidden="true"
            data-slot="hold-band"
            className="pointer-events-none absolute inset-y-0 start-0 w-0 bg-hold"
          />
          <span className="relative">{armed ? pressAgain : children}</span>
        </TooltipTrigger>
        <TooltipContent className="flex-col items-start gap-0">
          <span>{t(common.holdToConfirm)}</span>
          <span>{hint}</span>
        </TooltipContent>
      </Tooltip>
      <span id={helpId} className="sr-only">
        {hint} {t(common.holdHelpReader)}
      </span>
      <span aria-live="polite" className="sr-only">
        {armed ? pressAgain : ""}
      </span>
    </>
  );
}
