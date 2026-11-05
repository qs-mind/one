// A number inside a document: a reference to a ledger number (`num`) or a sheet cell or total (`cell`), shown
// with its resolved value from the view and opened like a sheet number (source, date, formula). It is not text:
// it cannot be typed over, the number changes in its sheet or in Project Records.
import type { RefValue } from "../../deliverables/types";
import { t } from "../../i18n";
import { formatDecimal } from "../sheet/format";

export function NumberRef({
  value,
  onOpen,
}: {
  value: RefValue | undefined;
  /** Opens the source; byKey is true when opened from the keyboard, so focus moves into it. */
  onOpen: (value: RefValue, el: HTMLElement, byKey: boolean) => void;
}) {
  if (!value)
    return (
      <span className="text-slate" title={t("docRefMissing")}>
        <bdi dir="ltr">—</bdi>
        <span className="sr-only">{t("docRefMissing")}</span>
      </span>
    );
  return (
    <button
      type="button"
      data-number-ref={value.number_id}
      title={t("sheetSource")}
      className="rounded-sm border-b border-copper px-0.5 hover:bg-stone focus-visible:outline focus-visible:outline-copper"
      onMouseDown={(event) => event.preventDefault()} // keep the caret where it was
      onClick={(event) => onOpen(value, event.currentTarget, event.detail === 0)}
    >
      {/* the value only, as in the sheet: the sentence around it names the unit or currency */}
      <bdi dir="ltr">{formatDecimal(value.value, value.currency ? 2 : undefined)}</bdi>
    </button>
  );
}
