// A Deliverable's history: its Saved versions (each accept made one) and its Revisions (issued, and signed off).
// Pick any two to compare them.
import { useEffect, useState } from "react";
import { deliverablesApi } from "../deliverables/api";
import type { Versions, View } from "../deliverables/types";
import { count, fill, pick, t, type Text } from "../i18n";
import { ComparePanel } from "./ComparePanel";
import { authorName, when } from "./place";

export function VersionsPanel({ projectId, view }: { projectId: string; view: View }) {
  const [found, setFound] = useState<Versions | null>(null);
  const [failed, setFailed] = useState<Text | null>(null);
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [comparing, setComparing] = useState<{ from: string; to: string } | null>(null);

  useEffect(() => {
    let live = true;
    void deliverablesApi.versions(projectId, view.id).then((answer) => {
      if (!live) return;
      if (!answer.ok) return setFailed(answer.error);
      setFailed(null);
      setFound(answer.data);
      const last = answer.data.versions.at(-1)?.n;
      if (last !== undefined) {
        setTo(`v:${last}`);
        setFrom(`v:${Math.max(1, last - 1)}`);
      }
    });
    return () => {
      live = false;
    };
  }, [projectId, view.id, view.version, view.revision?.no]);

  if (failed)
    return (
      <p role="alert" className="text-copper">
        {pick(failed)}
      </p>
    );
  if (!found) return <p className="text-slate">{t("deliverableLoading")}</p>;
  const options = [
    ...found.versions.map((v) => ({ key: `v:${v.n}`, label: fill(t("reviewVersion"), { n: v.n }) })),
    ...found.revisions.map((r) => ({ key: `r:${r.no}`, label: fill(t("reviewRev"), { n: r.no }) })),
  ];
  const select = (label: string, value: string, set: (v: string) => void) => (
    <label className="flex items-center gap-1">
      {label}
      <select value={value} onChange={(e) => set(e.target.value)} className="rounded-lg border border-slate bg-paper px-2 py-1">
        {options.map((o) => (
          <option key={o.key} value={o.key}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  );

  return (
    <section aria-label={t("reviewVersions")} className="flex flex-col gap-3">
      <div className="grid gap-3 min-[600px]:grid-cols-2">
        <div>
          <h3 className="font-semibold">{t("reviewVersions")}</h3>
          <p className="text-sm text-slate">{t("reviewVersionsHelp")}</p>
          <ol className="flex flex-col">
            {[...found.versions].reverse().map((v) => (
              <li key={v.n} className="flex flex-wrap gap-x-2">
                <span>{fill(t("reviewVersion"), { n: v.n })}</span>
                <span className="text-slate">{when(v.at)}</span>
                <span className="text-slate">{fill(t("reviewBy"), { who: authorName(v.by) })}</span>
                <span className="text-slate">
                  {v.changes.length ? count("reviewChangesCount", v.changes.length) : t("reviewNoChanges")}
                </span>
              </li>
            ))}
          </ol>
        </div>
        <div>
          <h3 className="font-semibold">{t("reviewRevisions")}</h3>
          <p className="text-sm text-slate">{t("reviewRevisionsHelp")}</p>
          {found.revisions.length === 0 && <p className="text-slate">{t("deliverableNoRevision")}</p>}
          <ol className="flex flex-col">
            {[...found.revisions].reverse().map((r) => (
              <li key={r.no} className="flex flex-wrap gap-x-2">
                <span>{fill(t("reviewRev"), { n: r.no })}</span>
                <span className="text-slate">{when(r.issued_at)}</span>
                <span className="text-slate">{fill(t("reviewVersion"), { n: r.version_n })}</span>
                <span className={r.signed_off ? "font-semibold" : "text-slate"}>
                  {r.signed_off ? t("statusSignedOff") : t("reviewIssued")}
                </span>
              </li>
            ))}
          </ol>
        </div>
      </div>
      {options.length > 1 && (
        <form
          className="flex flex-wrap items-center gap-3"
          onSubmit={(event) => {
            event.preventDefault();
            setComparing({ from, to });
          }}
        >
          {select(t("reviewFrom"), from, setFrom)}
          {select(t("reviewTo"), to, setTo)}
          <button type="submit" disabled={from === to} className="rounded-lg border border-ink/20 px-3 py-1 hover:bg-stone disabled:opacity-40">
            {t("reviewCompare")}
          </button>
        </form>
      )}
      {comparing && <ComparePanel projectId={projectId} deliverableId={view.id} from={comparing.from} to={comparing.to} />}
    </section>
  );
}
