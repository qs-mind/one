// The rail in the frame: which item is current for which address, and where each one goes. The Rail's own look and
// keyboard are tested in @/design/Rail.test.tsx.
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import type { Schemas } from "@/api/client";
import { P2, P3, scenario, server, startFakeCore } from "@/api/fakeCore";
import { DIRS, renderIn, resetPage, stubBrowser } from "@/design/test/harness";
import { common } from "@/texts/common";
import { text } from "@/texts/useText";
import type { Dir } from "@/texts/types";
import { paths } from "./paths";
import { appRoutes } from "./routes";

startFakeCore();

const PASSED: Schemas["SetupSteps"] = { done: true, steps: { language: "done", account: "done", ai: "done", card: null, usage: null } };

beforeEach(() => {
  stubBrowser();
  server.use(http.get("*/api/setup", () => HttpResponse.json(PASSED)));
});
afterEach(resetPage);

describe.each(DIRS)("the rail (%s)", (dir: Dir) => {
  const t = (pair: { en: string; ar: string }) => text(pair, dir === "rtl" ? "ar" : "en");
  const NAMES = [t(common.home), t(common.tenders), t(common.settings)];

  async function open(path: string) {
    const router = createMemoryRouter(appRoutes, { initialEntries: [path] });
    renderIn(dir, <RouterProvider router={router} />);
    const nav = await screen.findByRole("navigation", { name: t(common.navigation) });
    return { router, nav };
  }
  const link = (name: string) => screen.getByRole("link", { name });
  const current = (nav: HTMLElement) => [...nav.querySelectorAll('[aria-current="page"]')].map((el) => el.getAttribute("aria-label"));

  it("has three destinations, links in this order, and stands on the start side", async () => {
    const { nav } = await open(paths.home);
    expect([...nav.querySelectorAll("a")].map((el) => el.getAttribute("aria-label"))).toEqual(NAMES);
    expect(document.documentElement.dir).toBe(dir);
    expect(nav.parentElement?.firstElementChild).toBe(nav); // first in the frame: the start side in either direction
  });

  it.each([
    [paths.home, 0],
    [paths.tender(P2), 1],
    [paths.doc(P2, "d1"), 1],
    [paths.room(P2), 1],
    [paths.member(P2, "lead-qs"), 1],
    [paths.settings("caps"), 2],
  ])("marks the current place at %s", async (path, at) => {
    const { nav } = await open(path);
    expect(current(nav)).toEqual([NAMES[at]]);
  });

  it("goes to Home, to the tender last opened, and to Settings", async () => {
    const { router } = await open(paths.settings("caps"));
    await waitFor(() => expect(link(NAMES[1]!).getAttribute("href")).toBe(paths.tender(P2))); // Home.last_project_id
    expect(link(NAMES[0]!).getAttribute("href")).toBe(paths.home);
    expect(link(NAMES[2]!).getAttribute("href")).toBe(paths.settings());
    await userEvent.click(link(NAMES[1]!));
    expect(router.state.location.pathname).toBe(paths.tender(P2));
    await userEvent.click(link(NAMES[2]!));
    expect(router.state.location.pathname).toBe(paths.settings());
    await userEvent.click(link(NAMES[0]!));
    expect(router.state.location.pathname).toBe(paths.home);
  });

  it("keeps the tender open in this session as the Tender destination", async () => {
    const { router, nav } = await open(paths.room(P3));
    expect(link(NAMES[1]!).getAttribute("href")).toBe(paths.tender(P3));
    await userEvent.click(link(NAMES[0]!));
    expect(current(nav)).toEqual([NAMES[0]]);
    expect(router.state.location.pathname).toBe(paths.home);
    expect(link(NAMES[1]!).getAttribute("href")).toBe(paths.tender(P3));
  });

  it("with no tender opened yet, Tenders leads to Home's list", async () => {
    scenario("home:empty");
    await open(paths.settings("caps"));
    await waitFor(() => expect(link(NAMES[1]!).getAttribute("href")).toBe(paths.home));
  });
});
