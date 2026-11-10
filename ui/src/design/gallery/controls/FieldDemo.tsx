import { Field } from "@/design/Field";
import { Input } from "@/design/ui/input";
import { controls } from "@/texts/design/controls";
import { foundation } from "@/texts/design/foundation";
import { useText } from "@/texts/useText";
import { Code, Demo, State } from "../parts";

const BOX = "flex w-80 flex-col gap-2";

export function FieldDemo() {
  const t = useText();
  return (
    <Demo id="field" title="Field">
      <State name={t(foundation.rest)} className={BOX}>
        <Field label={t(controls.role)} help={t(controls.roleExample)}>
          <Input />
        </Field>
      </State>
      <State name={t(controls.checking)} className={BOX}>
        <Field label={t(controls.apiKey)} help={t(controls.keyChecking)}>
          <Input dir="ltr" defaultValue="sk-sample-0000" />
        </Field>
      </State>
      <State name={t(foundation.error)} className={BOX}>
        <Field label={t(controls.apiKey)} error={t(controls.keyRejected)}>
          <Input dir="ltr" defaultValue="sk-sample-0000" />
        </Field>
      </State>
      <State name={<Code>labelSize=lg</Code>} className={BOX}>
        <Field label={t(controls.labelLg)} labelSize="lg" help={t(controls.keyHelp)}>
          <Input dir="ltr" placeholder={t(controls.keyPlaceholder)} />
        </Field>
      </State>
    </Demo>
  );
}
