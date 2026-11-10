// The seven fields of the profile in two columns (one under 640px), wired to a react-hook-form form checked by the
// shared schema (@/engineer/profile). A field shows zod's problem in words, or the core's own refusal when it gave one.
import { type ReactNode, useMemo } from "react";
import { Controller, type UseFormReturn } from "react-hook-form";
import { Field } from "@/design/Field";
import { Input } from "@/design/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/design/ui/select";
import {
  COUNTRIES,
  currencyChoices,
  type FieldName,
  ORG_TYPES,
  problemText,
  type ProfileForm,
  type ProfileValid,
  USUAL_CURRENCY,
} from "@/engineer/profile";
import { engineer } from "@/texts/engineer";
import { intlLocale } from "@/texts/format";
import type { TextPair } from "@/texts/types";
import { useText } from "@/texts/useText";

type Form = UseFormReturn<ProfileForm, unknown, ProfileValid>;
/** The core's refusal of one field (422 PROFILE_BAD_VALUE), shown until the field is saved again. */
export type Refused = { field: FieldName; words: TextPair } | null;

const TYPED = [
  { name: "first_name", label: engineer.first_name },
  { name: "last_name", label: engineer.last_name },
  { name: "position", label: engineer.position, example: engineer.positionExample },
  { name: "company", label: engineer.company },
] as const;

export function ProfileFields({ form, refused }: { form: Form; refused: Refused }) {
  const t = useText();
  const errors = form.formState.errors;
  const currencies = useMemo(() => currencyChoices(intlLocale(t.lang)), [t.lang]);

  function problem(field: FieldName): ReactNode {
    if (refused?.field === field) return t(refused.words);
    const code = errors[field]?.message;
    if (code === undefined) return undefined;
    const { pair, max } = problemText(field, code);
    return t(pair, max === undefined ? undefined : { max });
  }

  const choice = (name: "org_type" | "country" | "currency", items: { value: string; label: string }[], label: TextPair) => (
    <Field label={t(label)} error={problem(name)}>
      <Controller
        name={name}
        control={form.control}
        render={({ field }) => (
          <Select
            items={items}
            value={field.value === "" ? null : field.value}
            onValueChange={(value) => {
              const next = typeof value === "string" ? value : "";
              field.onChange(next);
              // Choosing a country fills its usual currency; "another country" leaves the currency as it is.
              if (name === "country" && next in USUAL_CURRENCY)
                form.setValue("currency", USUAL_CURRENCY[next as keyof typeof USUAL_CURRENCY], { shouldValidate: form.formState.isSubmitted });
            }}
          >
            <SelectTrigger ref={field.ref} onBlur={field.onBlur}>
              <SelectValue placeholder={t(engineer.choose)} />
            </SelectTrigger>
            <SelectContent>
              {items.map((item) => (
                <SelectItem key={item.value} value={item.value}>
                  {item.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
      />
    </Field>
  );

  return (
    <div className="grid grid-cols-2 gap-5 max-sm:grid-cols-1">
      {TYPED.map((typed) => (
        <Field key={typed.name} label={t(typed.label)} error={problem(typed.name)}>
          <Input {...form.register(typed.name)} placeholder={"example" in typed ? t(typed.example) : undefined} />
        </Field>
      ))}
      {choice("org_type", ORG_TYPES.map((value) => ({ value, label: t(engineer[value]) })), engineer.org_type)}
      {choice("country", COUNTRIES.map((value) => ({ value, label: t(engineer[value]) })), engineer.country)}
      {choice("currency", currencies, engineer.currency)}
    </div>
  );
}
