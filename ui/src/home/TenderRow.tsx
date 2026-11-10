// One tender on Home: its name, the stage it is in and what is happening, its stages as a bar, and the days left to
// its submission date. The row opens the tender. The nearest deadline is drawn in bold (the system's rule for copper
// on a near date: decision 0.1.3).
import { Link } from "react-router";
import type { Schemas } from "@/api/client";
import { MetaLine } from "@/design/MetaLine";
import type { StageState } from "@/design/now-waiting";
import { ListRow } from "@/design/ListRow";
import { Pill } from "@/design/Pill";
import { StageBar } from "@/design/StageBar";
import { cn } from "@/design/lib/utils";
import { paths } from "@/app/paths";
import { common } from "@/texts/common";
import { home } from "@/texts/home";
import { textDir } from "@/texts/language";
import { useText } from "@/texts/useText";
import { DateSource } from "@/tender/DateSource";
import { daysUntil } from "./days";

type Row = Schemas["TenderRow"];

const STAGE: Record<Row["stages"][number], StageState> = {
  approved: "done",
  now: "now",
  waiting_engineer: "waiting",
  pending: "pending",
};

function Days({ row, today, near }: { row: Row; today: Date; near: boolean }) {
  const t = useText();
  const days = row.submission_date ? daysUntil(row.submission_date, today) : null;
  const words =
    row.state === "finished"
      ? t(home.finished)
      : days === null
        ? t(home.noDate)
        : days < 0
          ? t(home.datePassed)
          : days === 0
            ? t(home.dueToday)
            : t.plural(common.daysLeft, days);
  // The date's source under the days (S39), as words: the whole row is the link that opens the tender.
  const source = row.state !== "finished" && row.submission_date ? row.submission_source : null;
  return (
    <span className="flex min-w-0 max-w-44 flex-col items-end text-end md:w-44">
      <span className={cn(near && "font-bold text-foreground")}>{words}</span>
      {source && <DateSource compact source={source} />}
    </span>
  );
}

type TenderRowProps = { row: Row; today: Date; near: boolean; samplePill: boolean };

export function TenderRow({ row, today, near, samplePill }: TenderRowProps) {
  const t = useText();
  const name = row.name_pair ? t(row.name_pair) : row.name;
  const now = row.stages.findIndex((stage) => stage === "now" || stage === "waiting_engineer");
  const approved = row.stages.filter((stage) => stage === "approved").length;
  const total = row.stages.length;
  const label =
    row.stage && now >= 0
      ? t(home.stageOf, { n: now + 1, total, stage: t(row.stage) })
      : t(home.stagesApproved, { n: approved, total });
  return (
    <ListRow
      frame="divided"
      size="lg"
      render={<Link to={paths.tender(row.project_id)} />}
      title={<bdi dir={textDir(name)}>{name}</bdi>}
      meta={
        <MetaLine
          items={[
            row.stage && t(row.stage),
            row.line && t(row.line),
            row.confidential && t(home.confidential),
          ]}
        />
      }
      trailing={
        <>
          {samplePill && row.sample && <Pill>{t(common.sample)}</Pill>}
          {total > 0 && <StageBar className="w-28 md:w-40" label={label} stages={row.stages.map((stage) => ({ state: STAGE[stage] }))} />}
          <Days row={row} today={today} near={near} />
        </>
      }
    />
  );
}
