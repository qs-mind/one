import { useEffect, useState } from "react";
import { dir, fill, t, useLanguage, type Text } from "../../i18n";
import type { ProjectSources } from "../../project/types";
import { SourceError } from "../../project/sources";
import { FilePages, SMALL, LARGE, type FilePage } from "./FileDoc";
import { compareApi, type Citation, type CompareFile, type Comparison, type ChangedPage } from "./compareApi";

function Page({ sources, citation, width }: { sources: ProjectSources; citation: Citation; width: number }) {
  const state: FilePage = { page: citation.page, pages: citation.page, setPage: () => {}, mode: "image", setMode: () => {}, pageOf: fill(t("page"), { page: citation.page }) };
  return <FilePages sources={sources} fileId={citation.file_id} state={state} width={width} controls={false} />;
}
function Overlay({ projectId, change, width }: { projectId: string; change: ChangedPage; width: number }) {
  useLanguage();
  const [url, setUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let live = true;
    let owned: string | undefined;
    setUrl(null); setFailed(false);
    compareApi.overlay(projectId, change.old.file_id, change.new.file_id, change.old.page, change.new.page, width).then(
      (got) => { if (live) { owned = got; setUrl(got); } else URL.revokeObjectURL(got); },
      () => live && setFailed(true),
    );
    return () => { live = false; if (owned) URL.revokeObjectURL(owned); };
  }, [projectId, change, width]);
  return failed ? <p role="alert">{t("pageNotShown")}</p> : url ? <img className="w-full" src={url} alt={t("compareOverlay")} /> : null;
}

export function CompareDoc({ projectId, fileId, sources, onClose }: { projectId: string; fileId: string; sources: ProjectSources; onClose(): void }) {
  const lang = useLanguage();
  const [files, setFiles] = useState<CompareFile[]>([]);
  const [old, setOld] = useState("");
  const [result, setResult] = useState<Comparison | null>(null);
  const [selected, setSelected] = useState(0);
  const [error, setError] = useState<Text | "compareFailed" | null>(null);
  const [width, setWidth] = useState<number>(SMALL);
  useEffect(() => {
    let live = true;
    compareApi.files(projectId).then((got) => {
      if (!live) return;
      setFiles(got);
      setOld(got.find((f) => f.id === fileId)?.replaces ?? "");
    }, () => live && setError("compareFailed"));
    return () => { live = false; };
  }, [projectId, fileId]);
  useEffect(() => {
    let live = true;
    setResult(null); setSelected(0); setError(null);
    if (old) compareApi.compare(projectId, old, fileId).then(
      (got) => live && setResult(got),
      (e) => live && setError(e instanceof SourceError ? e.line : "compareFailed"),
    );
    return () => { live = false; };
  }, [old, fileId, projectId]);
  const cite = (c: Citation) => `${c.name} · ${fill(t("page"), { page: c.page })} · ${c.date}`;
  const selectedPage = result?.changed[selected];
  return <section dir={dir()} className="h-full overflow-auto bg-paper p-3 text-ink">
    <div className="flex flex-wrap items-center gap-3">
      <button type="button" onClick={onClose}>{t("close")}</button>
      <label>{t("compareChoose")} <select value={old} onChange={(e) => setOld(e.target.value)}>
        <option value="">{t("compareChoose")}</option>
        {files.filter((f) => f.id !== fileId).map((f) => <option key={f.id} value={f.id}>{f.name} · {f.added_at}</option>)}
      </select></label>
      <button type="button" aria-pressed={width === LARGE} onClick={() => setWidth(width === SMALL ? LARGE : SMALL)}>{t("pageViewImage")} +</button>
    </div>
    {error && <p role="alert">{typeof error === "string" ? t(error) : error[lang]}</p>}
    {old && !result && !error && <p role="status">{t("compareLoading")}</p>}
    {result && <>
      <p className="py-2 text-sm text-slate">{t("compareScope")} {result.compared_at}</p>
      <p>{t("compareUnchanged")}: {result.unchanged}</p>
      {result.pairs.filter((pair) => pair.pairing_note).map((pair) => <p key={`${pair.old.page}-${pair.new.page}`} className="py-2 text-copper">
        {cite(pair.old)} → {cite(pair.new)}: {pair.pairing_note?.[lang]}
      </p>)}
      {result.changed.length === 0 && <p>{t("compareNoChanges")}</p>}
      <ul className="my-3 flex flex-col gap-2">{result.changed.map((change, index) => <li key={`${change.old.page}-${change.new.page}`}>
        <button type="button" aria-pressed={selected === index} onClick={() => setSelected(index)} className="text-start underline">
          {cite(change.old)} → {cite(change.new)}: {change.summary[lang]}
        </button>
      </li>)}</ul>
      {selectedPage && <>
        <p>{t(({ sheet: "compareSheet", title: "compareTitle", order: "compareOrder" } as const)[selectedPage.method])}</p>
        <p>{t("compareRemoved")}: <bdi>{selectedPage.removed.join(" ")}</bdi></p>
        <p>{t("compareAdded")}: <bdi>{selectedPage.added.join(" ")}</bdi></p>
        <div className="grid gap-3 lg:grid-cols-3">
          <figure><figcaption>{t("compareOld")} · {cite(selectedPage.old)}</figcaption><Page sources={sources} citation={selectedPage.old} width={width} /></figure>
          <figure><figcaption>{t("compareNewer")} · {cite(selectedPage.new)}</figcaption><Page sources={sources} citation={selectedPage.new} width={width} /></figure>
          {selectedPage.overlay && <figure><figcaption>{t("compareOverlay")} · {t("compareLegend")}</figcaption><Overlay projectId={projectId} change={selectedPage} width={width} /></figure>}
        </div>
      </>}
      {([ ["compareUnpairedOld", result.unpaired_old], ["compareUnpairedNew", result.unpaired_new] ] as const).map(([label, pages]) => pages.length > 0 && <div key={label}>
        <h3>{t(label)}</h3><ul>{pages.map((page) => <li key={page.page}>{cite(page)}</li>)}</ul>
      </div>)}
    </>}
  </section>;
}
