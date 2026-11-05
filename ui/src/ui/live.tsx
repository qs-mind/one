// ONE saves and checks as the engineer goes: no Save or Check button. A pasted key is checked at once; a typed one
// after a pause in typing, and only once it is long enough to be a whole key, so no half key ever leaves the page.
// A choice saves when it is made; a text field after a pause (when what it holds is whole) or on leaving it. A newer
// value stops the older check or save, so only the latest answer shows. A failure keeps what the engineer typed.
import { useCallback, useEffect, useRef, useState } from "react";
import { Feedback } from "../firstlaunch/parts";
import { pick, t, type Text, texts, useLanguage } from "../i18n";

/** How long typing must stop before a field is saved or checked. */
export const PAUSE = 700;

/** The shortest whole key: a Claude key is about 100 characters, a Brave Search key about 30. */
export const KEY_MIN = { claude: 40, brave: 20 } as const;

/** Long enough, with no space inside, to be a whole key: anything shorter is still being typed, or was cut short. */
export function looksLikeKey(value: string, min: number): boolean {
  const key = value.trim();
  return key.length >= min && !/\s/.test(key);
}

/** An amount as exact decimal text: "12", "0.50". */
export const looksLikeAmount = (value: string) => /^\d+(\.\d+)?$/.test(value.trim());

export type Live = { state: "idle" | "short" | "busy" | "done" } | { state: "failed"; line: Text };

/** A key field that checks itself. `run` saves and checks one whole key (at least `min` characters) and answers null
 * when it works, or the line to show; it gets a signal that a newer value aborts. A key that failed stays in the
 * field, to be fixed; one that works leaves it (the page never holds a saved key). */
export function useLiveKey(min: number, run: (key: string, signal: AbortSignal) => Promise<Text | null>) {
  const [value, setValue] = useState("");
  const [live, setLive] = useState<Live>({ state: "idle" });
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const flight = useRef<AbortController>(undefined);
  const pasted = useRef(false);
  const latest = useRef(run);
  latest.current = run;

  const stop = useCallback(() => {
    clearTimeout(timer.current);
    flight.current?.abort();
    flight.current = undefined;
  }, []);
  useEffect(() => stop, [stop]);

  const start = useCallback(
    async (key: string) => {
      stop();
      const controller = new AbortController();
      flight.current = controller;
      setLive({ state: "busy" });
      const line = await latest.current(key.trim(), controller.signal).catch(() => texts.keyFailed);
      if (controller.signal.aborted) return; // a newer value took over: its answer is the one to show
      flight.current = undefined;
      setLive(line ? { state: "failed", line } : { state: "done" });
      if (!line) setValue("");
    },
    [stop],
  );

  const change = useCallback(
    (next: string) => {
      setValue(next);
      stop();
      const now = pasted.current;
      pasted.current = false;
      if (!next.trim()) return setLive({ state: "idle" });
      // what shows stays until the pause: a line never blinks on each keystroke
      if (!looksLikeKey(next, min)) timer.current = setTimeout(() => setLive({ state: "short" }), PAUSE);
      else if (now) void start(next);
      else timer.current = setTimeout(() => void start(next), PAUSE);
    },
    [min, start, stop],
  );

  const field = {
    value,
    onChange: (event: { target: { value: string } }) => change(event.target.value),
    onPaste: () => void (pasted.current = true),
  };
  /** The same key checked once more (after no internet, a busy provider): the field keeps it. */
  const again = useCallback(() => void (looksLikeKey(value, min) && start(value)), [value, min, start]);
  return { field, live, again };
}

export type Saving = { state: "idle" | "busy" | "done" } | { state: "failed"; line: Text };
type Job = () => Promise<Text | null>;

/** Saves as the engineer goes. `now` saves at once (a choice, leaving a field); `later` after a pause in typing, or,
 * with `pause` false, only when the field is left (`flush`). Saves run one after another, in the order made, so the
 * last one made is the one kept; `n` counts the answers, so each "Saved" shows anew. A save still waiting when the
 * screen closes is made then. */
export function useSaving() {
  const [saving, setSaving] = useState<Saving>({ state: "idle" });
  const [n, setN] = useState(0);
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const waiting = useRef<Job>(undefined);
  const last = useRef<Promise<boolean>>(Promise.resolve(true));
  const made = useRef(0);

  const now = useCallback((job: Job): Promise<boolean> => {
    clearTimeout(timer.current);
    waiting.current = undefined;
    const mine = ++made.current;
    setSaving({ state: "busy" });
    const done = last.current.then(job).then(
      (line) => {
        if (mine === made.current) {
          setSaving(line ? { state: "failed", line } : { state: "done" });
          setN((count) => count + 1);
        }
        return !line;
      },
      () => false,
    );
    last.current = done;
    return done;
  }, []);

  const later = useCallback(
    (job: Job, pause = true) => {
      clearTimeout(timer.current);
      waiting.current = job;
      if (pause) timer.current = setTimeout(() => void now(job), PAUSE);
    },
    [now],
  );

  /** Nothing to save any more (a field emptied before its pause). */
  const drop = useCallback(() => {
    clearTimeout(timer.current);
    waiting.current = undefined;
  }, []);

  /** Makes the save that waits, if any; resolves once every save made so far is done, true when the last worked. */
  const flush = useCallback(() => (waiting.current ? now(waiting.current) : last.current), [now]);

  useEffect(
    () => () => {
      clearTimeout(timer.current);
      if (waiting.current) void waiting.current();
    },
    [],
  );
  return { saving, n, now, later, drop, flush };
}

/** The line under a field that saves itself, in a slot that keeps its height, so nothing below it moves: "Saving…"
 * (after 300 ms, so a quick save never flashes), a check mark with "Saved" that fades, or what failed, in Copper,
 * which stays until the next save. */
export function SaveNote({ saving, n }: { saving: Saving; n: number }) {
  useLanguage();
  return (
    <div className="min-h-7" data-save-note>
      {saving.state === "busy" && <Feedback state="busy">{t("saving")}</Feedback>}
      {saving.state === "done" && (
        <Feedback key={n} state="done" fade>
          {t("saved")}
        </Feedback>
      )}
      {saving.state === "failed" && (
        <Feedback key={n} state="failed">
          {pick(saving.line)}
        </Feedback>
      )}
    </div>
  );
}
