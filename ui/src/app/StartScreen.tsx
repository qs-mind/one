// The start screen (docs/specs/2026-11-05-motion-design.md, section 1), shown each time ONE opens, for as long as the
// core is starting: on Paper, the mark alone draws itself, then «ONE» and the slogan come in, word by word (Arabic
// never by letter). It covers a real wait and never adds one beyond the drawing (under 1.5 s): once the drawing is
// done and the core is ready, its words fade on its Paper and ONE takes its place in one cut (never the two drawn at
// once: a crossfade showed step 1 through the mark). A core still
// starting after 3 s gets one quiet line; a core that is down gets its reason, its log and Retry here. Reduced
// motion: everything whole at once, and an instant swap.
import { useEffect, useRef, useState } from "react";
import { DRAW_MS, Mark } from "../brand/Mark";
import { dir, type Language, t } from "../i18n";
import { DUR, play, reducedMotion, useReducedMotion } from "../ui/motion";
import { CoreDown } from "./CoreDown";

/** «ONE» fades in as the face fills; the slogan's words follow WORD_GAP_MS apart. */
const ONE_AT = DRAW_MS - 100;
const WORDS_AT = DRAW_MS + 200;
const WORD_GAP_MS = 80;
const WORD_MS = 220;
/** The whole drawing, after which ONE may show: the last word in place. */
export const INTRO_MS = WORDS_AT + 3 * WORD_GAP_MS + WORD_MS + 40;
/** How long the core may start before the screen says it is still starting. */
export const SLOW_MS = 3000;

export type StartState = "starting" | "slow" | "down" | "ready";

export function StartScreen({
  state,
  log,
  lang,
  onRetry,
  onShow,
  onDone,
}: {
  state: StartState;
  log: string;
  lang: Language;
  onRetry(): void;
  /** The drawing is done and the core ready: show ONE beneath the screen as it leaves. */
  onShow(): void;
  /** The screen has left. */
  onDone(): void;
}) {
  const reduced = useReducedMotion();
  const [draw] = useState(() => !reducedMotion()); // decided once: a mark already drawn never draws again
  const [drawn, setDrawn] = useState(!draw);
  const [leaving, setLeaving] = useState(false);
  const screen = useRef<HTMLElement>(null);
  const content = useRef<HTMLDivElement>(null);
  const left = useRef(false);

  useEffect(() => {
    if (reduced) return setDrawn(true); // turned on mid-drawing: the CSS shows it whole, and nothing waits for it
    const timer = setTimeout(() => setDrawn(true), INTRO_MS);
    return () => clearTimeout(timer);
  }, [reduced]);

  useEffect(() => {
    if (state !== "ready" || !drawn || left.current) return;
    left.current = true;
    setLeaving(true);
    const el = content.current!;
    void play(
      el,
      [
        { opacity: 1, transform: "scale(1)" },
        { opacity: 0, transform: "scale(1.02)" },
      ],
      DUR.long,
    ).then(() => {
      el.style.opacity = "0"; // its end state until it is gone, so it never flashes back for a frame
      onShow(); // ONE and the Paper it replaces swap in the same frame
      onDone();
    });
  }, [state, drawn, onShow, onDone]);

  const words = t("startSlogan", lang).split(" ");
  return (
    <main
      ref={screen}
      data-start-screen=""
      data-intro={draw ? "" : undefined}
      lang={lang}
      dir={dir(lang)}
      aria-busy={state === "starting" || state === "slow"}
      className={`start-screen fixed inset-0 z-[100] flex flex-col items-center justify-center overflow-y-auto bg-paper px-4 py-8 text-ink ${leaving ? "pointer-events-none" : ""}`}
    >
      <p role="status" className="sr-only">
        {state === "down" ? "" : t("checking", lang)}
      </p>
      <div ref={content} className="flex w-full flex-col items-center">
        <Mark draw={draw} size={112} />
        <p className="start-one mt-7 font-logo text-[1.875rem] leading-none font-bold" style={{ animationDelay: `${ONE_AT}ms` }}>
          ONE
        </p>
        <p className="mt-3 text-lg text-slate">
          {words.map((word, i) => (
            <span key={i}>
              {i > 0 && " "}
              <span data-word="" className="start-word inline-block" style={{ animationDelay: `${WORDS_AT + i * WORD_GAP_MS}ms` }}>
                {word}
              </span>
            </span>
          ))}
        </p>
        {/* room kept for the quiet line, so nothing moves when it comes */}
        <p className="mt-2 min-h-6 text-xs text-slate">
          {state === "slow" && <span className="start-rise inline-block">{t("startEngine", lang)}</span>}
        </p>
        {state === "down" && <CoreDown logPath={log} onRetry={onRetry} lang={lang} />}
      </div>
    </main>
  );
}
