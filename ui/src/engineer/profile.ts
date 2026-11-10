// The engineer's profile as a form: one zod schema that first launch (step 2) and Settings, My profile, share. The
// form holds every value as text ("" until filled); the core takes a half-filled profile (PUT /engineer/profile is
// called as the engineer types) and says itself whether it is `complete`. The schema says what stops "Next".
//
// The core checks the same bounds and answers PROFILE_BAD_VALUE with the field when one is passed.
import { z } from "zod";
import type { Schemas } from "@/api/client";
import { engineer } from "@/texts/engineer";
import type { TextPair } from "@/texts/types";

export const ORG_TYPES = ["contractor", "consultant", "owner", "procurement"] as const;
export const COUNTRIES = ["EG", "SA", "AE", "other"] as const;
export type OrgType = (typeof ORG_TYPES)[number];
export type Country = (typeof COUNTRIES)[number];

/** The currency a country usually prices in; filled when the country is chosen. "other" leaves it as it is. */
export const USUAL_CURRENCY: Record<Exclude<Country, "other">, string> = { EG: "EGP", SA: "SAR", AE: "AED" };

export const FIELDS = ["first_name", "last_name", "position", "company", "org_type", "country", "currency"] as const;
export type FieldName = (typeof FIELDS)[number];

// A problem travels as a short code in zod's message; problemText() turns it into words.
const typed = (max: number) => z.string().trim().min(1, "missing").max(max, `tooLong:${max}`);
const oneOf = <const T extends readonly [string, ...string[]]>(values: T) => z.string().pipe(z.enum(values, "choose"));

export const profileSchema = z.object({
  first_name: typed(80),
  last_name: typed(80),
  position: typed(120),
  company: typed(120),
  org_type: oneOf(ORG_TYPES),
  country: oneOf(COUNTRIES),
  currency: z.string().min(1, "choose").regex(/^[A-Z]{3}$/, "currency"),
});

/** What the form holds: every field as text. */
export type ProfileForm = z.input<typeof profileSchema>;
/** What the schema hands on once every field passes. */
export type ProfileValid = z.output<typeof profileSchema>;

/** The profile as the core answers it, in the form's terms. */
export function formOf(profile: Schemas["Profile"]): ProfileForm {
  return {
    first_name: profile.first_name,
    last_name: profile.last_name,
    position: profile.position,
    company: profile.company,
    org_type: profile.org_type ?? "",
    country: profile.country ?? "",
    currency: profile.currency ?? "",
  };
}

const isOrgType = (value: string): value is OrgType => (ORG_TYPES as readonly string[]).includes(value);
const isCountry = (value: string): value is Country => (COUNTRIES as readonly string[]).includes(value);

/** The form as PUT /engineer/profile takes it, half-filled or not: an empty choice is null. */
export function toProfileIn(form: ProfileForm): Schemas["ProfileIn"] {
  return {
    first_name: form.first_name,
    last_name: form.last_name,
    position: form.position,
    company: form.company,
    org_type: isOrgType(form.org_type) ? form.org_type : null,
    country: isCountry(form.country) ? form.country : null,
    currency: form.currency === "" ? null : form.currency,
  };
}

/** The words for a problem zod found in a field. */
export function problemText(field: FieldName, code: string | undefined): { pair: TextPair; max?: number } {
  if (code?.startsWith("tooLong:")) return { pair: engineer.tooLong, max: Number(code.slice("tooLong:".length)) };
  if (code === "currency") return { pair: engineer.badCurrency };
  return { pair: field === "org_type" || field === "country" || field === "currency" ? engineer.missingChoice : engineer.missingText };
}

/** Every ISO currency the platform knows, named in the page's language, the usual three first. */
export function currencyChoices(locale: string): { value: string; label: string }[] {
  const names = new Intl.DisplayNames([locale], { type: "currency" });
  const usual = Object.values(USUAL_CURRENCY);
  const rest = Intl.supportedValuesOf("currency").filter((code) => !usual.includes(code));
  return [...usual, ...rest].map((code) => ({ value: code, label: `${names.of(code) ?? code} (${code})` }));
}
