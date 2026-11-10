// The app against the fake core (ui/fake.html, npm run dev:ui): for working on a place, its screenshots and the e2e
// tests, with no core and no AI. Vite builds only index.html, so this never ships. The address sets the scene
// (api/fakeCoreBrowser.ts), and ?lang=en|ar and ?theme=light|dark the look; #/gallery and #/specimens show the design
// gallery instead.
import "@/design/tokens.css";
import "../styles.css";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "@/app/App";
import { startFakeCoreInBrowser } from "@/api/fakeCoreBrowser";
import { AppProviders } from "@/design/AppProviders";
import { applyHash } from "@/design/gallery/address";
import { Gallery } from "@/design/gallery/Gallery";
import { setTheme } from "@/design/theme";
import { loadLook } from "@/settings/look";
import { setLang } from "@/texts/language";

const gallery = /^#\/(gallery|specimens)(\/|$)/.test(window.location.hash);
if (gallery) applyHash(); // the language and theme of the address, before the first paint
else {
  await startFakeCoreInBrowser();
  await loadLook();
  const ask = new URLSearchParams(window.location.search);
  const lang = ask.get("lang");
  const theme = ask.get("theme");
  if (lang === "ar" || lang === "en") setLang(lang);
  if (theme === "light" || theme === "dark") setTheme(theme);
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <AppProviders>{gallery ? <Gallery /> : <App />}</AppProviders>
  </StrictMode>,
);
