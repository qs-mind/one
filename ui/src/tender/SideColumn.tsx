// The tender's side column (Main.dc.html's aside, specimen 1): what waits for the engineer, the plan's stages and the
// team now, 40 apart. Beside the thread at desktop widths; under it, full width, below 900px. The waiting items are
// Stone panels with no copper (they sit under their own label); one opens its place in the thread.
import type { Schemas } from "@/api/client";
import { ListRow } from "@/design/ListRow";
import { SectionLabel } from "@/design/SectionLabel";
import { textDir } from "@/texts/language";
import { tender as texts } from "@/texts/tender";
import { useText } from "@/texts/useText";
import { Stages } from "./Stages";
import { TeamNow } from "./TeamNow";

type SideColumnProps = {
  projectId: string;
  waiting: readonly Schemas["WaitingItem"][];
  plan: Schemas["TenderPlan"] | null | undefined;
  members: readonly Schemas["TeamMember"][];
  onReveal: (item: Schemas["WaitingItem"]) => void;
};

function Waiting({ items, onReveal }: { items: SideColumnProps["waiting"]; onReveal: SideColumnProps["onReveal"] }) {
  const t = useText();
  return (
    <section aria-labelledby="tender-waiting" className="flex flex-col gap-3">
      <SectionLabel id="tender-waiting">{t(texts.waitingTitle)}</SectionLabel>
      {items.length === 0 ? (
        <p className="text-muted-foreground">{t(texts.nothingWaits)}</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {items.map((item) => {
            const meta = item.blocking ? t(texts.blocking) : (item.text ?? undefined);
            return (
              <li key={item.id} data-waiting={item.kind}>
                <ListRow
                  render={<button type="button" onClick={() => onReveal(item)} />}
                  frame="panel"
                  tone="strong"
                  title={t(item.title)}
                  meta={meta === undefined ? undefined : <span dir={textDir(meta)}>{meta}</span>}
                />
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

export function SideColumn({ projectId, waiting, plan, members, onReveal }: SideColumnProps) {
  const t = useText();
  return (
    <aside
      aria-label={t(texts.sideLabel)}
      className="flex w-full shrink-0 flex-col gap-10 border-t border-border px-(--gutter) py-7 md:w-75 md:overflow-y-auto md:border-t-0 md:border-s md:px-8 lg:w-(--side-w)"
    >
      <Waiting items={waiting} onReveal={onReveal} />
      {plan && plan.stages.length > 0 && <Stages stages={plan.stages} />}
      <TeamNow projectId={projectId} members={members} open={null} />
    </aside>
  );
}
