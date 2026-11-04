import "@fontsource-variable/kumbh-sans";
import "@fontsource/ibm-plex-sans-arabic/400.css";
import "@fontsource/ibm-plex-sans-arabic/600.css";
import "./styles.css";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { Chat } from "./chat/Chat";
import { language, setLanguage } from "./i18n";

setLanguage(language()); // put the remembered language and its direction on <html>

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Chat />
  </StrictMode>,
);
