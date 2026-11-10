// A core for tests: it answers every Phase 1 route from sample data. NEVER import it from application code: only a
// *.test file may (fakeCore.test.ts checks), or msw and the samples end up in the app.
//
// In a test file: call startFakeCore() once, then use the screen or the client as the app does. The samples live in
// memory for one test and change as the core would change them, so a test can press a button and see what comes next.
// `scenario` puts another sample of a route in place; `stageEnds` does what the core does by itself.
//
// It serves the activity stream too (fakeCoreLive.ts): each change above is said on it as the core says it, so a
// screen that listens moves with no reload. `publish` says anything else the core would (a member's line, a Brief).
import { setupServer } from "msw/node";
import { afterAll, afterEach, beforeAll } from "vitest";
import { hangUp } from "./fakeCoreLive";
import { contractRoutes } from "./fakeCoreRoutes";
import { resetFakeCore } from "./fakeCoreSamples";

export { hangUp, listening, publish } from "./fakeCoreLive";
export { P1, P2, P3, P4, P5, P6, resetFakeCore, scenario, stageEnds, type Scenario } from "./fakeCoreSamples";

/** The msw server behind the fake core: a test adds a route of its own with `server.use(...)`. */
export const server = setupServer(...contractRoutes);

/** Call once in a test file: the fake core answers its tests, and the samples are put back after each one. A call the
 * fake core has no route for fails, so nothing reaches the network. */
export function startFakeCore(): void {
  beforeAll(() => server.listen({ onUnhandledFrame: "error" }));
  afterEach(() => {
    server.resetHandlers();
    hangUp();
    resetFakeCore();
  });
  afterAll(() => server.close());
}
