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
import { installScale } from "./ui/scale";
import { UpdateCard } from "./update/UpdateCard";

setLanguage(language()); // put the remembered language and its direction on <html>
installCrashReports(); // an error the screen does not catch: its class and our file:line, to Usage Stats
installPointerFocus(); // focus rings for the keyboard only, not after a click
installScale(); // every size follows the window, from the first paint (the zoom comes once the core answers)
// the real-window walks' bridge (scripts/realapp): a dev server started with it only; a production build drops it
if (import.meta.env.DEV && import.meta.env.VITE_QSONE_TEST_BRIDGE === "1") {
  const url: string = import.meta.env.VITE_QSONE_TEST_BRIDGE_URL;
  void import("./testbridge").then((bridge) => bridge.install(url));
}

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
