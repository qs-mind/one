// The fake core in the browser, for the dev page (ui/fake.html, npm run dev:ui), its screenshots and the e2e tests: the
// same routes the unit tests use (fakeCoreRoutes.ts, and today's first-launch and Settings routes), answered by msw's
// Service Worker, with the tender's kept routes empty. Every number is sample data. NEVER import this from application
// code: only ui/src/fake does, and Vite never builds that page.
//
// The address chooses the scene: ?first is a clean start (first launch from step 1, an empty profile), ?first=profile
// has the language chosen, ?first=upgrade is someone upgrading (language and AI passed, the profile still empty);
// ?scenario=home:empty puts another sample in place. A clean start has no AI linked.
import { http, HttpResponse } from "msw";
import { setupWorker } from "msw/browser";
import { firstLaunchRoutes, older } from "@/firstlaunch/fakeCoreFirstLaunchRoutes";
import { kept, settingsRoutes } from "@/settings/fakeCoreSettingsRoutes";
import { contractRoutes } from "./fakeCoreRoutes";
import { scenario, type Scenario } from "./fakeCoreSamples";

const named = (id: unknown) => (id === "general" ? "General" : `Tender ${String(id).slice(-1)} (sample)`);

// The tender's kept routes (today's chat history, Project Records and the Project Map), with nothing in them yet.
const keptRoutes = [
  http.get("*/api/health", () => HttpResponse.json({ ok: true })),
  http.post("*/api/projects/:id/open", ({ params }) =>
    HttpResponse.json({ id: params.id, name: named(params.id), created_at: "2026-11-01T09:00:00+00:00", open: true }),
  ),
  http.get("*/api/chat/:id/messages", () => HttpResponse.json({ messages: [] })),
  http.get("*/api/chat/:id/stream", () => new HttpResponse(null, { status: 204 })),
  http.get("*/api/projects/:id/deliverables", () => HttpResponse.json({ deliverables: [] })),
  http.get("*/api/projects/:id/files", () => HttpResponse.json({ files: [] })),
  http.get("*/api/projects/:id/workspace", () => HttpResponse.json({ open: null, anchor: null, client_boqs: [] })),
  http.put("*/api/projects/:id/workspace", () => new HttpResponse(null, { status: 204 })),
  http.get("*/api/projects/:id/map", () =>
    HttpResponse.json({ status: { waiting: 0, reading: 0, total: 0, line: { en: "", ar: "" } }, groups: [], files: [], next_cursor: null }),
  ),
  http.get("*/api/projects/:id/map/facts", () => HttpResponse.json({ facts: [], next_cursor: null })),
  http.get("*/api/projects/:id/map/links", () => HttpResponse.json({ links: [], next_cursor: null })),
];

// Any other route of the core: refused in words, so a place says what it says when the core refuses.
const notHere = http.all("*/api/*", () =>
  HttpResponse.json({ error: { en: "The fake core has no answer for this.", ar: "النسخة التجريبية مالهاش رد على ده." } }, { status: 404 }),
);

/** Sets the scene the address asks for, then answers every call until the page is left. */
export async function startFakeCoreInBrowser(): Promise<void> {
  const ask = new URLSearchParams(window.location.search);
  const first = ask.get("first");
  if (first === null || first === "profile" || first === "upgrade") older.steps.language = "done";
  if (first === null || first === "upgrade") older.steps.ai = "done";
  if (first !== null) scenario("profile:incomplete");
  if (first === "") kept.ai.connectors = []; // a clean start: no AI linked yet, so step 3 offers Later
  const name = ask.get("scenario");
  if (name) scenario(name as Scenario);
  const worker = setupWorker(...contractRoutes, ...firstLaunchRoutes, ...settingsRoutes, ...keptRoutes, notHere);
  await worker.start({ onUnhandledFrame: "bypass", quiet: true });
}
