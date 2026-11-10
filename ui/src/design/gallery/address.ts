// The gallery's address: #/<view>/<lang>/<theme>, e.g. #/specimens/en/dark. Read at start and on every hashchange;
// it sets the language and theme stores, and the switches write it. Nothing is stored anywhere else.
import { useEffect, useSyncExternalStore } from "react";
import { setTheme, type ThemeSetting } from "@/design/theme";
import { setLang } from "@/texts/language";
import type { Lang } from "@/texts/types";

export type View = "gallery" | "specimens" | "conversation";
export type Address = { view: View; lang: Lang; theme: ThemeSetting };

const VIEWS: readonly View[] = ["gallery", "specimens", "conversation"];
const LANGS: readonly Lang[] = ["ar", "en"];
const THEMES: readonly ThemeSetting[] = ["system", "light", "dark"];

const pick = <T extends string>(options: readonly T[], value: string | undefined, fallback: T): T =>
  options.find((option) => option === value) ?? fallback;

/** Missing or unknown parts fall back to the gallery, Arabic, the system theme. */
export function parseHash(hash: string): Address {
  const [view, lang, theme] = hash.replace(/^#\/?/, "").split("/");
  return { view: pick(VIEWS, view, "gallery"), lang: pick(LANGS, lang, "ar"), theme: pick(THEMES, theme, "system") };
}

export const toHash = ({ view, lang, theme }: Address): string => `#/${view}/${lang}/${theme}`;

function subscribe(listener: () => void): () => void {
  window.addEventListener("hashchange", listener);
  return () => window.removeEventListener("hashchange", listener);
}

const readHash = () => window.location.hash;

/** Applies the address in the hash to the language and theme stores. main.tsx calls it before the first render. */
export function applyHash(): void {
  const { lang, theme } = parseHash(readHash());
  setLang(lang);
  setTheme(theme);
}

/** The current address, applied to the stores; `go` writes a changed part into the hash. */
export function useAddress(): [Address, (next: Partial<Address>) => void] {
  const address = parseHash(useSyncExternalStore(subscribe, readHash, readHash));
  const { lang, theme } = address;
  useEffect(() => {
    setLang(lang);
    setTheme(theme);
  }, [lang, theme]);
  const go = (next: Partial<Address>) => {
    window.location.hash = toHash({ ...address, ...next });
  };
  return [address, go];
}
