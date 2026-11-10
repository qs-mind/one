import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { toast } from "sonner";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { server, startFakeCore } from "@/api/fakeCore";
import { DIRS, resetPage, stubBrowser } from "@/design/test/harness";
import { older, serveFirstLaunch } from "@/firstlaunch2/fakeCoreFirstLaunch";
import { common } from "@/texts/common";
import { engineer } from "@/texts/engineer";
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
  Element.prototype.setPointerCapture ??= () => {}; // jsdom lacks it; the notice's button calls it on press
});
afterEach(() => {
  toast.dismiss(); // an Undo notice stays until dismissed
  resetPage();
});

const plain = (value: string | null | undefined) => (value ?? "").replace(/[⁦⁨⁩]/g, "");
const bodyText = () => plain(document.body.textContent);

describe.each(DIRS)("Settings sections (%s)", (dir) => {
  const lang = dir === "rtl" ? "ar" : "en";
  const say = (pair: { en: string; ar: string }, vars?: Record<string, string | number>) => text(pair, lang, vars);

  it("My profile shows the seven fields and saves a change as the engineer types", async () => {
    let saved: unknown;
    server.use(
      http.put("*/api/engineer/profile", async ({ request }) => {
        saved = await request.json();
        return HttpResponse.json({ ...(saved as object), complete: true });
      }),
    );
    openSettings(dir, "me");
    const company = await screen.findByLabelText(say(engineer.company));
    for (const field of ["first_name", "last_name", "position"] as const) expect(screen.getByLabelText(say(engineer[field]))).toBeInTheDocument();
    for (const field of ["org_type", "country", "currency"] as const)
      expect(screen.getByRole("combobox", { name: say(engineer[field]) })).toBeInTheDocument();
    await userEvent.clear(company);
    await userEvent.type(company, "Sample Contracting");
    await waitFor(() => expect(saved).toMatchObject({ company: "Sample Contracting" }));
    await screen.findByText(say(texts.saved));
  });

  it("My profile says a missing field in words, from the shared schema", async () => {
    openSettings(dir, "me");
    const first = await screen.findByLabelText(say(engineer.first_name));
    await userEvent.clear(first);
    await screen.findByText(say(engineer.missingText));
  });

  it("what the Lead QS learned: each lesson can be removed, with Undo", async () => {
    openSettings(dir, "me");
    const lessons = await screen.findByRole("region", { name: say(texts.lessons) });
    expect(within(lessons).getAllByRole("textbox")).toHaveLength(2);
    await userEvent.click(within(lessons).getAllByRole("button", { name: say(texts.remove) })[0]!);
    await waitFor(() => expect(within(lessons).getAllByRole("textbox")).toHaveLength(1));
    expect(bodyText()).toContain(say(texts.lessonRemoved));
    expect(screen.getByRole("button", { name: say(common.undo) })).toBeInTheDocument();
  });

  it("Team lists the members who stay, with their record", async () => {
    openSettings(dir, "team");
    await screen.findByText(say({ en: "Lead QS", ar: "Lead QS" }));
    expect(bodyText()).toContain(plain(say(texts.checks, { passed: 4, total: 5 })));
    expect(bodyText()).toContain(plain(say(texts.costUsd, { cost: "6.85" })));
    expect(bodyText()).toContain(say({ en: "Contracts QS (sample)", ar: "مهندس العقود - عينة" }));
  });

  it("Spending caps shows what is spent beside the caps", async () => {
    openSettings(dir, "caps");
    const spent = await screen.findByRole("region", { name: say(texts.spent) });
    expect(plain(spent.textContent)).toContain(plain(say(texts.spentMonth, { amount: "9.65" })));
  });

  it("Connectors: a connector goes off at once, and can be removed with Undo", async () => {
    openSettings(dir, "connectors");
    const row = await screen.findByRole("checkbox", { name: /drive-sample/ });
    expect(row).toBeChecked();
    await userEvent.click(row);
    await waitFor(() => expect(kept.calls).toContain('PUT /connectors/drive-sample/enabled {"enabled":false}'));
    await waitFor(() => expect(row).not.toBeChecked());
    await userEvent.click(screen.getByRole("button", { name: say(texts.remove) }));
    await screen.findByText(say(texts.noConnectors));
    await userEvent.click(screen.getByRole("button", { name: say(common.undo) }));
    await screen.findByRole("checkbox", { name: /drive-sample/ });
  });

  it("Backup: the folder is saved on leaving the box; Back up now runs one", async () => {
    openSettings(dir, "backup");
    const folder = await screen.findByLabelText(say(texts.folder));
    expect(folder).toHaveValue("/home/engineer/Backups");
    await userEvent.clear(folder);
    await userEvent.type(folder, "/home/engineer/Other");
    await userEvent.tab();
    await waitFor(() => expect(kept.calls).toContain('PUT /backup/folder {"path":"/home/engineer/Other"}'));
    await userEvent.click(screen.getByRole("button", { name: say(texts.backUpNow) }));
    await screen.findByText(say(texts.backedUp));
    expect(kept.calls).toContain("POST /backup/run");
  });

  it("Privacy: the consent can be given here, and Usage Stats is off until turned on", async () => {
    older.consent = { at: null, text_version: 3 };
    openSettings(dir, "privacy");
    await screen.findByText(say(texts.notAgreed));
    await userEvent.click(screen.getByRole("button", { name: say(firstlaunch.agree) }));
    await waitFor(() => expect(bodyText()).toContain(plain(say(texts.agreedOn, { date: "" })).replace(".", "").trim()));
    expect(older.calls).toContain('PUT /settings/ai-consent {"text_version":3}');
    expect(await screen.findByRole("checkbox", { name: /Usage Stats|إحصاءات الاستخدام/ })).not.toBeChecked();
  });
});
