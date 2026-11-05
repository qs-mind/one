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
  const chip = "inline-flex min-w-0 max-w-48 items-center rounded-full border border-slate px-2 text-xs leading-5 text-slate";
  // one line: a long source name is cut, its full name on hover; a calculation says so, not its formula's keys
  const name = !source ? t("noSource") : source.kind === "calculation" ? t("calculated") : <FileName name={source.title} fit />;
  return (
    <span className="inline-flex flex-wrap items-center gap-x-2 gap-y-1">
      {/* one isolated run taking its direction from its unit: «1,200 م3» reads number first in Arabic, and
          "39,850.50 EGP/m3" left to right */}
      <bdi dir="auto" className="font-semibold tabular-nums">
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
          {name}
        </button>
      ) : (
        <span className={chip}>{name}</span>
      )}
    </span>
  );
}
