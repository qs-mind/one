// Undo instead of "are you sure?" (core: qsone/undo.py). The removal has already happened; this shows in its place,
// «اتشال «X» · تراجع», with a 1 px line shrinking back to the side the words start on over the core's real window.
// Pointing at it, or focusing Undo, pauses the line and the core's window with it, so the time shown is the time there
// is. Undo takes it back (`onUndone`); when the window ends the removal is for good (`onEnd`). Too late at the core:
// the core's own words say so. With reduced motion the line does not move; the window is just as long.
import { useEffect, useRef, useState } from "react";
import { coreLine, send } from "../core";
import { pick, t, type Text, texts, useLanguage } from "../i18n";
import { reducedMotion } from "./motion";

export function UndoNotice({
  label,
  token,
  windowMs,
  onUndone,
  onEnd,
  takeFocus = true,
}: {
  /** What was removed: «اتشال «عينة»». */
  label: string;
  /** The core's Undo token for it, and its window (the answer to the removal). */
  token: string;
  windowMs: number;
  onUndone: () => void;
  onEnd: () => void;
  /** Off when the focus is still somewhere useful (a keyboard review going on); else it comes here. */
  takeFocus?: boolean;
}) {
  useLanguage();
  const box = useRef<HTMLDivElement>(null);
  const line = useRef<HTMLSpanElement>(null);
  const animation = useRef<Animation>(undefined);
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const left = useRef(windowMs);
  const since = useRef(0);
  const reasons = useRef(new Set<"pointer" | "focus">());
  const ended = useRef(false);
  const [failed, setFailed] = useState<Text>();
  const end = useRef(onEnd);
  end.current = onEnd;
  const path = `/undo/${encodeURIComponent(token)}`;

  function run() {
    since.current = Date.now();
    timer.current = setTimeout(() => {
      ended.current = true;
      end.current();
    }, left.current);
  }

  useEffect(() => {
    const el = line.current;
    if (el && !reducedMotion() && typeof el.animate === "function") {
      animation.current = el.animate([{ transform: "scaleX(1)" }, { transform: "scaleX(0)" }], {
        duration: windowMs,
        easing: "linear",
        fill: "forwards",
      });
    }
    if (takeFocus) box.current?.focus({ preventScroll: true }); // the removed row's button is gone: focus stays here
    run();
    return () => {
      clearTimeout(timer.current);
      animation.current?.cancel();
    };
  }, []); // once, for this removal

  function pause(why: "pointer" | "focus") {
    if (ended.current) return;
    const was = reasons.current.size;
    reasons.current.add(why);
    if (was) return;
    clearTimeout(timer.current);
    left.current = Math.max(0, left.current - (Date.now() - since.current));
    animation.current?.pause();
    void send(`${path}/pause`, "POST");
  }

  function resume(why: "pointer" | "focus") {
    if (ended.current || !reasons.current.delete(why) || reasons.current.size) return;
    animation.current?.play();
    void send(`${path}/resume`, "POST");
    run();
  }

  async function undo() {
    clearTimeout(timer.current);
    ended.current = true;
    const response = await send(path, "POST");
    if (response?.ok) return onUndone();
    setFailed(await coreLine(response, texts.undoFailed));
  }

  return (
    <div
      ref={box}
      role="status"
      tabIndex={-1}
      onPointerEnter={() => pause("pointer")}
      onPointerLeave={() => resume("pointer")}
      className="relative flex flex-wrap items-baseline gap-x-1.5 pb-1 focus:outline-none"
    >
      <span dir="auto">{label}</span>{" "}
      <span aria-hidden="true" className="text-slate">
        ·
      </span>{" "}
      {failed ? (
        <span role="alert" className="text-copper">
          {pick(failed)}
        </span>
      ) : (
        <button
          type="button"
          onClick={() => void undo()}
          onFocus={() => pause("focus")}
          onBlur={() => resume("focus")}
          className="font-semibold underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-ink"
        >
          {t("undo")}
        </button>
      )}
      <span ref={line} aria-hidden="true" className="undo-line text-slate" />
    </div>
  );
}
