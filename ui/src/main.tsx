import "./polyfills";
import "@fontsource-variable/kumbh-sans";
// Zain (Arabic, 400 and 700) is declared in styles.css, a little larger than its own size
import "./styles.css";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { HealthGate } from "./app/CoreDown";
import { installCrashReports } from "./app/crash";
import { ScreenError } from "./app/ScreenError";
import { SetupGate } from "./firstlaunch/FirstLaunch";
import { importFolders } from "./import/importer";
import { language, setLanguage } from "./i18n";
import { App } from "./shell/App";
import { installPointerFocus } from "./ui/pointerFocus";
import { UpdateCard } from "./update/UpdateCard";

setLanguage(language()); // put the remembered language and its direction on <html>
installCrashReports(); // an error the screen does not catch: its class and our file:line, to Usage Stats
installPointerFocus(); // focus rings for the keyboard only, not after a click

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ScreenError>
      <HealthGate>
        <SetupGate onImport={(from, old) => void importFolders(from, { old })}>
          <App />
          <UpdateCard />
        </SetupGate>
      </HealthGate>
    </ScreenError>
  </StrictMode>,
);
