import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { scenario, startFakeCore } from "@/api/fakeCore";
import { DIRS, renderIn, resetPage, stubBrowser } from "@/design/test/harness";
import { common } from "@/texts/common";
import { engineer } from "@/texts/engineer";
import { firstlaunch } from "@/texts/firstlaunch";
import { getLang } from "@/texts/language";
import { text } from "@/texts/useText";
import { older, serveFirstLaunch } from "./fakeCoreFirstLaunch";
import { Welcome } from "./Welcome";

startFakeCore();
serveFirstLaunch();
beforeEach(stubBrowser);
afterEach(resetPage);

const plain = (value: string | null | undefined) => (value ?? "").replace(/[⁦⁨⁩]/g, "");

describe.each(DIRS)("Welcome (%s)", (dir) => {
  const lang = dir === "rtl" ? "ar" : "en";
  const say = (pair: { en: string; ar: string }) => text(pair, lang);
  const stepOf = (step: number) => plain(text(common.stepOf, lang, { step, total: 3 }));

  it("a clean start opens on the language; Next says the choice and goes to who you are", async () => {
    scenario("profile:incomplete");
    renderIn(dir, <Welcome onDone={() => {}} />);
    expect(await screen.findByRole("heading", { level: 1, name: say(firstlaunch.languageTitle) })).toBeInTheDocument();
    expect(plain(document.body.textContent)).toContain(stepOf(1));
    expect(screen.getByRole("radio", { name: lang === "ar" ? "العربية" : "English" })).toBeChecked();
    await userEvent.click(screen.getByRole("button", { name: say(firstlaunch.next) }));
    expect(await screen.findByRole("heading", { level: 1, name: say(firstlaunch.whoTitle) })).toBeInTheDocument();
    expect(older.calls).toContain(`PUT /setup/language {"state":"done","lang":"${lang}"}`);
    expect(plain(document.body.textContent)).toContain(stepOf(2));
  });

  it("choosing the other language turns the page at once", async () => {
    renderIn(dir, <Welcome onDone={() => {}} />);
    const other = lang === "ar" ? "English" : "العربية";
    await userEvent.click(await screen.findByRole("radio", { name: other }));
    expect(getLang()).toBe(lang === "ar" ? "en" : "ar");
    expect(document.documentElement.dir).toBe(lang === "ar" ? "ltr" : "rtl");
  });

  it("someone with the language chosen and an incomplete profile lands on step 2", async () => {
    scenario("profile:incomplete");
    older.steps.language = "done";
    renderIn(dir, <Welcome onDone={() => {}} />);
    expect(await screen.findByRole("heading", { level: 1, name: say(firstlaunch.whoTitle) })).toBeInTheDocument();
  });

  it("someone upgrading (language and AI passed, profile incomplete) sees step 2 only, and its Next ends", async () => {
    scenario("profile:incomplete");
    older.steps = { ...older.steps, language: "done", ai: "done" };
    const onDone = vi.fn();
    renderIn(dir, <Welcome onDone={onDone} />);
    expect(await screen.findByRole("heading", { level: 1, name: say(firstlaunch.whoTitle) })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: say(firstlaunch.back) })).toBeNull();
    for (const pair of [engineer.first_name, engineer.last_name, engineer.position, engineer.company])
      await userEvent.type(await screen.findByRole("textbox", { name: say(pair) }), "مهندس"); // the choices are known
    await userEvent.click(screen.getByRole("button", { name: say(firstlaunch.next) }));
    await waitFor(() => expect(onDone).toHaveBeenCalledOnce());
    expect(screen.queryByRole("heading", { level: 1, name: say(firstlaunch.aiTitle) })).toBeNull();
    expect(older.calls.some((call) => call.startsWith("PUT /setup/ai"))).toBe(false);
    expect(older.steps.ai).toBe("done");
  });

  it("with a complete profile it opens on Connect AI, and ends there", async () => {
    older.steps.language = "done";
    const onDone = vi.fn();
    renderIn(dir, <Welcome onDone={onDone} />);
    expect(await screen.findByRole("heading", { level: 1, name: say(firstlaunch.aiTitle) })).toBeInTheDocument();
    expect(plain(document.body.textContent)).toContain(stepOf(3));
    await userEvent.click(screen.getByRole("button", { name: say(firstlaunch.later) }));
    await waitFor(() => expect(onDone).toHaveBeenCalledOnce());
  });

  it("the setup strip runs under every step", async () => {
    scenario("setup:downloading");
    renderIn(dir, <Welcome onDone={() => {}} />);
    await screen.findByRole("heading", { level: 1, name: say(firstlaunch.languageTitle) });
    expect(await screen.findByRole("progressbar")).toBeInTheDocument();
  });
});
