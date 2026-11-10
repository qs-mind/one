import { SectionLabel } from "@/design/SectionLabel";
import { surfaces } from "@/texts/design/surfaces";
import { useText } from "@/texts/useText";
import { Demo, State } from "../parts";

export function SectionLabelDemo() {
  const t = useText();
  return (
    <Demo id="section-label" title="SectionLabel">
      {([surfaces.waitingForYou, surfaces.stages, surfaces.teamNow] as const).map((label) => (
        <State key={label.en} name="h3" className="flex flex-col gap-3">
          <SectionLabel as="h3">{t(label)}</SectionLabel>
          <span>{t(surfaces.approvePlan)}</span>
        </State>
      ))}
    </Demo>
  );
}
