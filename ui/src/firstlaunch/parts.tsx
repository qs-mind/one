// What every first-launch screen shares: its frame (title, help, the step's own content, then Back, Skip and Next),
// the buttons and the fields, in the screen's usual look: Paper, Stone surfaces, Ink for the one main action.
import { type ReactNode, useEffect, useId, useRef, useSyncExternalStore } from "react";
import { t, useLanguage } from "../i18n";

export type Step = "language" | "account" | "ai" | "card" | "usage";
export const STEPS: readonly Step[] = ["language", "account", "ai", "card", "usage"];
export type StepState = "done" | "skipped" | null;
export type Setup = { done: boolean; steps: Record<Step, StepState> };

/** What the flow gives each step: Back (none on the first screen) and the step's end, saved in the core. `pass`
 * resolves false when the core did not save it (the screen then says so and stays). */
export type Nav = {
  back?: () => void;
  pass: (state: "done" | "skipped") => Promise<boolean>;
};

// Opening the flow from inside the app -------------------------------------------------------------------------------

type Request = { from: Step; only: boolean };
let request: Request | null = null;
const listeners = new Set<() => void>();
const changed = (next: Request | null) => {
  request = next;
  for (const listener of listeners) listener();
};

/** Opens the flow over the app, at `from`; with `only`, that one step, then back to the app. */
export function openSetup(from: Step = "language", only = false) {
  changed({ from, only });
}

export function useSetupRequest() {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    () => request,
  );
}

/** Back to the app. */
export function closeSetup() {
  changed(null);
}

// Colour changes ease over 150 ms, so a hover or a choice never snaps.
const ease = "transition-colors duration-150 ease-out";
export const primary = `rounded-md bg-ink px-5 py-2.5 text-paper hover:bg-ink/90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink disabled:opacity-40 ${ease}`;
export const secondary = `rounded-md bg-stone px-5 py-2.5 text-ink hover:bg-ink/[0.08] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink disabled:opacity-40 ${ease}`;
export const quiet = `rounded-md px-3 py-2.5 text-slate hover:bg-stone hover:text-ink focus-visible:outline-2 focus-visible:outline-ink disabled:opacity-40 ${ease}`;
export const field = `h-11 w-full rounded-md border border-slate/40 bg-paper px-3 outline-none focus:border-ink ${ease}`;
/** A choice the engineer picks among a few: a quiet frame on Paper at rest, Ink once chosen. Its text aligns to the
 * start unless the caller says otherwise. */
export const option = (chosen: boolean) =>
  `rounded-lg border px-4 py-3 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink disabled:opacity-40 ${ease} ${
    chosen ? "border-ink bg-ink text-paper" : "border-ink/15 bg-paper text-ink hover:bg-stone"
  }`;

export type Progress = "busy" | "done" | "failed";

/** How a check, a sign-in or a save is going, in the same look on every step, without a colour of its own: a quiet
 * Slate ring turning while it runs (shown after 300 ms, so a quick one never flashes); a filled Ink circle whose check
 * draws itself once it worked, the line in Ink; Copper with a ring and "!" when it did not, the line saying what to do
 * next. Each line rises into place, and scrolls into view when it lands below the window's edge. With `fade`, a done
 * line fades out after a moment, keeping its place (a quiet "Saved"). */
export function Feedback({ state, children, fade = false }: { state: Progress; children: ReactNode; fade?: boolean }) {
  const line = useRef<HTMLParagraphElement>(null);
  const shown = Boolean(children);
  useEffect(() => {
    if (!shown) return;
    const still = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    line.current?.scrollIntoView?.({ block: "nearest", behavior: still ? "auto" : "smooth" });
  }, [state, shown]);
  if (!shown) return null;
  const look = state === "done" ? "font-medium text-ink" : state === "failed" ? "text-copper" : "text-slate";
  return (
    <p
      ref={line}
      role={state === "failed" ? "alert" : "status"}
      data-feedback={state}
      className={`${state === "busy" ? "fl-rise-late" : fade ? "fl-fade" : "fl-rise"} flex items-start gap-2.5 ${look}`}
    >
      <span aria-hidden="true" className="flex h-[1lh] shrink-0 items-center">
        {state === "busy" && <span className="fl-spin block size-4 rounded-full border-2 border-slate/25 border-t-slate" />}
        {state === "done" && (
          <svg viewBox="0 0 20 20" className="size-5">
            <circle cx="10" cy="10" r="10" className="fill-ink" />
            <path d="M5.8 10.4l2.8 2.8 5.6-5.8" fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="fl-check stroke-paper" />
          </svg>
        )}
        {state === "failed" && (
          <svg viewBox="0 0 20 20" className="size-5">
            <circle cx="10" cy="10" r="9" fill="none" strokeWidth="1.5" className="stroke-copper" />
            <path d="M10 5.5v5.5" strokeWidth="2" strokeLinecap="round" className="stroke-copper" />
            <circle cx="10" cy="14.3" r="1.15" className="fill-copper" />
          </svg>
        )}
      </span>
      <span className="min-w-0">{children}</span>
    </p>
  );
}

export function Alert({ children }: { children: ReactNode }) {
  return <Feedback state="failed">{children}</Feedback>;
}

/** One screen of the flow. Its heading takes focus when it opens, so a screen reader hears each new step. */
export function StepScreen({
  title,
  help,
  children,
  nav,
  skip = true,
  onSkip,
  next,
  failed,
}: {
  title: string;
  help?: ReactNode;
  children?: ReactNode;
  nav: Nav;
  /** False on a screen with nothing to skip. */
  skip?: boolean;
  /** In place of passing the step as skipped at once (Account first stops a sign-in that is waiting). */
  onSkip?: () => void;
  /** The step's main action, at the end of the row. */
  next?: ReactNode;
  failed?: ReactNode;
}) {
  useLanguage();
  const heading = useRef<HTMLHeadingElement>(null);
  const id = useId();
  useEffect(() => heading.current?.focus({ preventScroll: true }), [title]);
  return (
    <section aria-labelledby={id} className="flex flex-col gap-8">
      <div className="flex flex-col gap-3">
        <h1 id={id} ref={heading} tabIndex={-1} className="text-2xl font-semibold text-ink outline-none">
          {title}
        </h1>
        {help && <p className="text-slate">{help}</p>}
      </div>
      {children}
      <Alert>{failed}</Alert>
      <div className="flex flex-wrap items-center gap-2 pt-2">
        {nav.back && (
          <button type="button" onClick={nav.back} className={`${quiet} -ms-3`}>
            {t("setupBack")}
          </button>
        )}
        <div className="ms-auto flex flex-wrap items-center gap-2">
          {skip && (
            <button type="button" onClick={onSkip ?? (() => void nav.pass("skipped"))} className={quiet}>
              {t("setupSkip")}
            </button>
          )}
          {next}
        </div>
      </div>
    </section>
  );
}
