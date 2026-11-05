// Before the client's own BOQ file is filled: every cell it would write (the client's text, before, after), the
// cells left alone (the client's formulas, merged cells), and each item code that differs from ours, which the
// engineer marks right or leaves blocking. Then "Make the file" saves the filled copy; the client's file is kept.
import { useEffect, useState } from "react";
import { deliverablesApi } from "../deliverables/api";
import type { FillPreview as Preview } from "../deliverables/types";
import { count, fill, language, pick, t, type Text } from "../i18n";
import { formatDecimal } from "../viewers/sheet/format";
import { saveAnswer } from "./save";

export type FillPreviewProps = {
  projectId: string;
  planId: string;
  announce?: (line: string) => void;
  onClose?: () => void;
};

const looksNumber = (text: string | null) => text !== null && /^-?\d+(\.\d+)?$/.test(text);
const shown = (text: string | null) =>
  text === null ? "—" : <bdi dir={looksNumber(text) ? "ltr" : "auto"}>{looksNumber(text) ? formatDecimal(text) : text}</bdi>;

export function FillPreview({ projectId, planId, announce, onClose }: FillPreviewProps) {
  const [preview, setPreview] = useState<Preview | null>(null);
  const [failed, setFailed] = useState<Text | string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let live = true;
    void deliverablesApi.fillPreview(projectId, planId).then((answer) => {
      if (!live) return;
      if (answer.ok) setPreview(answer.data);
      else setFailed(answer.error); // FILL_NEEDS_SIGNOFF until a Revision is signed off
    });
    return () => {
      live = false;
    };
  }, [projectId, planId]);

  async function itIsRight(row: number) {
    setFailed(null);
    const answer = await deliverablesApi.acceptMismatches(projectId, planId, [row]);
    if (answer.ok) setPreview(answer.data);
    else setFailed(answer.error);
  }

  async function make() {
    setBusy(true);
    setFailed(null);
    const out = await saveAnswer(await deliverablesApi.fillFile(projectId, planId));
    setBusy(false);
    if (out.ok) announce?.(out.line);
    else setFailed(out.line);
  }

  const open = preview?.mismatches.filter((m) => !m.accepted) ?? [];
  return (
    <section aria-label={t("fillPreview")} className="flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <h3 className="font-semibold">{t("fillPreview")}</h3>
        {preview && <span className="text-slate">{fill(t("reviewRev"), { n: preview.revision })}</span>}
        {onClose && (
          <button type="button" className="ms-auto rounded px-2 hover:bg-stone" onClick={onClose}>
            {t("close")}
          </button>
        )}
      </div>
      {!preview && !failed && <p className="text-slate">{t("deliverableLoading")}</p>}
      {preview && (
        <>
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="text-start text-slate">
                <th className="border-b border-stone px-1 text-start font-normal">{t("fillCell")}</th>
                <th className="border-b border-stone px-1 text-start font-normal">{t("fillClientText")}</th>
                <th className="border-b border-stone px-1 text-start font-normal">{t("fillBefore")}</th>
                <th className="border-b border-stone px-1 text-start font-normal">{t("fillAfter")}</th>
              </tr>
            </thead>
            <tbody>
              {preview.writes.map((w) => (
                <tr key={w.cell}>
                  <td className="border-b border-stone px-1">
                    <bdi dir="ltr">{w.cell}</bdi>
                  </td>
                  <td className="border-b border-stone px-1">{shown(w.client_text)}</td>
                  <td className="border-b border-stone px-1 text-slate">{shown(w.before)}</td>
                  <td className="border-b border-stone px-1 font-semibold">{shown(w.after)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {preview.skipped.length > 0 && (
            <div>
              <h4 className="font-semibold">{t("fillSkipped")}</h4>
              <ul className="list-disc ps-6">
                {preview.skipped.map((s) => (
                  <li key={s.cell}>
                    <bdi dir="ltr">{s.cell}</bdi>: {s.reason === "formula" ? t("fillSkippedFormula") : t("fillSkippedMerged")}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {preview.mismatches.length > 0 && (
            <div>
              <h4 className="font-semibold">{t("fillMismatches")}</h4>
              <ul className="flex flex-col gap-1">
                {preview.mismatches.map((m) => (
                  <li key={m.row} className="flex flex-wrap items-center gap-2">
                    <span dir="auto">{pick(m.text)}</span>
                    {m.accepted ? (
                      <span className="text-slate">{t("fillMarkedRight")}</span>
                    ) : (
                      <button type="button" className="rounded border border-slate px-2 py-0.5 hover:bg-stone" onClick={() => void itIsRight(m.row)}>
                        {t("fillItIsRight")}
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {preview.unmapped_rows.length > 0 && (
            <p className="text-slate">{count("fillUnmappedRows", preview.unmapped_rows.length)}</p>
          )}
          {preview.unmapped_items.length > 0 && (
            <p className="text-slate">
              <bdi dir="auto">
                {fill(t("fillUnmappedItems"), {
                  codes: preview.unmapped_items.map((i) => i.code ?? "—").join(language() === "ar" ? "، " : ", "),
                })}
              </bdi>
            </p>
          )}
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              disabled={busy || open.length > 0}
              aria-describedby={open.length > 0 ? `fill-first-${planId}` : undefined}
              className="rounded bg-ink px-3 py-1 text-paper disabled:opacity-40"
              onClick={() => void make()}
            >
              {t("fillMake")}
            </button>
            {open.length > 0 && (
              <span id={`fill-first-${planId}`} className="text-slate">
                {t("fillMismatchesFirst")}
              </span>
            )}
          </div>
        </>
      )}
      {failed && (
        <p role="alert" className="text-copper">
          {typeof failed === "string" ? failed : pick(failed)}
        </p>
      )}
    </section>
  );
}
