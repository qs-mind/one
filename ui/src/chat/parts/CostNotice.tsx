// A Spending Cap notice: the core's words carry the real amount spent and the cap; the subscription's cost is marked
// as equivalent cost, since it is not billed per use.
import { pick, t, useLanguage } from "../../i18n";
import type { CostData } from "./types";

export function CostNotice({ cost }: { cost: CostData }) {
  useLanguage();
  return (
    <div role="status" className={`flex flex-col gap-1 ${cost.level === "info" ? "text-slate" : "text-copper"}`}>
      <p>{pick(cost.text)}</p>
      {cost.equivalent && <p className="text-slate">{t("equivalentCost")}</p>}
    </div>
  );
}
