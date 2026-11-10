import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { scenario, startFakeCore } from "@/api/fakeCore";
import { DIRS, renderIn, resetPage, stubBrowser } from "@/design/test/harness";
import { common } from "@/texts/common";
import { engineer } from "@/texts/engineer";
import { firstlaunch } from "@/texts/firstlaunch";
import { getLang } from "@/texts/language";
import { text } from "@/texts/useText";
import { paths } from "@/app/paths";
import { appRoutes } from "@/app/routes";
import { older, serveFirstLaunch } from "./fakeCoreFirstLaunch";

startFakeCore();
serveFirstLaunch();
beforeEach(stubBrowser);
afterEach(resetPage);

const plain = (value: string | null | undefined) => (value ?? "").replace(/[⁦⁨⁩]/g, "");

// First launch as the app opens it: the gate works out the step and puts it in the address; the screen follows.
function open(dir: "rtl" | "ltr", path: string = paths.home) {
  const router = createMemoryRouter(appRoutes, { initialEntries: [path] });
  renderIn(dir, <RouterProvider router={router} />);
  return router;
}
const where = (router: ReturnType<typeof open>) => router.state.location.pathname;

describe.each(DIRS)("Welcome (%s)", (dir) => {
  const lang = dir === "rtl" ? "ar" : "en";
  const say = (pair: { en: string; ar: string }) => text(pair, lang);
  const stepOf = (step: number) => plain(text(common.stepOf, lang, { step, total: 3 }));

  it("a clean start opens on the language; Next says the choice and goes to who you are", async () => {
    scenario("profile:incomplete");
    const router = open(dir);
    expect(await screen.findByRole("heading", { level: 1, name: say(firstlaunch.languageTitle) })).toBeInTheDocument();
    expect(plain(document.body.textContent)).toContain(stepOf(1));
    expect(screen.getByRole("radio", { name: lang === "ar" ? "العربية" : "English" })).toBeChecked();
    await userEvent.click(screen.getByRole("button", { name: say(firstlaunch.next) }));
    expect(await screen.findByRole("heading", { level: 1, name: say(firstlaunch.whoTitle) })).toBeInTheDocument();
    expect(older.calls).toContain(`PUT /setup/language {"state":"done","lang":"${lang}"}`);
    expect(plain(document.body.textContent)).toContain(stepOf(2));
    expect(where(router)).toBe(paths.welcome("profile"));
    await userEvent.click(screen.getByRole("button", { name: say(firstlaunch.back) }));
    expect(await screen.findByRole("heading", { level: 1, name: say(firstlaunch.languageTitle) })).toBeInTheDocument();
    expect(where(router)).toBe(paths.welcome("language"));
  });

  it("choosing the other language turns the page at once", async () => {
    open(dir);
    const other = lang === "ar" ? "English" : "العربية";
    await userEvent.click(await screen.findByRole("radio", { name: other }));
    expect(getLang()).toBe(lang === "ar" ? "en" : "ar");
    expect(document.documentElement.dir).toBe(lang === "ar" ? "ltr" : "rtl");
  });

  it("someone with the language chosen and an incomplete profile lands on step 2", async () => {
    scenario("profile:incomplete");
    older.steps.language = "done";
    const router = open(dir);
    expect(await screen.findByRole("heading", { level: 1, name: say(firstlaunch.whoTitle) })).toBeInTheDocument();
    expect(where(router)).toBe(paths.welcome("profile"));
    expect(screen.getByRole("button", { name: say(firstlaunch.back) })).toBeInTheDocument();
  });

  it("someone upgrading (language and AI passed, profile incomplete) sees step 2 only, and its Next ends", async () => {
    scenario("profile:incomplete");
    older.steps = { ...older.steps, language: "done", ai: "done" };
    const router = open(dir, paths.welcome("ai")); // the gate pins someone upgrading to step 2, whatever the address
    expect(await screen.findByRole("heading", { level: 1, name: say(firstlaunch.whoTitle) })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: say(firstlaunch.back) })).toBeNull();
    for (const pair of [engineer.first_name, engineer.last_name, engineer.position, engineer.company])
      await userEvent.type(await screen.findByRole("textbox", { name: say(pair) }), "مهندس"); // the choices are known
    expect(where(router)).toBe(paths.welcome("profile"));
    expect(plain(document.body.textContent)).not.toContain(stepOf(2));
    await userEvent.click(screen.getByRole("button", { name: say(firstlaunch.next) }));
    await waitFor(() => expect(where(router)).toBe(paths.home));
    expect(screen.queryByRole("heading", { level: 1, name: say(firstlaunch.aiTitle) })).toBeNull();
    expect(older.calls.some((call) => call.startsWith("PUT /setup/ai"))).toBe(false);
    expect(older.steps.ai).toBe("done");
  });

  it("with a complete profile it opens on Connect AI, and ends there", async () => {
    older.steps.language = "done";
    const router = open(dir);
    expect(await screen.findByRole("heading", { level: 1, name: say(firstlaunch.aiTitle) })).toBeInTheDocument();
    expect(where(router)).toBe(paths.welcome("ai"));
    expect(plain(document.body.textContent)).toContain(stepOf(3));
    await userEvent.click(screen.getByRole("button", { name: say(firstlaunch.later) }));
    await waitFor(() => expect(where(router)).toBe(paths.home));
  });

  it("the setup strip runs under every step", async () => {
    scenario("setup:downloading");
    open(dir);
    await screen.findByRole("heading", { level: 1, name: say(firstlaunch.languageTitle) });
    expect(await screen.findByRole("progressbar")).toBeInTheDocument();
  });
});
