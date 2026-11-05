import "./polyfills";
import "@fontsource-variable/kumbh-sans";
import "@fontsource/zain/arabic-400.css";
import "@fontsource/zain/arabic-700.css";
import "./styles.css";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { HealthGate } from "./app/CoreDown";
import { ScreenError } from "./app/ScreenError";
import { language, setLanguage } from "./i18n";
import { App } from "./shell/App";

setLanguage(language()); // put the remembered language and its direction on <html>

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ScreenError>
      <HealthGate>
        <App />
      </HealthGate>
    </ScreenError>
  </StrictMode>,
);
