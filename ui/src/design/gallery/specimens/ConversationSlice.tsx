// Specimen 2: a slice of the tender thread (Main.dc.html), from the real components only.
import { ChevronDownIcon } from "lucide-react";
import type { ReactNode } from "react";
import { HoldButton } from "@/design/HoldButton";
import { MetaLine } from "@/design/MetaLine";
import { notify } from "@/design/notify";
import { StageBar } from "@/design/StageBar";
import { StatusDot } from "@/design/StatusDot";
import { Button, buttonVariants } from "@/design/ui/button";
import { Card, CardAction, CardContent, CardFooter, CardHeader, CardTitle } from "@/design/ui/card";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/design/ui/collapsible";
import { controls } from "@/texts/design/controls";
import { specimens } from "@/texts/design/specimens";
import { surfaces } from "@/texts/design/surfaces";
import { textDir } from "@/texts/language";
import { useText } from "@/texts/useText";
import type { StageState } from "@/design/now-waiting";

const PLAN: readonly { state: StageState; weight: number }[] = [
  { state: "done", weight: 1 },
  { state: "now", weight: 1 },
  { state: "pending", weight: 2 },
  { state: "pending", weight: 2 },
  { state: "pending", weight: 3 },
  { state: "pending", weight: 1 },
  { state: "pending", weight: 1 },
];
const DAYS = 12; // the plan's length in the mockup; the weights are each stage's share of it

/** One paragraph of data text: its direction comes from its own letters. */
function Body({ children }: { children: string }) {
  return <p dir={textDir(children)}>{children}</p>;
}

function LeadMessage({ gap, children }: { gap: "gap-2" | "gap-3"; children: ReactNode }) {
  return (
    <div className={`flex flex-col ${gap}`}>
      <span className="text-xs text-muted-foreground">
        <bdi>Lead QS</bdi>
      </span>
      {children}
    </div>
  );
}

export function ConversationSlice() {
  const t = useText();
  const link = buttonVariants({ variant: "link", className: "text-xs" });
  return (
    <div className="flex w-full max-w-(--measure) flex-col gap-7">
      <LeadMessage gap="gap-2">
        <Body>{t(specimens.leadOne)}</Body>
        <Body>{t(specimens.leadTwo)}</Body>
        <div className="flex flex-wrap gap-x-5">
          <a href="#src-spec" className={link}>
            {t(specimens.sourceSpec)}
          </a>
          <a href="#src-bill" className={link}>
            {t(surfaces.sourceTitle)}
          </a>
        </div>
        <div className="mt-2 flex flex-wrap gap-3 max-sm:flex-col">
          <Button wrap className="max-sm:w-full">
            {t(controls.longDecision)}
          </Button>
          <Button wrap variant="outline" className="max-sm:w-full">
            {t(specimens.priceOnBill)}
          </Button>
        </div>
        <Collapsible>
          <CollapsibleTrigger render={<Button variant="ghost" className="justify-start gap-2 px-2" />}>
            <ChevronDownIcon aria-hidden className="size-4.5 group-data-panel-open/button:rotate-180" />
            {t(surfaces.details)}
          </CollapsibleTrigger>
          <CollapsibleContent className="pt-2">
            <Body>{t(surfaces.detailsBody)}</Body>
          </CollapsibleContent>
        </Collapsible>
      </LeadMessage>

      <p dir={textDir(t(specimens.engineerAsks))} className="max-w-[78%] self-end rounded-2xl bg-muted px-5 py-3">
        {t(specimens.engineerAsks)}
      </p>

      <LeadMessage gap="gap-3">
        <Body>{t(specimens.leadPlan)}</Body>
        <Card className="mt-1">
          <CardHeader>
            <CardTitle>{t(surfaces.planTitle)}</CardTitle>
            <CardAction>
              <MetaLine
                className="text-xs text-muted-foreground"
                items={[t(surfaces.stageCount, { n: PLAN.length }), t(surfaces.planDays, { n: DAYS })]}
              />
            </CardAction>
          </CardHeader>
          <CardContent>
            <StageBar
              stages={PLAN}
              label={t(surfaces.stageLabel, { step: 2, total: PLAN.length, name: t(surfaces.stageQueries) })}
            />
          </CardContent>
          <CardFooter>
            <HoldButton wrap onHold={() => notify(t(controls.heldDone))} hint={t(controls.approveHint)}>
              {t(controls.approve)}
            </HoldButton>
            <Button wrap variant="outline">
              {t(controls.discuss)}
            </Button>
          </CardFooter>
        </Card>
      </LeadMessage>

      <div>
        <Button
          variant="ghost"
          wrap
          className="justify-start gap-3 px-1 text-start text-xs text-muted-foreground hover:text-foreground active:text-foreground"
        >
          <StatusDot state="now" />
          <MetaLine
            items={[t(specimens.contractsReading), t(specimens.pageOf, { page: 12, total: 64 })]}
          />
        </Button>
        <span role="status" className="sr-only">
          {t(specimens.contractsReading)}
        </span>
      </div>
    </div>
  );
}
