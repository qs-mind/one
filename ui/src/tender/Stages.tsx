// The plan's stages in the side column (specimen 1): a dot and the title of each, in the plan's order. A done stage
// says so in muted words, the stage that runs now is strong with the word "now", one that waits for the engineer's
// sign-off says that; the stages still to come are muted. No stage is a button yet.
import { ListRow } from "@/design/ListRow";
import { NowWord } from "@/design/now-waiting";
import { SectionLabel } from "@/design/SectionLabel";
import { StatusDot } from "@/design/StatusDot";
import type { Schemas } from "@/api/client";
import { planShape } from "@/conversation/plan";
import { common } from "@/texts/common";
import { textDir } from "@/texts/language";
import { tender as texts } from "@/texts/tender";
import { useText } from "@/texts/useText";

type Stage = Schemas["Stage"];

export function Stages({ stages }: { stages: readonly Stage[] }) {
  const t = useText();
  const shape = planShape(stages);
  const current = shape.current;
  return (
    <section aria-labelledby="tender-stages" className="flex flex-col gap-3">
      <SectionLabel id="tender-stages">{t(texts.stagesTitle)}</SectionLabel>
      <div
        role="list"
        aria-label={current ? t(texts.stagesLabel, { step: current.step, total: shape.count, title: t(current.stage.title) }) : undefined}
        className="flex flex-col"
      >
        {stages.map((stage, index) => {
          const state = shape.bar[index]!.state;
          const title = t(stage.title);
          const trailing =
            state === "done" ? (
              <span className="text-xs text-muted-foreground">{t(common.done)}</span>
            ) : state === "now" ? (
              <NowWord>{t(common.now)}</NowWord>
            ) : state === "waiting" ? (
              <NowWord>{t(texts.stageSignOff)}</NowWord>
            ) : undefined;
          return (
            <div role="listitem" key={stage.id} data-stage={stage.id} data-state={state}>
              <ListRow
                frame="plain"
                tone={state === "now" || state === "waiting" ? "strong" : state === "pending" ? "muted" : "default"}
                leading={<StatusDot state={state} />}
                title={<bdi dir={textDir(title)}>{title}</bdi>}
                trailing={trailing}
              />
            </div>
          );
        })}
      </div>
    </section>
  );
}
