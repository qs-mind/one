import { ListRow } from "@/design/ListRow";
import { NowWord } from "@/design/now-waiting";
import { StageBar } from "@/design/StageBar";
import { StatusDot } from "@/design/StatusDot";
import { common } from "@/texts/common";
import { surfaces } from "@/texts/design/surfaces";
import { useText } from "@/texts/useText";
import { Demo, State } from "../parts";

const COLUMN = "flex w-full max-w-md flex-col gap-2 px-4";
const TENDER = Array.from({ length: 7 }, (_, i) => ({ state: i < 5 ? "done" : i === 5 ? "now" : "pending" }) as const);

export function ListRowDemo() {
  const t = useText();
  return (
    <Demo id="list-row" title="ListRow">
      <State name="plain" className={COLUMN}>
        <div className="flex flex-col">
          <ListRow leading={<StatusDot state="done" />} title={t(surfaces.stageReading)} trailing={t(common.done)} />
          <ListRow leading={<StatusDot state="now" />} tone="strong" title={t(surfaces.stageQueries)} trailing={<NowWord>{t(common.now)}</NowWord>} />
          <ListRow leading={<StatusDot state="pending" />} tone="muted" title={t(surfaces.stageTakeoff)} />
          <ListRow render={<button type="button" />} tone="strong" title="Lead QS" meta={t(surfaces.leadMeta)} />
          <ListRow render={<button type="button" data-force="hover" />} title={t(surfaces.contracts)} meta={`${t(surfaces.stateHover)}: ${t(surfaces.contractsMeta)}`} />
          <ListRow render={<button type="button" data-force="focus" />} tone="muted" title={t(surfaces.reviewer)} meta={t(surfaces.reviewerMeta)} />
        </div>
      </State>
      <State name={`plain · ${t(surfaces.stateCurrent)}`} className={COLUMN}>
        <nav className="flex flex-col gap-1" aria-label={t(common.settings)}>
          <ListRow render={<a href="#current" aria-current="page" />} current className="mx-0 px-4" title={t(surfaces.sectionModels)} />
          <ListRow render={<a href="#other" />} tone="muted" className="mx-0 px-4" title={t(surfaces.sectionAccount)} />
        </nav>
      </State>
      <State name="divided" className="flex w-full max-w-2xl flex-col gap-2 px-4">
        <div className="flex flex-col">
          {[surfaces.tenderOne, surfaces.tenderTwo].map((name, i) => (
            <ListRow
              key={name.en}
              frame="divided"
              size="lg"
              render={<a href={`#tender-${i}`} />}
              title={t(name)}
              meta={t(i === 0 ? surfaces.tenderOneMeta : surfaces.leadMeta)}
              trailing={
                <>
                  <StageBar className="w-40" stages={TENDER} label={t(surfaces.stageLabel, { step: 6, total: 7, name: t(surfaces.stageReview) })} />
                  <span className={i === 0 ? "min-w-24 text-end text-base font-bold text-foreground" : "min-w-24 text-end text-base"}>
                    {t.plural(common.daysLeft, i === 0 ? 5 : 12)}
                  </span>
                </>
              }
            />
          ))}
        </div>
      </State>
      <State name="boxed" className={COLUMN}>
        {/* With a radio inside, a boxed row is a <label> (specimen 4); here it is shown passive. */}
        <ListRow frame="boxed" current title={t(surfaces.recommended)} meta={t(surfaces.recommendedMeta)} />
        <ListRow frame="boxed" title={t(surfaces.ownChoice)} />
      </State>
      <State name="panel" className={COLUMN}>
        <ListRow frame="panel" tone="strong" render={<button type="button" />} title={t(surfaces.approvePlan)} meta={t(surfaces.workPaused)} />
        <ListRow frame="panel" tone="strong" render={<button type="button" data-force="hover" />} title={t(surfaces.approvePlan)} meta={`${t(surfaces.stateHover)}: ${t(surfaces.workPaused)}`} />
      </State>
    </Demo>
  );
}
