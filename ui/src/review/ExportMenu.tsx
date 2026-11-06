// Exports of one Deliverable, made by the core from its view: Excel and PDF for a Sheet, Word and PDF for a
// Document, saved where the engineer chooses. Until it is signed off, every export carries «مسودة — غير معتمد».
// "Fill the client's file" opens the Fill preview when the Lead QS has made a Fill Plan.
import { useState } from "react";
import { deliverablesApi } from "../deliverables/api";
import type { View } from "../deliverables/types";
import { pick, t, texts } from "../i18n";
import { saveAnswer } from "./save";

export type ExportMenuProps = {
  projectId: string;
  view: View;
  /** The Fill Plan for the client's own file, when the Lead QS has made one. */
  fillPlanId?: string | null;
  /** The client's file that plan fills, shown beside the button. */
  fillFileName?: string | null;
  onFill?: (planId: string) => void;
  announce?: (line: string) => void;
};

export function ExportMenu({ projectId, view, fillPlanId, fillFileName, onFill, announce }: ExportMenuProps) {
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);
  // how the last export went, shown quietly under the buttons (the announcer says it too)
  const [done, setDone] = useState<string | null>(null);
  const draft = view.status !== "signed_off";
  const formats: ["xlsx" | "docx" | "pdf", string][] =
    view.kind === "pack" ? [["pdf", t("exportPdf")]] : view.kind === "sheet"
      ? [
          ["xlsx", t("exportExcel")],
          ["pdf", t("exportPdf")],
        ]
      : [
          ["docx", t("exportWord")],
          ["pdf", t("exportPdf")],
        ];
  const markId = `export-draft-${view.id}`;

  async function make(format: "xlsx" | "docx" | "pdf") {
    setBusy(true);
    setFailed(null);
    setDone(null);
    const out = await saveAnswer(await deliverablesApi.exportFile(projectId, view.id, format));
    setBusy(false);
    if (out.ok) {
      setDone(out.line);
      announce?.(out.line);
    } else setFailed(out.line);
  }

  return (
    <div role="group" aria-label={t("exportMenu")} className="flex flex-wrap items-center gap-2">
      <span className="text-slate">{t("exportMenu")}</span>
      {formats.map(([format, label]) => (
        <button
          key={format}
          type="button"
          disabled={busy || (view.kind === "pack" && draft)}
          aria-describedby={draft ? markId : undefined}
          className="rounded-lg border border-ink/20 px-3 py-1 hover:bg-stone disabled:opacity-40"
          onClick={() => void make(format)}
        >
          {label}
        </button>
      ))}
      {view.kind === "sheet" && fillPlanId && (
        <button
          type="button"
          className="rounded-lg border border-ink/20 px-3 py-1 hover:bg-stone"
          onClick={() => onFill?.(fillPlanId)}
        >
          {t("exportClientFile")}
        </button>
      )}
      {view.kind === "sheet" && fillPlanId && fillFileName && (
        <bdi dir="auto" className="text-slate">
          {fillFileName}
        </bdi>
      )}
      {draft && (
        <span id={markId} className="text-copper">
          {/* the mark is printed in the Deliverable's own language, as the files carry it */}
          <bdi dir="auto">{pick(view.kind === "pack" ? texts.packNeedsSignoff : texts.exportDraftMark, view.language)}</bdi>
        </span>
      )}
      {done && (
        <p data-export-done className="basis-full text-slate">
          <bdi dir="auto">{done}</bdi>
        </p>
      )}
      {failed && (
        <p role="alert" className="basis-full text-copper">
          {failed}
        </p>
      )}
    </div>
  );
}
