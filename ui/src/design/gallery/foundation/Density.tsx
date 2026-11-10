import { ListRow } from "@/design/ListRow";
import { Num } from "@/design/Num";
import { foundation } from "@/texts/design/foundation";
import { useLang } from "@/texts/language";
import { useText } from "@/texts/useText";
import type { TextPair } from "@/texts/types";
import { Demo, State } from "../parts";

const ROWS: readonly { code: string; name: TextPair; quantity: number }[] = [
  { code: "7/01", name: foundation.rowPlain, quantity: 120 },
  { code: "7/02", name: foundation.rowFootings, quantity: 340.5 },
  { code: "7/03", name: foundation.rowBeams, quantity: 86 },
];
const TOTAL = ROWS.reduce((sum, row) => sum + row.quantity, 0);

const CELL = "h-(--sheet-row-h) px-(--sheet-cell-px)";
const NUMBER = `num text-end ${CELL}`;

export function Density() {
  const t = useText();
  const { dir } = useLang();
  return (
    <Demo id="density" title="Density">
      <State name={t(foundation.dense)} className="flex min-w-0 flex-[1_1_24rem] flex-col gap-2">
        <div className="overflow-x-auto rounded-2xl border border-line bg-card">
          <table className="dense w-full border-collapse text-base">
            <caption className="sr-only">{t(foundation.sheetLabel)}</caption>
            <thead className="text-xs text-muted-foreground">
              <tr className="border-b border-border">
                <th scope="col" className={`${CELL} text-start font-normal`}>
                  {t(foundation.colItem)}
                </th>
                <th scope="col" className={`${CELL} text-start font-normal`}>
                  {t(foundation.colDescription)}
                </th>
                <th scope="col" className={`${NUMBER} font-normal`}>
                  <bdi dir={dir}>{t(foundation.colQuantity)}</bdi>
                </th>
              </tr>
            </thead>
            <tbody>
              {ROWS.map((row) => (
                <tr key={row.code} className="border-b border-row-line">
                  <td className={CELL}>
                    <Num>{row.code}</Num>
                  </td>
                  <td className={CELL}>{t(row.name)}</td>
                  <td className={NUMBER}>
                    <Num value={row.quantity} />
                  </td>
                </tr>
              ))}
              <tr className="font-bold">
                <td className={CELL} colSpan={2}>
                  {t(foundation.total)}
                </td>
                <td className={NUMBER}>
                  <Num value={TOTAL} />
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </State>
      <State name={t(foundation.roomy)} className="flex min-w-0 flex-[1_1_24rem] flex-col gap-2 px-3">
        <div className="flex flex-col">
          {ROWS.map((row) => (
            <ListRow
              key={row.code}
              leading={<Num className="text-xs text-muted-foreground">{row.code}</Num>}
              title={t(row.name)}
              trailing={
                <span className="text-base text-foreground">
                  <Num value={row.quantity} /> <Num>{t(foundation.cubicMetre)}</Num>
                </span>
              }
            />
          ))}
        </div>
      </State>
    </Demo>
  );
}
