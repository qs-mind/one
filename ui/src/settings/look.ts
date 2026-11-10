// A `look.*` setting takes effect on the page as soon as it is stored: the language, the theme, and the zoom (every
// size is in rem, so the root size scales the whole interface).
import { client } from "@/api/client";
import { setTheme, type ThemeSetting } from "@/design/theme";
import { setLang } from "@/texts/language";
import { followZoom } from "@/ui/scale";
import type { Setting } from "./useSettings";

const THEMES: readonly string[] = ["system", "light", "dark"];

export function applyLook(setting: Setting): void {
  if (setting.key === "look.language" && (setting.value === "ar" || setting.value === "en")) setLang(setting.value);
  else if (setting.key === "look.theme" && typeof setting.value === "string" && THEMES.includes(setting.value))
    setTheme(setting.value as ThemeSetting);
  else if (setting.key === "look.zoom" && typeof setting.value === "string" && Number(setting.value) > 0)
    followZoom(Number(setting.value));
}

/** The longest ONE waits for the saved look before it opens as the system has it. */
const LOOK_WAIT_MS = 2000;

/** The engineer's language, theme and zoom from GET /settings, before the first place shows; a missing, failed or
 * late answer keeps the system's. */
export async function loadLook(): Promise<void> {
  const late = new Promise<undefined>((resolve) => setTimeout(() => resolve(undefined), LOOK_WAIT_MS));
  const read = client
    .GET("/settings")
    .then(({ data }) => data)
    .catch(() => undefined);
  const settings = await Promise.race([read, late]);
  for (const setting of settings?.settings ?? []) if (setting.key.startsWith("look.")) applyLook(setting);
}
