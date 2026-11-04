// Briefs a crash, power cut or closed app left unfinished. One never continues them by itself: each gets a card, and
// only Continue picks it up from its last Checkpoint.
import { useEffect, useState } from "react";
import { coreLine, send } from "../../core";
import { fill, pick, t, type Text, texts, useLanguage } from "../../i18n";
import type { BriefState } from "./types";

export type Unfinished = { id: string; chat_id: string; project_name: string | null; step: Text; state: BriefState };

export function ContinueBriefs({ onContinued }: { onContinued: (brief: Unfinished) => void }) {
  useLanguage();
  const [briefs, setBriefs] = useState<Unfinished[]>([]);
  const [busy, setBusy] = useState<string>();
  const [failed, setFailed] = useState<{ id: string; line: Text }>();

  useEffect(() => {
    let live = true;
    fetch("/api/briefs/unfinished")
      .then((response) => (response.ok ? (response.json() as Promise<{ briefs?: Unfinished[] }>) : undefined))
      .then((body) => live && body?.briefs && setBriefs(body.briefs))
      .catch(() => undefined); // nothing to offer
    return () => {
      live = false;
    };
  }, []);

  const drop = (id: string) => setBriefs((list) => list.filter((brief) => brief.id !== id));

  async function resume(brief: Unfinished) {
    setBusy(brief.id);
    setFailed(undefined);
    const response = await send(`/api/briefs/${encodeURIComponent(brief.id)}/continue`, "POST");
    setBusy(undefined);
    if (response?.ok) {
      drop(brief.id);
      onContinued(brief);
    } else {
      setFailed({ id: brief.id, line: await coreLine(response, texts.continueFailed) });
    }
  }

  if (briefs.length === 0) return null;
  return (
    <div className="flex flex-col gap-2 border-b border-stone px-4 py-3">
      {briefs.map((brief) => (
        <section key={brief.id} className="mx-auto flex w-full max-w-2xl flex-col gap-2 rounded-md border border-copper px-3 py-2">
          <p dir="auto" className="font-semibold">
            {brief.project_name ?? t("generalChat")}
          </p>
          <p dir="auto">{fill(t("continueBrief"), { step: pick(brief.step) })}</p>
          <div className="flex gap-2">
            <button
              type="button"
              disabled={busy === brief.id}
              onClick={() => void resume(brief)}
              className="rounded-md bg-ink px-3 py-1 text-paper disabled:opacity-40"
            >
              {t("continue")}
            </button>
            <button type="button" onClick={() => drop(brief.id)} className="rounded-md border border-ink px-3 py-1">
              {t("leave")}
            </button>
          </div>
          {failed?.id === brief.id && (
            <p role="alert" className="text-copper">
              {pick(failed.line)}
            </p>
          )}
        </section>
      ))}
    </div>
  );
}
