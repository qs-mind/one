import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/design/ui/select";
import { controls } from "@/texts/design/controls";
import { foundation } from "@/texts/design/foundation";
import { useText } from "@/texts/useText";
import { Demo, State } from "../parts";

const ORG_TYPES = ["contractor", "consultant", "owner", "supplier"] as const;

type OrgSelectProps = { label?: string; disabled?: boolean; invalid?: boolean; force?: "hover" | "focus" };

/** The type-of-organisation select of first launch; also used by the specimens. Inside a Field it takes the label. */
export function OrgSelect({ label, disabled, invalid, force }: OrgSelectProps) {
  const t = useText();
  const items = ORG_TYPES.map((value) => ({ value, label: t(controls[value]) }));
  return (
    <Select items={items} defaultValue="contractor" disabled={disabled}>
      <SelectTrigger aria-label={label} aria-invalid={invalid || undefined} data-force={force}>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {items.map((item) => (
          <SelectItem key={item.value} value={item.value}>
            {item.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

const BOX = "flex w-72 flex-col gap-2";

export function SelectDemo() {
  const t = useText();
  const label = t(controls.orgType);
  return (
    <Demo id="select" title="Select">
      <State name={`${t(foundation.rest)} · ${t(foundation.opensOnClick)}`} className={BOX}>
        <OrgSelect label={label} />
      </State>
      <State name={t(foundation.hover)} className={BOX}>
        <OrgSelect label={label} force="hover" />
      </State>
      <State name={t(foundation.focus)} className={BOX}>
        <OrgSelect label={label} force="focus" />
      </State>
      <State name={t(foundation.disabled)} className={BOX}>
        <OrgSelect label={label} disabled />
      </State>
      <State name={t(foundation.error)} className={BOX}>
        <OrgSelect label={label} invalid />
      </State>
    </Demo>
  );
}
