import { useMemo } from "react";
import { formatNumber, intlLocale } from "./format";
import { useLang } from "./language";
import type { Lang, PluralPair, TextPair, Vars } from "./types";

const FSI = "⁨"; // first strong isolate: an inserted value never reorders the sentence around it
const LRI = "⁦"; // left-to-right isolate: a number stays in one piece
const PDI = "⁩";

function fill(template: string, lang: Lang, vars?: Vars): string {
  return template.replace(/\{(\w+)\}/g, (_, name: string) => {
    const value = vars?.[name];
    if (value === undefined) throw new Error(`text is missing the value "${name}"`);
    return typeof value === "number" ? `${LRI}${formatNumber(value, lang)}${PDI}` : `${FSI}${value}${PDI}`;
  });
}

export function text(pair: TextPair, lang: Lang, vars?: Vars): string {
  return fill(pair[lang], lang, vars);
}

export function plural(pair: PluralPair, n: number, lang: Lang, vars?: Vars): string {
  const forms: Readonly<Partial<Record<Intl.LDMLPluralRule, string>>> = pair[lang];
  const form = forms[new Intl.PluralRules(intlLocale(lang)).select(n)] ?? pair[lang].other;
  return fill(form, lang, { ...vars, n });
}

export interface Translate {
  (pair: TextPair, vars?: Vars): string;
  plural: (pair: PluralPair, n: number, vars?: Vars) => string;
  lang: Lang;
}

/** The hook every component uses: `const t = useText(); t(common.close)`. */
export function useText(): Translate {
  const { lang } = useLang();
  return useMemo(
    () =>
      Object.assign((pair: TextPair, vars?: Vars) => text(pair, lang, vars), {
        plural: (pair: PluralPair, n: number, vars?: Vars) => plural(pair, n, lang, vars),
        lang,
      }),
    [lang],
  );
}
