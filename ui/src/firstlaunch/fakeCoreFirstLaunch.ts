// For tests only: serveFirstLaunch() serves today's first-launch routes (fakeCoreFirstLaunchRoutes.ts) beside the fake
// core. Call it once in a test file, after startFakeCore(); `older` is what the core holds now, and a test changes it to
// set the scene. NEVER import this from application code.
import { http, HttpResponse } from "msw";
import { beforeEach } from "vitest";
import { server } from "@/api/fakeCore";
import { firstLaunchRoutes, older, resetFirstLaunch } from "./fakeCoreFirstLaunchRoutes";

export { older } from "./fakeCoreFirstLaunchRoutes";

export function serveFirstLaunch(): void {
  beforeEach(() => {
    resetFirstLaunch();
    // The AI links, for step 3 (in the browser and in Settings' tests, Settings' own routes answer it).
    const links = http.get("*/api/settings/ai", () => HttpResponse.json({ connectors: older.links, sheet: [], roles: {}, defaults: {} }));
    server.use(...firstLaunchRoutes, links);
  });
}
