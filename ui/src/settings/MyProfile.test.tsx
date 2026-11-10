import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { toast } from "sonner";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { client } from "@/api/client";
import { server, startFakeCore } from "@/api/fakeCore";
import { DIRS, resetPage, stubBrowser } from "@/design/test/harness";
import { older, serveFirstLaunch } from "@/firstlaunch/fakeCoreFirstLaunch";
import { engineer } from "@/texts/engineer";
import { firstlaunch } from "@/texts/firstlaunch";
import { settings as texts } from "@/texts/settings";
import { text } from "@/texts/useText";
import { kept, serveSettings } from "./fakeCoreSettings";
import { openSettings } from "./test-open";

startFakeCore();
serveFirstLaunch();
serveSettings();
beforeEach(stubBrowser);
afterEach(() => {
  toast.dismiss();
  resetPage();
});

const plain = (value: string | null | undefined) => (value ?? "").replace(/[⁦⁨⁩]/g, "");

describe.each(DIRS)("Settings, My profile (%s)", (dir) => {
  const lang = dir === "rtl" ? "ar" : "en";
  const say = (pair: { en: string; ar: string }, vars?: Record<string, string>) => text(pair, lang, vars);

  it("a refusal the core gives for one field shows on that field", async () => {
    const words = { en: "Write the company as it is registered (sample).", ar: "اكتب اسم الشركة زي ما هو متسجل (عينة)." };
    server.use(http.put("*/api/engineer/profile", () => HttpResponse.json({ error: words, field: "company" }, { status: 422 })));
    openSettings(dir, "me");
    const company = await screen.findByLabelText(say(engineer.company));
    await userEvent.type(company, " X");
    await screen.findByText(say(words));
    expect(company).toHaveAttribute("aria-invalid", "true");
  });

  it("a rewritten lesson is saved when the engineer leaves its box", async () => {
    openSettings(dir, "me");
    const lessons = await screen.findByRole("region", { name: say(texts.lessons) });
    const box = within(lessons).getAllByRole("textbox")[0]!;
    await userEvent.clear(box);
    await userEvent.type(box, "Sample lesson, rewritten");
    await userEvent.tab();
    await waitFor(async () => {
      const { data } = await client.GET("/engineer/lessons");
      expect(data!.lessons.map((lesson) => lesson.text)).toContain("Sample lesson, rewritten");
    });
  });

  it("the QS Mind account: signed in, it says who, and Sign out signs out", async () => {
    older.account = { state: "signed_in", email: "engineer@example.com", name: null };
    openSettings(dir, "me");
    const account = await screen.findByRole("region", { name: say(texts.account) });
    await waitFor(() => expect(plain(account.textContent)).toContain(plain(say(firstlaunch.signedIn, { email: "engineer@example.com" }))));
    await userEvent.click(within(account).getByRole("button", { name: say(texts.signOut) }));
    await within(account).findByRole("button", { name: say(texts.signIn) });
    expect(kept.calls).toContain("DELETE /account");
  });

  it("the QS Mind account: signed out, Sign in waits for the browser and can be cancelled", async () => {
    openSettings(dir, "me");
    const account = await screen.findByRole("region", { name: say(texts.account) });
    await userEvent.click(await within(account).findByRole("button", { name: say(texts.signIn) }));
    await within(account).findByText(say(firstlaunch.signingIn));
    expect(older.calls.some((call) => call.startsWith("POST /account/sign-in"))).toBe(true);
    await userEvent.click(within(account).getByRole("button", { name: say(firstlaunch.cancel) }));
    await within(account).findByRole("button", { name: say(texts.signIn) });
    expect(older.calls.some((call) => call.startsWith("POST /account/cancel"))).toBe(true);
  });

  it("the QS Mind account: a sign-in that ends in the browser shows who is signed in", async () => {
    openSettings(dir, "me");
    const account = await screen.findByRole("region", { name: say(texts.account) });
    await userEvent.click(await within(account).findByRole("button", { name: say(texts.signIn) }));
    await within(account).findByText(say(firstlaunch.signingIn));
    // The fake core answers the next GET /account with the finished sign-in; only the screen's own asking reaches it.
    await within(account).findByRole("button", { name: say(texts.signOut) }, { timeout: 3000 });
    expect(plain(account.textContent)).toContain(plain(say(firstlaunch.signedIn, { email: "engineer@example.com" })));
  });
});
