// The look the engineer left (GET /settings) is put on the page before the first place shows (app/CoreDown.tsx).
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { client } from "@/api/client";
import { server, startFakeCore } from "@/api/fakeCore";
import { getThemeSetting } from "@/design/theme";
import { resetPage, stubBrowser } from "@/design/test/harness";
import { getLang, setLang } from "@/texts/language";
import { loadLook } from "./look";

startFakeCore();
beforeEach(stubBrowser);
afterEach(() => {
  resetPage();
  document.documentElement.style.fontSize = "";
});

describe("loadLook", () => {
  it("puts the saved language, theme and zoom on the page", async () => {
    const { data } = await client.GET("/settings");
    const saved = { "look.language": "en", "look.theme": "dark", "look.zoom": "1.1" } as Record<string, string>;
    const settings = data!.settings.map((it) => (it.key in saved ? { ...it, value: saved[it.key]! } : it));
    server.use(http.get("*/api/settings", () => HttpResponse.json({ settings })));
    setLang("ar");
    await loadLook();
    expect(getLang()).toBe("en");
    expect(getThemeSetting()).toBe("dark");
    expect(document.documentElement.style.fontSize).toBe("110%");
  });

  it("keeps the system's look when the core cannot answer", async () => {
    setLang("en");
    server.use(http.get("*/api/settings", () => HttpResponse.error()));
    await loadLook();
    expect(getLang()).toBe("en");
    expect(document.documentElement.style.fontSize).toBe("");
  });
});
