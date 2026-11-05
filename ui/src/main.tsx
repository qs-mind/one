import "./polyfills";
import "@fontsource-variable/kumbh-sans";
import "@fontsource/zain/arabic-400.css";
import "@fontsource/zain/arabic-700.css";
import "./styles.css";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { HealthGate } from "./app/CoreDown";
import { Chat } from "./chat/Chat";
import { language, setLanguage } from "./i18n";

setLanguage(language()); // put the remembered language and its direction on <html>

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <HealthGate>
      <Chat />
    </HealthGate>
  </StrictMode>,
);
