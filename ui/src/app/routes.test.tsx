import { screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import type { Schemas } from "@/api/client";
import { P2, scenario, server, startFakeCore } from "@/api/fakeCore";
import { renderIn, resetPage, stubBrowser } from "@/design/test/harness";
import { appRoutes } from "./routes";
import { paths } from "./paths";

startFakeCore();

// GET /setup is today's first-launch route, outside the contract's routes, so the fake core does not serve it.
type Steps = Schemas["SetupStepStates"];
const PASSED: Steps = { language: "done", account: "done", ai: "done", card: null, usage: null };
let steps: Steps;
let setupCalls: number;

beforeEach(() => {
  stubBrowser();
  steps = PASSED;
  setupCalls = 0;
  server.use(
    http.get("*/api/setup", () => {
      setupCalls++;
      return HttpResponse.json({ done: false, steps } satisfies Schemas["SetupSteps"]);
    }),
  );
});
afterEach(resetPage);

function open(path: string) {
  const router = createMemoryRouter(appRoutes, { initialEntries: [path] });
  renderIn("rtl", <RouterProvider router={router} />);
  return router;
}

const place = async (name: string) => {
  await waitFor(() => expect(document.querySelector(`[data-place="${name}"]`)).not.toBeNull());
  return document.querySelector<HTMLElement>(`[data-place="${name}"]`)!;
};
const where = (router: ReturnType<typeof open>) => router.state.location.pathname;

describe("each route renders its place", () => {
  it.each([
    [paths.home, "home", {}],
    [paths.tender(P2), "tender", { tender: P2, view: "conversation" }],
    [paths.doc(P2, "d1"), "tender", { tender: P2, view: "doc", doc: "d1" }],
    [paths.room(P2), "tender", { tender: P2, view: "room" }],
    [paths.member(P2, "lead-qs"), "tender", { tender: P2, view: "member", member: "lead-qs" }],
    [paths.settings("caps"), "settings", { section: "caps" }],
    [paths.welcome("profile"), "welcome", { step: "profile" }],
  ])("%s", async (path, name, data) => {
    const router = open(path);
    const main = await place(name);
    expect({ ...main.dataset }).toEqual({ place: name, ...data });
    expect(where(router)).toBe(path);
  });

  it("the rail stands beside every place but first launch", async () => {
    open(paths.room(P2));
    await place("tender");
    expect(screen.getByRole("navigation")).toBeTruthy();
    resetPage();
    document.body.innerHTML = "";
    open(paths.welcome("language"));
    await place("welcome");
    expect(screen.queryByRole("navigation")).toBeNull();
  });

  it("Settings with no section opens the first; an unknown address opens Home", async () => {
    const router = open("/settings");
    await place("settings");
    expect(where(router)).toBe(paths.settings());
    await router.navigate("/nowhere/at/all");
    await place("home");
    expect(where(router)).toBe(paths.home);
  });
});

describe("the first-launch gate", () => {
  it("sends an incomplete profile to step 2, from any address", async () => {
    scenario("profile:incomplete");
    const router = open(paths.room(P2));
    await place("welcome");
    expect(where(router)).toBe(paths.welcome("profile"));
  });

  it("sends a first launch with no language to step 1, and one with no AI step to step 3", async () => {
    steps = { ...PASSED, language: null, ai: null };
    const first = open(paths.home);
    await place("welcome");
    expect(where(first)).toBe(paths.welcome("language"));
    document.body.innerHTML = "";
    steps = { ...PASSED, ai: null };
    const third = open(paths.home);
    await place("welcome");
    expect(where(third)).toBe(paths.welcome("ai"));
  });

  it("lets a skipped AI step through", async () => {
    steps = { ...PASSED, ai: "skipped" };
    const router = open(paths.settings("ai"));
    await place("settings");
    expect(where(router)).toBe(paths.settings("ai"));
  });

  it("asks again when first launch is left, and lets the engineer in once it is done", async () => {
    scenario("profile:incomplete");
    const router = open(paths.home);
    await place("welcome");
    await waitFor(() => expect(setupCalls).toBe(2)); // the gate's call, then the first-launch screen's own
    scenario("profile");
    await router.navigate(paths.home);
    await place("home");
    expect(where(router)).toBe(paths.home);
    expect(setupCalls).toBe(3);
  });

  it("asks again on leaving and sends back what is still not done", async () => {
    scenario("profile:incomplete");
    const router = open(paths.home);
    await place("welcome");
    await waitFor(() => expect(setupCalls).toBe(2)); // the gate's call, then the first-launch screen's own
    await router.navigate(paths.tender(P2));
    await waitFor(() => expect(setupCalls).toBe(3));
    await place("welcome");
    expect(where(router)).toBe(paths.welcome("profile"));
  });

  it("does not hold the engineer when the core cannot answer it", async () => {
    server.use(
      http.get("*/api/setup", () => HttpResponse.text("down", { status: 500 })),
      http.get("*/api/engineer/profile", () => HttpResponse.error()),
    );
    const router = open(paths.tender(P2));
    await place("tender");
    expect(where(router)).toBe(paths.tender(P2));
  });

  it("shows no place while it asks", () => {
    server.use(http.get("*/api/setup", () => new Promise<never>(() => {})));
    open(paths.home);
    expect(document.querySelector("[data-place]")).toBeNull();
    expect(document.querySelector('[aria-busy="true"]')).not.toBeNull();
  });
});
