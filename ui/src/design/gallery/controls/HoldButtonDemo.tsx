import { useEffect, useRef, type ReactNode } from "react";
import { HoldButton } from "@/design/HoldButton";
import { notify } from "@/design/notify";
import { controls } from "@/texts/design/controls";
import { foundation } from "@/texts/design/foundation";
import { useText } from "@/texts/useText";
import { Demo, State } from "../parts";

/** The assistive path, held on show: a synthetic click arms it, and it is armed again whenever it disarms. */
function Armed({ children }: { children: ReactNode }) {
  const box = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    const button = box.current?.querySelector("button");
    if (!button) return;
    const arm = () => {
      if (!button.hasAttribute("data-armed")) button.click();
    };
    // On the next frame: StrictMode runs this effect twice before data-armed lands, and a second click would confirm.
    const frame = requestAnimationFrame(arm);
    const watch = new MutationObserver(arm);
    watch.observe(button, { attributes: true, attributeFilter: ["data-armed"] });
    return () => {
      cancelAnimationFrame(frame);
      watch.disconnect();
    };
  }, []);
  return <span ref={box}>{children}</span>;
}

export function HoldButtonDemo() {
  const t = useText();
  const onHold = () => notify(t(controls.heldDone));
  const hint = t(controls.approveHint);
  return (
    <Demo id="hold-button" title="HoldButton">
      <State name={t(foundation.rest)}>
        <HoldButton onHold={onHold} hint={hint}>
          {t(controls.approve)}
        </HoldButton>
      </State>
      <State name={t(foundation.armed)}>
        <Armed>
          <HoldButton onHold={onHold} hint={hint}>
            {t(controls.approve)}
          </HoldButton>
        </Armed>
      </State>
      <State name={t(foundation.disabled)}>
        <HoldButton onHold={onHold} hint={hint} disabled>
          {t(controls.approve)}
        </HoldButton>
      </State>
      <State name={t(foundation.wraps)} className="flex w-70 flex-col gap-2">
        <HoldButton onHold={onHold} hint={hint} wrap className="w-full">
          {t(controls.approve)}
        </HoldButton>
      </State>
    </Demo>
  );
}
