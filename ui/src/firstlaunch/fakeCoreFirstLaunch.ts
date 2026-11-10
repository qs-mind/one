// For tests only: serveFirstLaunch() serves today's first-launch routes (fakeCoreFirstLaunchRoutes.ts) beside the fake
// core. Call it once in a test file, after startFakeCore(); `older` is what the core holds now, and a test changes it to
// set the scene. NEVER import this from application code.
import { beforeEach } from "vitest";
import { server } from "@/api/fakeCore";
import { firstLaunchRoutes, resetFirstLaunch } from "./fakeCoreFirstLaunchRoutes";

export { older } from "./fakeCoreFirstLaunchRoutes";

export function serveFirstLaunch(): void {
  beforeEach(() => {
    resetFirstLaunch();
    server.use(...firstLaunchRoutes);
  });
}
