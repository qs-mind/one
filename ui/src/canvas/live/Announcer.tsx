// The one polite live region for the team: it says when an agent starts working, waits for the engineer, finishes,
// stops on an error or goes silent, in the page language, at most once every 2 s (what comes in between is said
// together, the latest per agent). Never a cursor move, never streamed text. Mounted once by the shell.
import { useEffect, useState } from "react";
import { fill, pick, t } from "../../i18n";
import { subscribeChanges, type Change } from "./activity";

export const ANNOUNCE_GAP_MS = 2000;

const busy = (state: string | undefined) => state === "working" || state === "thinking";

/** The words for a change, or null when it is not worth saying (thinking after working is the same news). */
export function lineFor({ agent, before }: Change): string | null {
  const role = pick(agent.role);
  if (agent.noNews && !before?.noNews) return fill(t("announceNoNews"), { role });
  if (before?.state === agent.state) return null;
  if (agent.state === "waiting") return fill(t("announceWaiting"), { role });
  if (agent.state === "done") return fill(t("announceDone"), { role });
  if (agent.state === "failed") return fill(t("announceFailed"), { role });
  if (busy(agent.state) && !busy(before?.state)) return fill(t("announceWorking"), { role });
  return null;
}

export function Announcer() {
  const [text, setText] = useState("");
  useEffect(() => {
    let last = -Infinity;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const pending = new Map<string, Change>();
    const say = () => {
      timer = undefined;
      const lines = [...pending.values()].map(lineFor).filter((l): l is string => l !== null);
      pending.clear();
      if (!lines.length) return;
      setText(lines.join(". "));
      last = Date.now();
    };
    const off = subscribeChanges((changes) => {
      for (const change of changes) {
        if (!lineFor(change)) continue;
        pending.delete(change.agent.id); // the latest word per agent, in the order they came
        pending.set(change.agent.id, change);
      }
      if (!pending.size || timer) return;
      const wait = last + ANNOUNCE_GAP_MS - Date.now();
      if (wait <= 0) say();
      else timer = setTimeout(say, wait);
    });
    return () => {
      off();
      clearTimeout(timer);
    };
  }, []);
  return (
    <div role="status" aria-live="polite" className="sr-only">
      {text}
    </div>
  );
}
