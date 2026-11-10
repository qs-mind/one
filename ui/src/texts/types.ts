export type Lang = "ar" | "en";
export type Dir = "rtl" | "ltr";

/** One text in both languages. The same shape as the contract's `Text`. */
export type TextPair = { readonly en: string; readonly ar: string };

/** A counted text. `{n}` is the number. English has two forms, Arabic six (Intl.PluralRules). */
export type PluralPair = {
  readonly en: { readonly one: string; readonly other: string };
  readonly ar: {
    readonly zero: string;
    readonly one: string;
    readonly two: string;
    readonly few: string;
    readonly many: string;
    readonly other: string;
  };
};

/** Values placed into a text at `{name}`. */
export type Vars = Readonly<Record<string, string | number>>;

/** Declares the texts of one area; the keys stay typed. */
export const defineTexts = <const T extends Record<string, TextPair | PluralPair>>(texts: T): T => texts;
