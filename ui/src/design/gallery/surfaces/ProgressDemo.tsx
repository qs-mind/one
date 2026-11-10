import { Progress, ProgressLabel, ProgressValue } from "@/design/ui/progress";
import { surfaces } from "@/texts/design/surfaces";
import { useText } from "@/texts/useText";
import { Demo, State } from "../parts";

export function ProgressDemo() {
  const t = useText();
  const words = t(surfaces.downloaded, { done: 62, total: 135 });
  return (
    <Demo id="progress" title="Progress">
      <State name="46%" className="flex w-full max-w-xl flex-col gap-2">
        <Progress value={46} aria-valuetext={words}>
          <ProgressLabel>{t(surfaces.progressLabel)}</ProgressLabel>
          <ProgressValue>{() => words}</ProgressValue>
        </Progress>
      </State>
      <State name={t(surfaces.stateEmpty)} className="flex w-full max-w-xl flex-col gap-2">
        <Progress value={null}>
          <ProgressLabel>{t(surfaces.progressWaiting)}</ProgressLabel>
        </Progress>
      </State>
    </Demo>
  );
}
