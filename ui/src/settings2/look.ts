// A `look.*` setting takes effect on the page as soon as it is stored: the language, the theme, and the zoom (every
// size is in rem, so the root size scales the whole interface).
import { setTheme, type ThemeSetting } from "@/design/theme";
import { setLang } from "@/texts/language";
import type { Setting } from "./useSettings";

const THEMES: readonly string[] = ["system", "light", "dark"];

export function applyLook(setting: Setting): void {
  if (setting.key === "look.language" && (setting.value === "ar" || setting.value === "en")) setLang(setting.value);
  else if (setting.key === "look.theme" && typeof setting.value === "string" && THEMES.includes(setting.value))
    setTheme(setting.value as ThemeSetting);
  else if (setting.key === "look.zoom" && typeof setting.value === "string" && Number(setting.value) > 0)
    document.documentElement.style.fontSize = `${Number(setting.value) * 100}%`;
}
