import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { listening, publish, startFakeCore } from "@/api/fakeCore";
import type { Schemas } from "@/api/client";
import { DIRS, resetPage, stubBrowser } from "@/design/test/harness";
import { getThemeSetting } from "@/design/theme";
import { serveFirstLaunch } from "@/firstlaunch2/fakeCoreFirstLaunch";
import { getLang } from "@/texts/language";
import { settings as texts } from "@/texts/settings";
import { text } from "@/texts/useText";
import { serveSettings } from "./fakeCoreSettings";
import { SECTIONS } from "./Settings";
import { openSettings } from "./test-open";

startFakeCore();
serveFirstLaunch();
serveSettings();
beforeEach(stubBrowser);
afterEach(() => {
  resetPage();
  document.documentElement.style.fontSize = "";
});

const plain = (value: string | null | undefined) => (value ?? "").replace(/[⁦⁨⁩]/g, "");

describe.each(DIRS)("Settings (%s)", (dir) => {
  const lang = dir === "rtl" ? "ar" : "en";
  const say = (pair: { en: string; ar: string }, vars?: Record<string, string>) => text(pair, lang, vars);
  const pick = (pair: { en: string; ar: string }) => pair[lang];

  it("lists the eight sections and marks the open one; each opens its place", async () => {
    const router = openSettings(dir, "caps");
    const nav = screen.getByRole("navigation", { name: say(texts.sections) });
    const links = within(nav).getAllByRole("link");
    expect(links.map((link) => link.textContent)).toEqual(SECTIONS.map((id) => say(texts[id])));
    expect(within(nav).getByRole("link", { current: "page" })).toHaveTextContent(say(texts.caps));
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(say(texts.caps));
    await userEvent.click(within(nav).getByRole("link", { name: say(texts.look) }));
    expect(router.state.location.pathname).toBe("/settings/look");
    expect(document.querySelector("[data-place=settings]")).toHaveAttribute("data-section", "look");
  });

  it("an unknown section opens the first", async () => {
    const router = openSettings(dir, "nowhere");
    await waitFor(() => expect(router.state.location.pathname).toBe(`/settings/${SECTIONS[0]}`));
  });

  it("a money setting shows its recommended value, refuses a value that is not exact, and puts the recommended back", async () => {
    openSettings(dir, "caps");
    const month = await screen.findByLabelText(say({ en: "One month", ar: "الشهر" }));
    expect(month).toHaveValue("50");
    expect(plain(document.body.textContent)).toContain(plain(say(texts.recommended, { value: "150 USD" })));
    await userEvent.clear(month);
    await userEvent.type(month, "abc{Enter}");
    await waitFor(() => expect(plain(document.body.textContent)).toContain(plain(say(texts.example, { example: "50" }))));
    expect(month).toHaveAttribute("aria-invalid", "true");
    const putBack = { name: `${say(texts.putBack)}: ${say({ en: "One month", ar: "الشهر" })}` };
    await userEvent.click(screen.getByRole("button", putBack));
    await waitFor(() => expect(month).toHaveValue("150"));
    expect(screen.queryByRole("button", putBack)).toBeNull(); // at its recommended value now
  });

  it("a typed amount saves when the engineer leaves the box; nothing is sent when it did not change", async () => {
    openSettings(dir, "caps");
    const brief = await screen.findByLabelText(say({ en: "One piece of work", ar: "الشغلانة الواحدة" }));
    await userEvent.click(brief);
    await userEvent.tab();
    expect(screen.queryByText(say(texts.saving))).toBeNull();
    await userEvent.clear(brief);
    await userEvent.type(brief, "5");
    await userEvent.tab();
    await screen.findByText(plain(say(texts.saved)), { exact: false });
    expect(screen.getByRole("button", { name: `${say(texts.putBack)}: ${say({ en: "One piece of work", ar: "الشغلانة الواحدة" })}` })).toBeInTheDocument();
  });

  it("a toggle saves on change and says its recommended value", async () => {
    openSettings(dir, "privacy");
    const usage = await screen.findByRole("checkbox", { name: new RegExp(pick({ en: "Usage Stats", ar: "إحصاءات الاستخدام" })) });
    expect(usage).not.toBeChecked();
    expect(plain(document.body.textContent)).toContain(plain(say(texts.recommended, { value: say(texts.off) })));
    await userEvent.click(usage);
    await waitFor(() => expect(usage).toBeChecked());
    await screen.findByText(say(texts.saved));
  });

  it("a choice is a group of options with the recommended one marked; choosing the language turns the page", async () => {
    openSettings(dir, "look");
    const theme = await screen.findByRole("radiogroup", { name: say({ en: "Theme", ar: "المظهر" }) });
    const options = within(theme).getAllByRole("radio");
    expect(options).toHaveLength(3);
    expect(within(theme).getByText(say(texts.recommendedChoice))).toBeInTheDocument();
    await userEvent.click(within(theme).getByRole("radio", { name: say({ en: "Dark", ar: "غامق" }) }));
    await waitFor(() => expect(getThemeSetting()).toBe("dark"));
    const language = screen.getByRole("radiogroup", { name: say({ en: "Language", ar: "اللغة" }) });
    await userEvent.click(within(language).getByRole("radio", { name: /English/ }));
    await waitFor(() => expect(getLang()).toBe("en"));
    await userEvent.click(within(language).getByRole("radio", { name: /العربية/ }));
    await waitFor(() => expect(getLang()).toBe("ar"));
  });

  it("a setting the Lead changes by talking shows at once", async () => {
    openSettings(dir, "caps");
    const day = await screen.findByLabelText(say({ en: "One day", ar: "اليوم" }));
    await waitFor(() => expect(listening("general")).toBeGreaterThan(0));
    const setting = { key: "caps.day_usd", section: "caps", control: "money", value: "10", recommended: "15", currency: "USD", at_recommended: false,
      title: { en: "One day", ar: "اليوم" }, help: { en: "Sample.", ar: "عينة." } } satisfies Schemas["MoneySetting"];
    publish("general", { type: "setting", setting });
    await waitFor(() => expect(day).toHaveValue("10"));
  });
});
