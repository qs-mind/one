// A number in a view: its value exactly as the ledger holds it, with its unit or currency, and a chip with its source
// that opens the source popover. The screen never computes it.
import type { NumberCell } from "../../../deliverables/types";
import { fill, t } from "../../../i18n";
import { FileName } from "../../../ui/FileName";
import { formatDecimal } from "../../../viewers/sheet/format";
import { useViewEnv } from "./env";

/** "39,850.50 EGP/m3": an amount is its currency; unit and currency both set is currency per unit. */
export function numberText(cell: NumberCell): string {
  const per = cell.currency && cell.unit ? `${cell.currency}/${cell.unit}` : (cell.currency ?? cell.unit);
  return per ? `${formatDecimal(cell.value)} ${per}` : formatDecimal(cell.value);
}

export function Num({ cell }: { cell: NumberCell }) {
  const { sources, openSource } = useViewEnv();
  const source = cell.source ? sources[cell.source] : undefined;
  const shown = numberText(cell);
  const chip = "inline-flex max-w-48 items-center rounded-full border border-slate px-2 text-xs leading-5 text-slate";
  return (
    <span className="inline-flex flex-wrap items-center gap-x-2 gap-y-1">
      <bdi dir="ltr" className="font-semibold tabular-nums">
        {shown}
      </bdi>
      {openSource ? (
        <button
          type="button"
          aria-label={fill(t("viewSourceOf"), { value: shown })}
          className={`${chip} hover:border-copper hover:text-copper focus-visible:outline-2 focus-visible:outline-ink`}
          // a click from the keyboard (detail 0) moves the focus into the popover
          onClick={(event) => openSource(cell, event.currentTarget, event.detail === 0)}
        >
          {source ? <FileName name={source.title} /> : t("noSource")}
        </button>
      ) : (
        <span className={chip}>{source ? <FileName name={source.title} /> : t("noSource")}</span>
      )}
    </span>
  );
}
