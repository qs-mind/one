// Where a number comes from, opened by clicking it: its source, file and place, date and who entered it; for a
// calculated number the formula, each input with its own source, and the steps, from Plan 3's explain. An input
// that was itself calculated opens the same way. It sits inside the viewer's own box (absolutely placed, never
// a portal), so it scales with a canvas frame.
import { useEffect, useRef, useState, type CSSProperties } from "react";
import { deliverablesApi } from "../../deliverables/api";
import type { Explained, NumberCell, Source } from "../../deliverables/types";
import { fill, language, pick, t, texts, type Text } from "../../i18n";
import { formatDecimal } from "./format";

const roles: Record<string, Text> = {
  engineer: texts.sheetTheEngineer,
  lead_qs: texts.roleLead,
  checking_qs: texts.roleChecker,
  calc_engine: texts.reviewCalcEngine,
};

function where(locator: Record<string, string | number> | undefined): string | undefined {
  const { page, sheet, row, line } = locator ?? {};
  if (page !== undefined) return fill(t("page"), { page });
  if (sheet !== undefined && row !== undefined) return fill(t("sheetRow"), { sheet, row });
  if (row !== undefined) return fill(t("row"), { row });
  if (line !== undefined) return fill(t("line"), { line });
  return undefined;
}

const shown = (value: string, unit?: string | null) => (
  <bdi dir="ltr">
    {formatDecimal(value)}
    {unit ? ` ${unit}` : ""}
  </bdi>
);

export function SourcePopover({
  projectId,
  cell,
  sources,
  style,
  focus,
  onClose,
}: {
  projectId: string;
  cell: NumberCell;
  sources: Record<string, Source>;
  style: CSSProperties;
  /** Opened from the keyboard: focus moves in. A click leaves it on the sheet, so the arrows keep moving. */
  focus: boolean;
  onClose: () => void;
}) {
  const box = useRef<HTMLDivElement>(null);
  const [stack, setStack] = useState<string[]>([cell.number_id]); // the number shown, and the ones it was opened from
  const [page, setPage] = useState(1);
  const [explained, setExplained] = useState<Explained>();
  const [failed, setFailed] = useState<Text>();
  const numberId = stack[stack.length - 1]!;

  useEffect(() => {
    if (focus) box.current?.focus();
  }, [focus]);
  useEffect(() => {
    let live = true;
    setExplained(undefined);
    setFailed(undefined);
    void deliverablesApi.explain(projectId, numberId, page).then((answer) => {
      if (!live) return;
      if (answer.ok) setExplained(answer.data);
      else setFailed(answer.error);
    });
    return () => {
      live = false;
    };
  }, [projectId, numberId, page]);

  const first = stack.length === 1;
  const viewSource = first ? sources[cell.source] : undefined; // the view knows the file's name
  const source = viewSource ?? explained?.source;
  const dated = (first ? cell.dated : null) ?? explained?.number.dated ?? source?.dated;
  const by = explained?.number.recorded_by;
  const calc = explained?.calculation;
  const place = [viewSource?.file_name, where(source?.locator)].filter(Boolean).join(language() === "ar" ? "، " : ", ");

  function open(id: string) {
    setPage(1);
    setStack((s) => [...s, id]);
  }

  return (
    <div
      ref={box}
      role="dialog"
      aria-label={t("sheetSource")}
      tabIndex={-1}
      style={style}
      className="absolute z-20 flex max-h-96 w-80 max-w-[90%] flex-col gap-2 overflow-auto rounded-md border border-slate bg-paper p-3 text-start text-ink outline-none"
      onKeyDown={(event) => {
        if (event.key === "Escape") {
          event.stopPropagation();
          onClose();
        }
      }}
      onMouseDown={(event) => event.stopPropagation()}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="font-semibold">
          {explained ? shown(explained.number.value, explained.number.currency ?? explained.number.unit) : shown(cell.value, cell.currency ?? cell.unit)}
        </span>
        <span className="flex gap-1">
          {!first && (
            <button type="button" className="rounded px-2 hover:bg-stone" onClick={() => (setPage(1), setStack((s) => s.slice(0, -1)))}>
              {t("sheetBack")}
            </button>
          )}
          <button type="button" className="rounded px-2 hover:bg-stone" onClick={onClose}>
            {t("close")}
          </button>
        </span>
      </div>
      <section aria-label={t("sheetSource")} className="flex flex-col">
        <span className="text-xs text-slate">{t("sheetSource")}</span>
        {source ? (
          <span dir="auto">{source.title}</span>
        ) : (
          !failed && <span className="text-slate">{t("noSource")}</span>
        )}
        {place && <span dir="auto" className="text-slate">{place}</span>}
        {dated && <span>{fill(t("sheetDated"), { date: dated })}</span>}
        {by && <span>{fill(t("sheetEnteredBy"), { who: roles[by] ? pick(roles[by]) : by })}</span>}
      </section>
      {failed && <p role="alert" className="text-copper">{pick(failed)}</p>}
      {calc && (
        <>
          <section className="flex flex-col">
            <span className="text-xs text-slate">{t("sheetFormula")}</span>
            <bdi dir="ltr" className="font-mono">
              {calc.formula}
            </bdi>
          </section>
          {calc.inputs.length > 0 && (
            <section className="flex flex-col">
              <span className="text-xs text-slate">{t("sheetInputs")}</span>
              <ul className="flex flex-col gap-1">
                {calc.inputs.map((input) => (
                  <li key={`${input.name}-${input.seq ?? ""}-${input.number}`} className="flex flex-col">
                    {input.calculated ? (
                      <button type="button" className="self-start underline hover:text-copper" onClick={() => open(input.number)}>
                        <bdi dir="ltr">{input.name}</bdi> = {shown(input.value, input.unit)}
                      </button>
                    ) : (
                      <span>
                        <bdi dir="ltr">{input.name}</bdi> = {shown(input.value, input.unit)}
                      </span>
                    )}
                    <span dir="auto" className="text-slate">
                      {input.source.title}
                      {input.dated ? ` · ${fill(t("sheetDated"), { date: input.dated })}` : ""}
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          )}
          {calc.steps.length > 0 && (
            <section className="flex flex-col">
              <span className="text-xs text-slate">{t("sheetSteps")}</span>
              <ol className="flex flex-col">
                {calc.steps.map((step) => (
                  <li key={step.n}>
                    <bdi dir="ltr">
                      {step.n}. {step.text} = {formatDecimal(step.value)}
                      {step.unit ? ` ${step.unit}` : ""}
                    </bdi>
                  </li>
                ))}
              </ol>
            </section>
          )}
          {calc.pages > 1 && (
            <div className="flex items-center justify-between gap-2">
              <button type="button" disabled={page <= 1} className="rounded px-2 hover:bg-stone disabled:text-slate" onClick={() => setPage(page - 1)}>
                {t("sheetPreviousPage")}
              </button>
              <span>{fill(t("sheetPageOf"), { page: calc.page, pages: calc.pages })}</span>
              <button type="button" disabled={page >= calc.pages} className="rounded px-2 hover:bg-stone disabled:text-slate" onClick={() => setPage(page + 1)}>
                {t("sheetNextPage")}
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
