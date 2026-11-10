// The plan card, placed by a data-plan part and drawn from the plan the screen holds (the part is a pointer, 3.1):
// the stages bar, the days, the expected cost and AI time, then Approve and Discuss while it is proposed. Approval
// starts paid work, so it is a hold. An approved plan shows when; a Suggested change shows before and after, its
// reason and its two answers. A part that names an older version is one line.
import { HoldButton } from "@/design/HoldButton";
import { MetaLine } from "@/design/MetaLine";
import { StageBar } from "@/design/StageBar";
import { Button } from "@/design/ui/button";
import { Card, CardAction, CardContent, CardFooter, CardHeader, CardTitle } from "@/design/ui/card";
import { conversation } from "@/texts/conversation";
import { formatDate } from "@/texts/format";
import { textDir } from "@/texts/language";
import { type Translate, useText } from "@/texts/useText";
import { DateSource } from "@/tender/DateSource";
import type { Source, TenderPlan } from "./parts";
import { planShape } from "./plan";

type PlanCardProps = {
  /** The plan as the screen holds it (GET /plan and `plan` events); null while it loads. */
  plan: TenderPlan | null;
  /** The version the data-plan part names. */
  version: number;
  onApprove: (version: number) => void;
  onDiscuss: () => void;
  onChange: (changeId: string, accept: boolean) => void;
  /** Opens a submission date's source at its place (S39). */
  onOpenSource?: (source: Source) => void;
  /** The Lead is still working in this conversation: the core refuses approving a plan until it ends. */
  busy?: boolean;
};

const day = (value: string, t: Translate) => formatDate(new Date(`${value}T00:00:00Z`), t.lang, { day: "numeric", month: "long", timeZone: "UTC" });

/** "7 stages · 12 days · Expected cost 2.40 USD · about 54 minutes of AI work" for a plan or its change. */
function facts(plan: Pick<TenderPlan, "stages" | "expected_cost_usd" | "expected_minutes">, t: Translate) {
  const shape = planShape(plan.stages);
  return [
    t.plural(conversation.stageCount, shape.count),
    t.plural(conversation.dayCount, shape.days),
    plan.expected_cost_usd === null ? t(conversation.costUnknown) : t(conversation.cost, { cost: `${plan.expected_cost_usd} USD` }),
    t.plural(conversation.minutes, plan.expected_minutes),
  ];
}

function barLabel(plan: TenderPlan, t: Translate): string {
  const shape = planShape(plan.stages);
  if (shape.allDone) return t(conversation.stageBarDone);
  if (!shape.current) return t(conversation.stageBarNone);
  const { step, stage } = shape.current;
  return t(conversation.stageBar, { step, total: shape.count, name: stage.title[t.lang] });
}

/** Where a submission date was read, under it; nothing when the core gives no source. */
function Dated({ source, onOpen }: { source: Source | null; onOpen?: (source: Source) => void }) {
  if (!source) return null;
  return (
    <span className="flex flex-wrap items-baseline gap-x-3" data-date-source>
      <DateSource source={source} onOpen={onOpen} />
    </span>
  );
}

export function PlanCard({ plan, version, onApprove, onDiscuss, onChange, onOpenSource, busy = false }: PlanCardProps) {
  const t = useText();
  if (!plan) return null;
  if (version < plan.version)
    return <p className="text-xs text-muted-foreground">{t(conversation.replaced, { n: plan.version })}</p>;

  const shape = planShape(plan.stages);
  const { change } = plan;
  return (
    <Card data-plan={plan.id} className="mt-1">
      <CardHeader>
        <CardTitle className="font-bold">{t(conversation.planTitle)}</CardTitle>
        <CardAction>
          <MetaLine
            className="text-xs text-muted-foreground"
            items={[t.plural(conversation.stageCount, shape.count), t.plural(conversation.dayCount, shape.days)]}
          />
        </CardAction>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <StageBar stages={shape.bar} label={barLabel(plan, t)} />
        <MetaLine
          className="text-xs text-muted-foreground"
          items={[...facts(plan, t).slice(2), t(conversation.submission, { date: day(plan.submission_date, t) })]}
        />
        <Dated source={plan.submission_source} onOpen={onOpenSource} />
        <p className="text-xs text-muted-foreground">{t(plan.cost_basis)}</p>
        {plan.status === "approved" && plan.approved_at && (
          <p className="text-xs">{t(conversation.approvedOn, { date: formatDate(new Date(plan.approved_at), t.lang) })}</p>
        )}
        {change && (
          <div className="flex flex-col gap-2 border-t border-border pt-3" data-change={change.id}>
            <p className="font-bold">{t(conversation.changeTitle)}</p>
            <p dir={textDir(change.reason)}>{change.reason}</p>
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-xs">
              <dt className="text-muted-foreground">{t(conversation.changeNow)}</dt>
              <dd>
                <MetaLine items={[...facts(plan, t), day(plan.submission_date, t)]} />
                <Dated source={plan.submission_source} onOpen={onOpenSource} />
              </dd>
              <dt className="text-muted-foreground">{t(conversation.changeAfter)}</dt>
              <dd>
                <MetaLine items={[...facts(change, t), day(change.submission_date, t)]} />
                <Dated source={change.submission_source} onOpen={onOpenSource} />
              </dd>
            </dl>
          </div>
        )}
      </CardContent>
      {(plan.status === "proposed" || change) && (
        <CardFooter className="flex-wrap gap-3 max-sm:flex-col max-sm:items-stretch">
          {busy && !change && <p className="w-full text-xs text-muted-foreground">{t(conversation.planBusy)}</p>}
          {change ? (
            <>
              {change.paid ? (
                <HoldButton wrap hint={t(conversation.acceptChangeHint)} onHold={() => onChange(change.id, true)}>
                  {t(conversation.acceptChange)}
                </HoldButton>
              ) : (
                <Button wrap onClick={() => onChange(change.id, true)}>
                  {t(conversation.acceptChange)}
                </Button>
              )}
              <Button wrap variant="outline" onClick={() => onChange(change.id, false)}>
                {t(conversation.rejectChange)}
              </Button>
            </>
          ) : (
            <>
              {plan.paid ? (
                <HoldButton wrap disabled={busy} hint={t(conversation.approveHint)} onHold={() => onApprove(plan.version)}>
                  {t(conversation.approve)}
                </HoldButton>
              ) : (
                <Button wrap disabled={busy} onClick={() => onApprove(plan.version)}>
                  {t(conversation.approve)}
                </Button>
              )}
              <Button wrap variant="outline" onClick={onDiscuss}>
                {t(conversation.discuss)}
              </Button>
            </>
          )}
        </CardFooter>
      )}
    </Card>
  );
}
