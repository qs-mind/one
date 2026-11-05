// The Introduction card: role, country, city and currency, kept in Engineer Records (PUT /engineer/card). The Lead QS
// reads one line of it. The currency follows the country and can be changed; a city is kept as typed, in any language.
import { type FormEvent, useEffect, useId, useState } from "react";
import { api } from "../api";
import { send } from "../core";
import { t, texts, useLanguage } from "../i18n";
import { field, type Nav, option, primary, StepScreen } from "./parts";

type Role = "contractor" | "consultant" | "owner" | "procurement";
type Country = "EG" | "SA" | "AE" | "other";
type Card = { role: Role; country: Country; city: string; currency: string };

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
const CODE = /^[A-Z]{3}$/;

export function IntroCard({ nav }: { nav: Nav }) {
  useLanguage();
  const [role, setRole] = useState<Role>();
  const [country, setCountry] = useState<Country | "">("");
  const [city, setCity] = useState("");
  const [currency, setCurrency] = useState("");
  const [failed, setFailed] = useState(false);
  const [saving, setSaving] = useState(false);
  const ids = { role: useId(), help: useId() };

  useEffect(() => {
    let live = true;
    void api("/engineer/card")
      .then((r) => (r.ok ? (r.json() as Promise<Partial<Card>>) : undefined))
      .then((saved) => {
        if (!live || !saved?.role) return;
        setRole(saved.role);
        setCountry(saved.country ?? "");
        setCity(saved.city ?? "");
        setCurrency(saved.currency ?? "");
      })
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, []);

  function pickCountry(next: Country | "") {
    setCountry(next);
    const follows = next ? CURRENCY[next] : undefined;
    if (follows) setCurrency(follows);
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!role || !country) return;
    setSaving(true);
    setFailed(false);
    const response = await send("/engineer/card", "PUT", { role, country, city: city.trim(), currency });
    setSaving(false);
    if (!response?.ok) return setFailed(true);
    await nav.pass("done");
  }

  const ready = role !== undefined && country !== "" && CODE.test(currency) && !saving;
  return (
    <form onSubmit={save} noValidate>
      <StepScreen
        title={t("cardTitle")}
        help={t("cardHelp")}
        nav={nav}
        failed={failed && t("cardNotSaved")}
        next={
          <button type="submit" disabled={!ready} className={primary}>
            {t("setupNext")}
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
              <select value={country} onChange={(event) => pickCountry(event.target.value as Country | "")} className={field}>
                <option value="" disabled />
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
          <div className="flex flex-col gap-2 sm:w-1/2 sm:pe-2">
            <label className="flex flex-col gap-2">
            <span>{t("cardCurrency")}</span>
            <input
              dir="ltr"
              maxLength={3}
              spellCheck={false}
              autoComplete="off"
              aria-describedby={ids.help}
              value={currency}
              onChange={(event) => setCurrency(event.target.value.toUpperCase().replace(/[^A-Z]/g, ""))}
              className={`${field} uppercase tracking-wider`}
            />
            </label>
            <span id={ids.help} className="text-xs text-slate">
              {t("cardCurrencyHelp")}
            </span>
          </div>
        </div>
      </StepScreen>
    </form>
  );
}
