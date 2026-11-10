import { NowWord, WaitingLabel } from "@/design/now-waiting";
import { StageBar } from "@/design/StageBar";
import { StatusDot } from "@/design/StatusDot";
import { common } from "@/texts/common";
import { surfaces } from "@/texts/design/surfaces";
import { useText } from "@/texts/useText";
import { Code, Demo, State } from "../parts";

export function NowWaiting() {
  const t = useText();
  return (
    <Demo id="now-waiting" title="now / waiting">
      <State name={<Code>NowWord</Code>}>
        <span className="flex items-center gap-3">
          <StatusDot state="now" />
          <span className="font-bold">{t(surfaces.stageQueries)}</span>
          <NowWord>{t(common.now)}</NowWord>
        </span>
      </State>
      <State name={<Code>WaitingLabel</Code>} className="flex max-w-md flex-col gap-2">
        <div className="flex flex-col gap-2 rounded-2xl bg-muted px-5 py-4">
          <WaitingLabel>{t(surfaces.waitingLine)}</WaitingLabel>
          <span>{t(surfaces.approvePlan)}</span>
        </div>
      </State>
      <State name={<Code>StageBar</Code>} className="flex w-60 flex-col gap-2">
        <StageBar
          label={t(surfaces.stageLabel, { step: 2, total: 3, name: t(surfaces.stageQueries) })}
          stages={[{ state: "done" }, { state: "now" }, { state: "pending" }]}
        />
      </State>
    </Demo>
  );
}
