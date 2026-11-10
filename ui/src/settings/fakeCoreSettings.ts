// For tests only: serveSettings() serves today's routes Settings keeps using (fakeCoreSettingsRoutes.ts) beside the
// fake core. Call it once in a test file, after startFakeCore() (and serveFirstLaunch() for the AI consent); `kept` is
// what the core holds now, and every call is noted in `kept.calls`. NEVER import this from application code.
import { beforeEach } from "vitest";
import { server } from "@/api/fakeCore";
import { resetSettings, settingsRoutes } from "./fakeCoreSettingsRoutes";

export { CODE, kept } from "./fakeCoreSettingsRoutes";

export function serveSettings(): void {
  beforeEach(() => {
    resetSettings();
    server.use(...settingsRoutes);
  });
}
