import { ListRow } from "@/design/ListRow";
import { Checkbox } from "@/design/ui/checkbox";
import { controls } from "@/texts/design/controls";
import { foundation } from "@/texts/design/foundation";
import { surfaces } from "@/texts/design/surfaces";
import { useText } from "@/texts/useText";
import { Code, Demo, State } from "../parts";

export function CheckboxDemo() {
  const t = useText();
  const name = t(controls.onDevice);
  const row = (props: { defaultChecked?: boolean; disabled?: boolean; invalid?: boolean; force?: "focus" }) => (
    <label className="flex min-h-11 items-center gap-3 has-data-disabled:text-muted-foreground">
      <Checkbox
        defaultChecked={props.defaultChecked}
        disabled={props.disabled}
        aria-invalid={props.invalid || undefined}
        data-force={props.force}
      />
      {name}
    </label>
  );
  return (
    <Demo id="checkbox" title="Checkbox">
      <State name={t(foundation.rest)}>{row({})}</State>
      <State name={t(foundation.checked)}>{row({ defaultChecked: true })}</State>
      <State name={t(foundation.focus)}>{row({ force: "focus" })}</State>
      <State name={t(foundation.disabled)}>{row({ disabled: true })}</State>
      <State name={`${t(foundation.disabled)} · ${t(foundation.checked)}`}>
        {row({ disabled: true, defaultChecked: true })}
      </State>
      <State name={t(foundation.error)}>{row({ invalid: true })}</State>
      <State name={<Code>on/off row</Code>} className="flex w-full max-w-xl flex-col gap-2">
        <ListRow
          frame="boxed"
          render={<label />}
          leading={<Checkbox defaultChecked />}
          title={name}
          meta={t(surfaces.onDeviceMeta)}
        />
      </State>
    </Demo>
  );
}
