import { useEffect, useRef, useState } from "react";
import { deliverablesApi } from "../../deliverables/api";
import type { PackFiles, PackStep, PackView } from "../../deliverables/types";
import { fill, language, pick, t } from "../../i18n";

const labels = { file: "packFile", cover: "packCover", divider: "packDivider", stamp: "packStamp", page_numbers: "packNumbers", seal: "packSeal" } as const;
const positions = { top: "packTop", center: "packCenter", bottom: "packBottom" } as const;
export function PackSteps({ steps, files }: { steps: PackStep[]; files?: PackFiles }) {
  return <ol aria-label={t("packSteps")} className="list-inside list-decimal space-y-2">
    {steps.map((step, i) => <li key={i} className="text-ink">
      <span className="text-slate">{t(labels[step.kind])} · </span>
      {step.title && <bdi>{pick(step.title)} · </bdi>}
      {"text" in step && <bdi>{pick(step.text)}</bdi>}
      {step.kind === "file" && files?.[step.file_id] && <bdi>{files[step.file_id]!.name} · {files[step.file_id]!.added_at.slice(0, 10)} · </bdi>}
      {step.kind === "file" && <bdi>{step.ranges.map(([a, b]) => `${a}–${b}`).join(", ")}</bdi>}
      {step.kind === "stamp" && <span> · {t(positions[step.position])} · <bdi>{step.pages.join(", ")}</bdi></span>}
    </li>)}
  </ol>;
}

export function PackViewer({ projectId, view }: { projectId: string; view: PackView }) {
  const [preview, setPreview] = useState<{ pages: number; page: number; image: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const generation = useRef(0);
  useEffect(() => {
    generation.current++;
    setPreview(null); setError(null); setBusy(false);
    return () => { generation.current++; };
  }, [projectId, view.id, view.version]);
  async function build(page = 1) {
    const current = ++generation.current;
    setBusy(true); setError(null);
    const result = await deliverablesApi.buildPack(projectId, view.id, view.version, page);
    if (current !== generation.current) return;
    setBusy(false);
    if (result.ok) setPreview(result.data);
    else setError(pick(result.error));
  }
  const caption = preview ? fill(t("packPreview"), { n: preview.page, total: preview.pages }) : "";
  return <section dir={language() === "ar" ? "rtl" : "ltr"} className="h-full overflow-auto bg-paper p-3">
    <PackSteps steps={view.steps} files={view.files} />
    {!view.steps.length && <p className="text-slate">{t("packEmpty")}</p>}
    {view.steps.some(s => s.kind === "seal") && <p className="my-3 text-slate">{t("packSealHelp")}</p>}
    <button type="button" disabled={busy || !view.steps.length} onClick={() => void build()}
      className="my-3 rounded border border-ink/20 px-3 py-1 text-ink disabled:opacity-40">
      {busy ? t("packBuilding") : t("packBuild")}
    </button>
    {error && <p role="alert" className="text-copper">{error}</p>}
    {preview && <figure>
      <figcaption className="flex flex-wrap items-center gap-3 text-slate">
        <button disabled={busy || preview.page === 1} onClick={() => void build(preview.page - 1)}>{t("packPrevious")}</button>
        <span>{caption}</span>
        <button disabled={busy || preview.page === preview.pages} onClick={() => void build(preview.page + 1)}>{t("packNext")}</button>
      </figcaption>
      <img src={preview.image} alt={caption} className="mx-auto mt-3 max-w-full border border-stone" />
    </figure>}
  </section>;
}
