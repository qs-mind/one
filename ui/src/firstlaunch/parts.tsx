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

export const primary =
  "rounded-md bg-ink px-5 py-2.5 text-paper hover:bg-ink/90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink disabled:opacity-40";
export const secondary =
  "rounded-md bg-stone px-5 py-2.5 text-ink hover:bg-ink/[0.08] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink disabled:opacity-40";
export const quiet =
  "rounded-md px-3 py-2.5 text-slate hover:bg-stone hover:text-ink focus-visible:outline-2 focus-visible:outline-ink disabled:opacity-40";
export const field = "w-full rounded-md border border-slate/40 bg-paper px-3 py-2 outline-none focus:border-ink";
/** A choice the engineer picks among a few: Stone at rest, Ink once chosen. */
export const option = (chosen: boolean) =>
  `rounded-lg px-4 py-3 text-start focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink disabled:opacity-40 ${
    chosen ? "bg-ink text-paper" : "bg-stone text-ink hover:bg-ink/[0.08]"
  }`;

export function Alert({ children }: { children: ReactNode }) {
  return children ? (
    <p role="alert" className="text-copper">
      {children}
    </p>
  ) : null;
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
