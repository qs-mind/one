// Specimen 1: the tender's side column (Main.dc.html, the aside), from the real components only.
import type { ReactNode } from "react";
import { ListRow } from "@/design/ListRow";
import { MetaLine } from "@/design/MetaLine";
import { NowWord } from "@/design/now-waiting";
import { SectionLabel } from "@/design/SectionLabel";
import { StatusDot } from "@/design/StatusDot";
import type { StageState } from "@/design/now-waiting";
import { common } from "@/texts/common";
import { specimens } from "@/texts/design/specimens";
import { surfaces } from "@/texts/design/surfaces";
import { useText } from "@/texts/useText";
import type { TextPair } from "@/texts/types";

export const STAGES: readonly TextPair[] = [
  surfaces.stageReading,
  surfaces.stageQueries,
  surfaces.stageTakeoff,
  surfaces.stageQuotes,
  surfaces.stagePricing,
  surfaces.stageReview,
  surfaces.stageHandover,
];
const NOW = 1; // the second stage, "Queries"

function Part({ label, children }: { label: TextPair; children: ReactNode }) {
  const t = useText();
  return (
    <section className="flex flex-col gap-3">
      <SectionLabel>{t(label)}</SectionLabel>
      <div className="flex flex-col">{children}</div>
    </section>
  );
}

export function TenderSide() {
  const t = useText();
  const stateOf = (index: number): StageState => (index < NOW ? "done" : index === NOW ? "now" : "pending");
  return (
    <aside
      aria-label={t(specimens.tenderStatus)}
      className="flex w-(--side-w) max-w-full flex-col gap-10 border-s border-border px-8 py-7"
    >
      <Part label={surfaces.waitingForYou}>
        <ListRow
          frame="panel"
          tone="strong"
          render={<button type="button" />}
          title={t(surfaces.approvePlan)}
          meta={t(surfaces.workPaused)}
        />
      </Part>
      <Part label={surfaces.stages}>
        {STAGES.map((stage, index) => {
          const state = stateOf(index);
          return (
            <ListRow
              key={stage.en}
              leading={<StatusDot state={state} />}
              tone={state === "now" ? "strong" : state === "pending" ? "muted" : "default"}
              title={t(stage)}
              trailing={
                state === "done" ? t(common.done) : state === "now" ? <NowWord>{t(common.now)}</NowWord> : undefined
              }
            />
          );
        })}
      </Part>
      <Part label={surfaces.teamNow}>
        <ListRow render={<button type="button" />} tone="strong" title={<bdi>Lead QS</bdi>} meta={t(surfaces.leadMeta)} />
        <ListRow
          render={<button type="button" />}
          tone="strong"
          title={t(surfaces.contracts)}
          meta={<MetaLine items={[t(surfaces.contractsMeta), t(specimens.contractsTemporary)]} />}
        />
        <ListRow
          render={<button type="button" />}
          tone="muted"
          title={t(surfaces.reviewer)}
          meta={t(surfaces.reviewerMeta)}
        />
      </Part>
    </aside>
  );
}
