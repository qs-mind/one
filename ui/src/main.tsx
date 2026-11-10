import "./polyfills";
import "@/design/tokens.css";
import "./styles.css";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./app/App";
import { HealthGate } from "./app/CoreDown";
import { installCrashReports } from "./app/crash";
import { ScreenError } from "./app/ScreenError";
import { AppProviders } from "./design/AppProviders";
import { UpdateCard } from "./update/UpdateCard";

installCrashReports(); // an error the screen does not catch: its class and our file:line, to Usage Stats
// the real-window walks' bridge (scripts/realapp): a dev server started with it only; a production build drops it
if (import.meta.env.DEV && import.meta.env.VITE_QSONE_TEST_BRIDGE === "1") {
  const url: string = import.meta.env.VITE_QSONE_TEST_BRIDGE_URL;
  void import("./testbridge").then((bridge) => bridge.install(url));
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ScreenError>
      <HealthGate>
        <AppProviders>
          <App />
          <UpdateCard />
        </AppProviders>
      </HealthGate>
    </ScreenError>
  </StrictMode>,
);
