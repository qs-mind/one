// The new interface's dev entry (ui/next.html, npm run dev:ui). Vite builds only index.html, so this never ships.
// It shows the app (#/, #/tender/<id>…), or the design gallery at #/gallery and #/specimens.
import "@/design/tokens.css";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "@/app/App";
import { AppProviders } from "@/design/AppProviders";
import { applyHash } from "@/design/gallery/address";
import { Gallery } from "@/design/gallery/Gallery";

const gallery = /^#\/(gallery|specimens)(\/|$)/.test(window.location.hash);
if (gallery) applyHash(); // the language and theme of the address, before the first paint

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <AppProviders>{gallery ? <Gallery /> : <App />}</AppProviders>
  </StrictMode>,
);
