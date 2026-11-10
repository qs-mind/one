import { Label } from "@/design/ui/label";
import { controls } from "@/texts/design/controls";
import { useText } from "@/texts/useText";
import { Code, Demo, State } from "../parts";

export function LabelDemo() {
  const t = useText();
  return (
    <Demo id="label" title="Label">
      <State name={<Code>size=default</Code>}>
        <Label>{t(controls.firstName)}</Label>
      </State>
      <State name={<Code>size=lg</Code>}>
        <Label size="lg">{t(controls.labelLg)}</Label>
      </State>
    </Demo>
  );
}
