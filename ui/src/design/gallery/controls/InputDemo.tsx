import { Field } from "@/design/Field";
import { Num } from "@/design/Num";
import { Input } from "@/design/ui/input";
import { controls } from "@/texts/design/controls";
import { foundation } from "@/texts/design/foundation";
import { useText } from "@/texts/useText";
import { Code, Demo, State } from "../parts";

const FORCED = ["hover", "focus"] as const;
const BOX = "flex w-72 flex-col gap-2";

export function InputDemo() {
  const t = useText();
  const name = t(controls.role);
  return (
    <Demo id="input" title="Input">
      <State name={t(foundation.rest)} className={BOX}>
        <Input aria-label={name} placeholder={t(controls.roleExample)} />
      </State>
      {FORCED.map((state) => (
        <State key={state} name={t(foundation[state])} className={BOX}>
          <Input aria-label={name} data-force={state} placeholder={t(controls.roleExample)} />
        </State>
      ))}
      <State name={t(foundation.filled)} className={BOX}>
        <Input aria-label={name} defaultValue={t(controls.roleExample)} />
      </State>
      <State name={t(foundation.disabled)} className={BOX}>
        <Input aria-label={name} disabled defaultValue={t(controls.roleExample)} />
      </State>
      <State name={t(foundation.error)} className={BOX}>
        <Input aria-label={name} aria-invalid defaultValue={t(controls.roleExample)} />
      </State>
      <State name={<Code>dir=ltr</Code>} className="flex w-full max-w-xl flex-col gap-2">
        <Input aria-label={t(controls.apiKey)} dir="ltr" placeholder={t(controls.keyPlaceholder)} />
      </State>
      <State name={<Code>variant=bare · unit box</Code>} className={BOX}>
        <Field label={t(controls.monthlyCap)}>
          <div className="focus-ring-within flex h-13 items-center gap-2 rounded-xl border border-input bg-card px-4 hover:border-muted-foreground has-aria-invalid:border-2 has-aria-invalid:border-foreground has-aria-invalid:px-[calc(--spacing(4)-1px)]">
            <Input variant="bare" dir="ltr" inputMode="decimal" defaultValue="1500" />
            <span className="shrink-0 text-xs text-muted-foreground">
              <Num>{t(controls.currency)}</Num>
            </span>
          </div>
        </Field>
      </State>
      <State name={<Code>date</Code>} className={BOX}>
        <Field label={t(controls.submissionDate)} help={t(controls.dateExample)}>
          <Input dir="ltr" inputMode="numeric" />
        </Field>
      </State>
    </Demo>
  );
}
