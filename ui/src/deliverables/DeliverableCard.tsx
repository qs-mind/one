// A Deliverable in the chat, where the Lead QS made it (a `data-deliverable` part): its title, kind, status, Revision,
// pending changes and open comments, kept up to date by the project's live stream, and "Open".
import { useEffect, useState } from "react";
import { subscribeActivity } from "../activity";
import { fill, pick, t, texts, useLanguage, type Text } from "../i18n";
import { StatusChips } from "../viewers/sheet/SheetViewer";
import { deliverablesApi } from "./api";
import type { DeliverableInfo } from "./types";
import type { Subscribe } from "./useDeliverable";

export function kindName(kind: DeliverableInfo["kind"]): string {
  return kind === "sheet" ? t("deliverableSheet") : kind === "document" ? t("deliverableDocument") : t("deliverableOther");
}

/** The small facts under a Deliverable's title: Revision, pending changes, open comments, sample data. */
export function Facts({ d }: { d: DeliverableInfo }) {
  return (
    <>
      <span className="text-slate">{d.revision !== null ? fill(t("reviewRev"), { n: d.revision }) : t("deliverableNoRevision")}</span>
      {(d.pending ?? 0) > 0 && <span>{fill(t("sheetPending"), { n: d.pending ?? 0 })}</span>}
      {d.open_comments > 0 && <span className="text-copper">{fill(t("openCommentsCount"), { n: d.open_comments })}</span>}
      {d.sample && <span className="rounded-full border border-slate px-2 text-xs leading-5">{t("sampleData")}</span>}
    </>
  );
}

export type DeliverableCardProps = {
  projectId: string;
  id: string;
  onOpen: (id: string) => void;
  subscribe?: Subscribe;
};

export function DeliverableCard({ projectId, id, onOpen, subscribe = subscribeActivity }: DeliverableCardProps) {
  useLanguage();
  const [entry, setEntry] = useState<DeliverableInfo | null>(null);
  const [failed, setFailed] = useState<Text | null>(null);

  useEffect(() => {
    let live = true;
    const load = () =>
      void deliverablesApi.list(projectId).then((answer) => {
        if (!live) return;
        const found = answer.ok ? answer.data.deliverables.find((d) => d.id === id) : undefined;
        if (found) setEntry(found);
        setFailed(found ? null : answer.ok ? texts.deliverableFailed : answer.error);
      });
    load();
    const stop = subscribe(
      projectId,
      (event) => {
        if (event.type === "deliverable" && event.deliverable.id === id) setEntry(event.deliverable);
      },
      load,
    );
    return () => {
      live = false;
      stop();
    };
  }, [projectId, id, subscribe]);

  if (!entry)
    return failed ? (
      <p role="alert" className="text-copper">
        {pick(failed)}
      </p>
    ) : null;
  return (
    <article
      aria-label={entry.title}
      className="flex flex-col gap-1 rounded-lg border border-ink/10 bg-paper p-3"
    >
      <div className="flex items-baseline gap-2">
        <span className="text-xs text-slate">{kindName(entry.kind)}</span>
        <h3 dir="auto" lang={entry.language} className="font-semibold">
          {entry.title}
        </h3>
      </div>
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <StatusChips view={entry} />
        <Facts d={entry} />
        <button
          type="button"
          className="ms-auto rounded bg-ink px-3 py-0.5 text-paper"
          aria-label={`${t("deliverableOpen")}: ${entry.title}`}
          onClick={() => onOpen(entry.id)}
        >
          {t("deliverableOpen")}
        </button>
      </div>
    </article>
  );
}
