// Specimen 4: Home's tender rows, first launch's fields and strip, and settings' option rows, from the real components.
import { useState } from "react";
import { Field } from "@/design/Field";
import { ListRow } from "@/design/ListRow";
import { cn } from "@/design/lib/utils";
import { MetaLine } from "@/design/MetaLine";
import type { StageState } from "@/design/now-waiting";
import { StageBar } from "@/design/StageBar";
import { Checkbox } from "@/design/ui/checkbox";
import { Input } from "@/design/ui/input";
import { Progress, ProgressLabel, ProgressValue } from "@/design/ui/progress";
import { RadioGroup, RadioGroupItem } from "@/design/ui/radio-group";
import { common } from "@/texts/common";
import { controls } from "@/texts/design/controls";
import { specimens } from "@/texts/design/specimens";
import { surfaces } from "@/texts/design/surfaces";
import { useText } from "@/texts/useText";
import type { TextPair } from "@/texts/types";
import { OrgSelect } from "../controls/SelectDemo";

const TOTAL_STAGES = 7;
const TENDERS: readonly { name: TextPair; stage: TextPair; status: TextPair; now: number; days: number }[] = [
  { name: specimens.hospital, stage: surfaces.stageReview, status: specimens.reviewerWorking, now: 5, days: 5 },
  { name: surfaces.tenderOne, stage: surfaces.stageQueries, status: surfaces.leadMeta, now: 1, days: 12 },
];
const NEAREST = Math.min(...TENDERS.map((tender) => tender.days));
const stagesUpTo = (now: number) =>
  Array.from({ length: TOTAL_STAGES }, (_, i): { state: StageState } => ({
    state: i < now ? "done" : i === now ? "now" : "pending",
  }));

function TenderRows() {
  const t = useText();
  return (
    <section aria-label={t(specimens.tenders)} className="flex flex-col">
      {TENDERS.map((tender) => (
        <ListRow
          key={tender.days}
          frame="divided"
          size="lg"
          render={<a href="#/specimens" />}
          title={t(tender.name)}
          meta={<MetaLine items={[t(tender.stage), t(tender.status)]} />}
          trailing={
            <>
              <StageBar
                className="w-40"
                stages={stagesUpTo(tender.now)}
                label={t(surfaces.stageLabel, { step: tender.now + 1, total: TOTAL_STAGES, name: t(tender.stage) })}
              />
              <span
                className={cn(
                  "min-w-24 text-end text-base",
                  tender.days === NEAREST ? "font-bold text-foreground" : "text-muted-foreground",
                )}
              >
                {t.plural(common.daysLeft, tender.days)}
              </span>
            </>
          }
        />
      ))}
    </section>
  );
}

function FirstLaunch() {
  const t = useText();
  const downloaded = t(surfaces.downloaded, { done: 62, total: 135 });
  return (
    <section aria-label={t(specimens.aboutYou)} className="flex flex-col gap-10">
      <div className="grid grid-cols-2 gap-5 max-sm:grid-cols-1">
        <Field label={t(controls.firstName)}>
          <Input />
        </Field>
        <Field label={t(controls.role)}>
          <Input placeholder={t(controls.roleExample)} />
        </Field>
        <Field label={t(controls.orgType)}>
          <OrgSelect />
        </Field>
      </div>
      <Progress value={46} aria-label={t(specimens.setupLabel)} aria-valuetext={downloaded}>
        <ProgressLabel>{t(surfaces.progressLabel)}</ProgressLabel>
        <ProgressValue>{() => downloaded}</ProgressValue>
      </Progress>
    </section>
  );
}

function SettingsRows() {
  const t = useText();
  const [model, setModel] = useState("recommended");
  return (
    <section className="flex flex-col gap-6">
      <div className="flex flex-col gap-3">
        <h3 id="specimen-models" className="text-lg font-bold">
          {t(controls.models)}
        </h3>
        <RadioGroup
          aria-labelledby="specimen-models"
          value={model}
          onValueChange={(next) => setModel(String(next))}
          className="gap-3"
        >
          <ListRow
            frame="boxed"
            render={<label />}
            current={model === "recommended"}
            leading={<RadioGroupItem value="recommended" />}
            title={t(controls.recommended)}
            meta={t(surfaces.recommendedMeta)}
          />
          <ListRow
            frame="boxed"
            render={<label />}
            current={model === "own"}
            leading={<RadioGroupItem value="own" />}
            title={t(controls.ownChoice)}
          />
        </RadioGroup>
      </div>
      <div className="flex flex-col gap-3">
        <h3 className="text-lg font-bold">{t(controls.onDevice)}</h3>
        <ListRow
          frame="boxed"
          render={<label />}
          leading={<Checkbox />}
          title={t(specimens.confidentialOnDevice)}
          meta={t(specimens.confidentialMeta)}
        />
      </div>
    </section>
  );
}

export function MixedSlice() {
  return (
    <div className="flex w-full max-w-230 flex-col gap-10">
      <TenderRows />
      <FirstLaunch />
      <SettingsRows />
    </div>
  );
}
