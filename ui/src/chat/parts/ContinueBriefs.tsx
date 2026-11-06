// Briefs a crash, power cut or closed app left unfinished. One never continues them by itself: each gets one line in
// the chat it belongs to (never in another), and only Continue picks it up from its last Checkpoint. «Leave it» tells
// the core, which ends the Brief, so it is never offered again. The list is read again each time the chat changes
// (and when ONE comes back after its core was down: the screen is built again).
import { useEffect, useState } from "react";
import { api } from "../../api";
import { coreLine, send } from "../../core";
import { fill, pick, t, type Text, texts, useLanguage } from "../../i18n";
import type { BriefState } from "./types";

export type Unfinished = { id: string; chat_id: string; project_name: string | null; step: Text; state: BriefState };

export function ContinueBriefs({
  chatId,
  onContinued,
  onLeft,
}: {
  /** The chat on the screen: only its own unfinished Briefs show. */
  chatId: string;
  onContinued: (brief: Unfinished) => void;
  /** The core ended a Brief the engineer left: the chat reads it again. */
  onLeft?: (brief: Unfinished) => void;
}) {
  useLanguage();
  const [briefs, setBriefs] = useState<Unfinished[]>([]);
  const [busy, setBusy] = useState<string>();
  const [failed, setFailed] = useState<{ id: string; line: Text }>();

  useEffect(() => {
    let live = true;
    setBriefs([]);
    api("/briefs/unfinished")
      .then((response) => (response.ok ? (response.json() as Promise<{ briefs?: Unfinished[] }>) : undefined))
      .then((body) => live && body?.briefs && setBriefs(body.briefs))
      .catch(() => undefined); // nothing to offer
    return () => {
      live = false;
    };
  }, [chatId]);

  const drop = (id: string) => setBriefs((list) => list.filter((brief) => brief.id !== id));

  async function act(brief: Unfinished, how: "continue" | "leave") {
    setBusy(brief.id);
    setFailed(undefined);
    const response = await send(`/briefs/${encodeURIComponent(brief.id)}/${how}`, "POST");
    setBusy(undefined);
    if (response?.ok) {
      drop(brief.id);
      if (how === "continue") onContinued(brief);
      else onLeft?.(brief);
    } else {
      const fallback = how === "continue" ? texts.continueFailed : texts.leaveFailed;
      setFailed({ id: brief.id, line: await coreLine(response, fallback) });
    }
  }

  const here = briefs.filter((brief) => brief.chat_id === chatId);
  if (here.length === 0) return null;
  return (
    <div className="flex flex-col gap-2 px-5 pb-1 pt-3">
      {here.map((brief) => {
        const line = fill(t("continueBriefLine"), { step: pick(brief.step) });
        return (
          <section
            key={brief.id}
            aria-label={line}
            data-continue-brief={brief.id}
            className="mx-auto flex w-full max-w-2xl flex-wrap items-center gap-x-3 gap-y-1 rounded-[14px] border border-copper px-4 py-1.5"
          >
            <p dir="auto" className="min-w-0 flex-1 basis-40 break-words">
              {line}
            </p>
            <div className="flex shrink-0 gap-1.5">
              <button
                type="button"
                disabled={busy === brief.id}
                onClick={() => void act(brief, "continue")}
                className="rounded-lg bg-ink px-3 py-1 text-paper disabled:opacity-40"
              >
                {t("continue")}
              </button>
              <button
                type="button"
                disabled={busy === brief.id}
                onClick={() => void act(brief, "leave")}
                className="rounded-lg border border-ink px-3 py-1 disabled:opacity-40"
              >
                {t("leave")}
              </button>
            </div>
            {failed?.id === brief.id && (
              <p role="alert" className="w-full text-copper">
                {pick(failed.line)}
              </p>
            )}
          </section>
        );
      })}
    </div>
  );
}
