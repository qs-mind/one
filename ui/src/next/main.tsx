// The new interface's dev entry (ui/next.html, npm run dev:ui). Vite builds only index.html, so this never ships.
// In this job it shows the design gallery: #/gallery (the start) and #/specimens.
import "@/design/tokens.css";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { AppProviders } from "@/design/AppProviders";
import { applyHash } from "@/design/gallery/address";
import { Gallery } from "@/design/gallery/Gallery";

applyHash(); // the language and theme of the address, before the first paint

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <AppProviders>
      <Gallery />
    </AppProviders>
  </StrictMode>,
);
