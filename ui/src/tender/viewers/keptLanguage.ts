// The kept viewers read the old interface's language store (ui/src/i18n.ts). The tender keeps it in step with the
// screen language before the viewers paint, so a sheet's words follow the page.
import { useLayoutEffect } from "react";
import { language, setLanguage } from "@/i18n";
import { useLang } from "@/texts/language";

export function useKeptLanguage(): void {
  const { lang } = useLang();
  useLayoutEffect(() => {
    if (language() !== lang) setLanguage(lang);
  }, [lang]);
}
