// The Project Index: every Deliverable of the open project, newest first, with its kind, latest Revision, status,
// pending changes and open comments. The live stream keeps it current; a row opens the viewer.
import { useEffect, useState } from "react";
import { subscribeActivity } from "../activity";
import { fill, pick, t, useLanguage, type Text } from "../i18n";
import { StatusChips } from "../viewers/sheet/SheetViewer";
import { deliverablesApi } from "./api";
import { kindName } from "./DeliverableCard";
import type { DeliverableInfo } from "./types";
import type { Subscribe } from "./useDeliverable";

const newestFirst = (a: DeliverableInfo, b: DeliverableInfo) => b.updated_at.localeCompare(a.updated_at);

export type ProjectIndexProps = {
  projectId: string;
  onOpen: (id: string) => void;
  onClose?: () => void;
  subscribe?: Subscribe;
};

export function ProjectIndex({ projectId, onOpen, onClose, subscribe = subscribeActivity }: ProjectIndexProps) {
  useLanguage();
  const [list, setList] = useState<DeliverableInfo[] | null>(null);
  const [failed, setFailed] = useState<Text | null>(null);

  useEffect(() => {
    let live = true;
    const load = () =>
      void deliverablesApi.list(projectId).then((answer) => {
        if (!live) return;
        if (answer.ok) {
          setFailed(null);
          setList([...answer.data.deliverables].sort(newestFirst));
        } else setFailed(answer.error);
      });
    load();
    const stop = subscribe(
      projectId,
      (event) => {
        if (event.type !== "deliverable") return;
        const entry = event.deliverable;
        setList((now) => [entry, ...(now ?? []).filter((d) => d.id !== entry.id)].sort(newestFirst));
      },
      load,
    );
    return () => {
      live = false;
      stop();
    };
  }, [projectId, subscribe]);

  const cell = "border-b border-stone px-2 py-1 text-start align-baseline";
  return (
    <section aria-labelledby="project-index" className="flex flex-col gap-3 p-4">
      <div className="flex items-center justify-between gap-2">
        <h2 id="project-index" className="font-semibold">
          {t("deliverables")}
        </h2>
        {onClose && (
          <button type="button" className="rounded px-2 hover:bg-stone" onClick={onClose}>
            {t("close")}
          </button>
        )}
      </div>
      {failed && (
        <p role="alert" className="text-copper">
          {pick(failed)}
        </p>
      )}
      {list?.length === 0 && <p className="text-slate">{t("deliverablesEmpty")}</p>}
      {list && list.length > 0 && (
        <table className="w-full border-collapse">
          <thead>
            <tr className="text-slate">
              <th className={`${cell} font-normal`}>{t("deliverableTitle")}</th>
              <th className={`${cell} font-normal`}>{t("deliverableType")}</th>
              <th className={`${cell} font-normal`}>{t("reviewRevisions")}</th>
              <th className={`${cell} font-normal`}>{t("deliverableStatus")}</th>
              <th className={`${cell} font-normal`}>{t("reviewChanges")}</th>
              <th className={`${cell} font-normal`}>{t("reviewComments")}</th>
            </tr>
          </thead>
          <tbody>
            {list.map((d) => (
              <tr key={d.id}>
                <td className={cell}>
                  <button
                    type="button"
                    dir="auto"
                    lang={d.language}
                    className="text-start font-semibold underline decoration-ink/20 hover:text-copper"
                    onClick={() => onOpen(d.id)}
                  >
                    {d.title}
                  </button>
                </td>
                <td className={cell}>{kindName(d.kind)}</td>
                <td className={cell}>{d.revision !== null ? fill(t("reviewRev"), { n: d.revision }) : "—"}</td>
                <td className={cell}>
                  <span className="flex flex-wrap gap-1">
                    <StatusChips view={d} />
                  </span>
                </td>
                <td className={cell}>
                  <bdi>{d.pending ?? 0}</bdi>
                </td>
                <td className={`${cell} ${d.open_comments > 0 ? "text-copper" : ""}`}>
                  <bdi>{d.open_comments}</bdi>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
