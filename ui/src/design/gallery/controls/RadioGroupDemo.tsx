import { RadioGroup, RadioGroupItem } from "@/design/ui/radio-group";
import { controls } from "@/texts/design/controls";
import { foundation } from "@/texts/design/foundation";
import { useText } from "@/texts/useText";
import { Demo, State } from "../parts";

const OPTIONS = ["recommended", "ownChoice"] as const;

function Stack({ disabled, invalid, force }: { disabled?: boolean; invalid?: boolean; force?: "focus" }) {
  const t = useText();
  return (
    <RadioGroup aria-label={t(controls.models)} defaultValue="recommended" disabled={disabled}>
      {OPTIONS.map((key, index) => (
        <label key={key} className="flex min-h-11 items-center gap-3 has-data-disabled:text-muted-foreground">
          <RadioGroupItem
            value={key}
            aria-invalid={invalid || undefined}
            data-force={index === 0 ? force : undefined}
          />
          {t(controls[key])}
        </label>
      ))}
    </RadioGroup>
  );
}

export function RadioGroupDemo() {
  const t = useText();
  return (
    <Demo id="radio-group" title="RadioGroup">
      <State name={`${t(foundation.rest)} · ${t(foundation.checked)}`}>
        <Stack />
      </State>
      <State name={t(foundation.focus)}>
        <Stack force="focus" />
      </State>
      <State name={t(foundation.disabled)}>
        <Stack disabled />
      </State>
      <State name={t(foundation.error)}>
        <Stack invalid />
      </State>
    </Demo>
  );
}
