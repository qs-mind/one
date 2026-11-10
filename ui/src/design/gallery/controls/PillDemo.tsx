import { FlaskConicalIcon } from "lucide-react";
import { Pill } from "@/design/Pill";
import { common } from "@/texts/common";
import { useText } from "@/texts/useText";
import { Code, Demo, State } from "../parts";

export function PillDemo() {
  const t = useText();
  return (
    <Demo id="pill" title="Pill">
      <State name={<Code>Pill</Code>}>
        <Pill>{t(common.sample)}</Pill>
      </State>
      <State name={<Code>Pill · icon 16</Code>}>
        <Pill>
          <FlaskConicalIcon aria-hidden />
          {t(common.sample)}
        </Pill>
      </State>
    </Demo>
  );
}
