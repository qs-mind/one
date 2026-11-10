import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { toast } from "sonner";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { startFakeCore } from "@/api/fakeCore";
import { DIRS, resetPage, stubBrowser } from "@/design/test/harness";
import { older, serveFirstLaunch } from "@/firstlaunch2/fakeCoreFirstLaunch";
import { common } from "@/texts/common";
import { firstlaunch } from "@/texts/firstlaunch";
import { settings as texts } from "@/texts/settings";
import { text } from "@/texts/useText";
import { kept, serveSettings } from "./fakeCoreSettings";
import { openSettings } from "./test-open";

startFakeCore();
serveFirstLaunch();
serveSettings();
beforeEach(() => {
  stubBrowser();
  older.consent = { at: "2026-11-01T09:00:00.000000+00:00", text_version: 3 };
});
afterEach(() => {
  toast.dismiss(); // an Undo notice stays until dismissed
  resetPage();
});

const plain = (value: string | null | undefined) => (value ?? "").replace(/[⁦⁨⁩]/g, "");

describe.each(DIRS)("Settings, AI (%s)", (dir) => {
  const lang = dir === "rtl" ? "ar" : "en";
  const say = (pair: { en: string; ar: string }, vars?: Record<string, string>) => text(pair, lang, vars);

  it("is laid out as the mockup: the key box, the providers, the models, on this computer only", async () => {
    openSettings(dir, "ai");
    const providers = await screen.findByRole("region", { name: say(texts.providers) });
    expect(within(providers).getByText("Claude (sample)")).toBeInTheDocument();
    expect(within(providers).getByText(say(texts.works))).toBeInTheDocument();
    const models = await screen.findByRole("radiogroup", { name: say({ en: "Models", ar: "الموديلات" }) });
    expect(within(models).getAllByRole("radio")).toHaveLength(2);
    expect(screen.getByRole("checkbox", { name: new RegExp(say({ en: "On this computer only", ar: "على الجهاز ده بس" })) })).not.toBeChecked();
    expect(screen.getByLabelText(say(firstlaunch.keyLabel))).toBeEnabled();
  });

  it("the key box waits for the AI consent", async () => {
    older.consent = { at: null, text_version: 3 };
    openSettings(dir, "ai");
    await screen.findByText(say(texts.keyLocked));
    expect(screen.getByLabelText(say(firstlaunch.keyLabel))).toBeDisabled();
  });

  it("a pasted key connects at once and is never shown back", async () => {
    openSettings(dir, "ai");
    const box = await screen.findByLabelText(say(firstlaunch.keyLabel));
    await waitFor(() => expect(box).toBeEnabled());
    await userEvent.click(box);
    await userEvent.paste("sk-ant-sample-key");
    await waitFor(() => expect(plain(document.body.textContent)).toContain(plain(say(firstlaunch.keyWorks, { provider: "Anthropic" }))));
    expect(document.body.textContent).not.toContain("sk-ant-sample-key");
  });

  it("Disconnect takes the provider out with Undo in a notice", async () => {
    openSettings(dir, "ai");
    const providers = await screen.findByRole("region", { name: say(texts.providers) });
    const box = screen.getByLabelText(say(firstlaunch.keyLabel));
    await waitFor(() => expect(box).toBeEnabled());
    await userEvent.click(box);
    await userEvent.paste("sk-ant-sample-key"); // the fake core links it, so it can be disconnected
    await waitFor(() => expect(plain(document.body.textContent)).toContain(plain(say(firstlaunch.keyWorks, { provider: "Anthropic" }))));
    kept.ai.connectors = []; // what GET /settings/ai answers once the link is out
    await userEvent.click(within(providers).getByRole("button", { name: say(texts.disconnect) }));
    await waitFor(() => expect(plain(document.body.textContent)).toContain(plain(say(texts.disconnected, { name: "Claude (sample)" }))));
    expect(screen.getByRole("button", { name: say(common.undo) })).toBeInTheDocument();
    await waitFor(() => expect(within(providers).getByText(say(texts.noProvider))).toBeInTheDocument());
  });

  it("choosing my own models shows a model for each role, saved when one is chosen", async () => {
    openSettings(dir, "ai");
    const models = await screen.findByRole("radiogroup", { name: say({ en: "Models", ar: "الموديلات" }) });
    await userEvent.click(within(models).getByRole("radio", { name: say({ en: "I choose a model for each role myself", ar: "أنا أختار موديل لكل دور" }) }));
    const roles = await screen.findByRole("region", { name: say(texts.rolesTitle) });
    expect(within(roles).getAllByRole("combobox")).toHaveLength(4);
    await userEvent.click(within(roles).getByRole("combobox", { name: say(texts.role_checker) }));
    await userEvent.click(await screen.findByRole("option", { name: /Claude small/ }));
    await waitFor(() => expect(kept.calls).toContain('PUT /settings/ai/roles {"checker":{"connector":"anthropic","model":"claude-sample-small"}}'));
  });

  it("the web search key is kept on leaving the box and says what ONE searches with", async () => {
    openSettings(dir, "ai");
    const search = await screen.findByLabelText(say(texts.searchKey));
    await screen.findByText(say(texts.searchNone));
    await userEvent.type(search, "search-sample-key");
    await userEvent.tab();
    await screen.findByText(say(texts.searchKept));
    expect(search).toHaveValue("");
  });
});
