// The Introduction card: role, country and city, kept in Engineer Records (PUT /engineer/card). The Lead QS reads one
// line of it. The currency is never asked: it follows the country (EGP, SAR, AED), and "Other" sends none. The country
// starts at the system's own when it is one of the three, else Egypt. A city is kept as typed, in any language.
import { type FormEvent, useEffect, useId, useState } from "react";
import { api } from "../api";
import { coreLine, send } from "../core";
import { pick, t, type Text, texts, useLanguage } from "../i18n";
import { field, type Nav, option, primary, StepScreen } from "./parts";

type Role = "contractor" | "consultant" | "owner" | "procurement";
type Country = "EG" | "SA" | "AE" | "other";
type Card = { role: Role; country: Country; city: string };

const roles: [Role, keyof typeof texts][] = [
  ["contractor", "cardRoleContractor"],
  ["consultant", "cardRoleConsultant"],
  ["owner", "cardRoleOwner"],
  ["procurement", "cardRoleProcurement"],
];
const countries: [Country, keyof typeof texts][] = [
  ["EG", "cardCountryEG"],
  ["SA", "cardCountrySA"],
  ["AE", "cardCountryAE"],
  ["other", "cardCountryOther"],
];
const CURRENCY: Partial<Record<Country, string>> = { EG: "EGP", SA: "SAR", AE: "AED" };

/** The country the system's language names (ar-EG, en-AE…) when it is one of the three, else Egypt. */
function systemCountry(): Country {
  for (const tag of navigator.languages ?? [navigator.language]) {
    let region: string | undefined;
    try {
      region = new Intl.Locale(tag).region;
    } catch {
      continue; // not a language tag
    }
    if (region === "EG" || region === "SA" || region === "AE") return region;
  }
  return "EG";
}

export function IntroCard({ nav }: { nav: Nav }) {
  useLanguage();
  const [role, setRole] = useState<Role>();
  const [country, setCountry] = useState<Country>(systemCountry);
  const [city, setCity] = useState("");
  const [failed, setFailed] = useState<Text>();
  const [saving, setSaving] = useState(false);
  const ids = { role: useId() };

  useEffect(() => {
    let live = true;
    void api("/engineer/card")
      .then((r) => (r.ok ? (r.json() as Promise<Partial<Card>>) : undefined))
      .then((saved) => {
        if (!live || !saved?.role) return;
        setRole(saved.role);
        if (saved.country) setCountry(saved.country);
        setCity(saved.city ?? "");
      })
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, []);

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!role || saving) return;
    setSaving(true);
    setFailed(undefined);
    const response = await send("/engineer/card", "PUT", { role, country, city: city.trim(), currency: CURRENCY[country] });
    setSaving(false);
    if (!response?.ok) return setFailed(await coreLine(response, texts.cardNotSavedRetry)); // the core's own words
    await nav.pass("done");
  }

  const ready = role !== undefined; // not dimmed while it saves: the spinner shows in it
  return (
    <form onSubmit={save} noValidate className="flex flex-1 flex-col">
      <StepScreen
        title={t("cardTitle")}
        help={t("cardHelp")}
        nav={nav}
        failed={failed && pick(failed)}
        next={
          // while it saves, the button itself shows it: nothing above it appears, so the row never moves
          <button type="submit" disabled={!ready} aria-busy={saving} className={`${primary} relative`}>
            <span className={saving ? "invisible" : undefined}>{t("setupNext")}</span>
            {saving && (
              <span className="absolute inset-0 flex items-center justify-center">
                <span aria-hidden="true" className="fl-spin block size-4 rounded-full border-2 border-paper/30 border-t-paper" />
                <span className="sr-only">{t("cardSaving")}</span>
              </span>
            )}
          </button>
        }
      >
        <div className="flex flex-col gap-6">
          <div role="radiogroup" aria-labelledby={ids.role} className="flex flex-col gap-2">
            <span id={ids.role}>{t("cardRole")}</span>
            <div className="grid gap-2 sm:grid-cols-2">
              {roles.map(([value, label]) => (
                <button
                  key={value}
                  type="button"
                  role="radio"
                  aria-checked={role === value}
                  onClick={() => setRole(value)}
                  className={`${option(role === value)} text-start`}
                >
                  {t(label)}
                </button>
              ))}
            </div>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="flex flex-col gap-2">
              <span>{t("cardCountry")}</span>
              <select value={country} onChange={(event) => setCountry(event.target.value as Country)} className={field}>
                {countries.map(([value, label]) => (
                  <option key={value} value={value}>
                    {t(label)}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-2">
              <span>{t("cardCity")}</span>
              <input dir="auto" maxLength={80} value={city} onChange={(event) => setCity(event.target.value)} className={field} />
            </label>
          </div>
        </div>
      </StepScreen>
    </form>
  );
}
