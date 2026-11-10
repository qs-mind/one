import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { startFakeCore } from "@/api/fakeCore";
import { DIRS, resetPage, stubBrowser } from "@/design/test/harness";
import { serveFirstLaunch } from "@/firstlaunch2/fakeCoreFirstLaunch";
import { settings as texts } from "@/texts/settings";
import { text } from "@/texts/useText";
import { CODE, kept, serveSettings } from "./fakeCoreSettings";
import { openSettings } from "./test-open";

startFakeCore();
serveFirstLaunch();
serveSettings();
beforeEach(stubBrowser);
afterEach(resetPage);

const plain = (value: string | null | undefined) => (value ?? "").replace(/[⁦⁨⁩]/g, "");

describe.each(DIRS)("Settings, Backup (%s)", (dir) => {
  const lang = dir === "rtl" ? "ar" : "en";
  const say = (pair: { en: string; ar: string }, vars?: Record<string, string>) => text(pair, lang, vars);

  it("the recovery code shows once and is confirmed by its last group as it is typed", async () => {
    openSettings(dir, "backup");
    const key = await screen.findByRole("region", { name: say(texts.backupKey) });
    expect(plain(key.textContent)).toContain(`${say(texts.keyCodeSaved)}: ${say(texts.no)}`);
    await userEvent.click(within(key).getByRole("button", { name: say(texts.makeCode) }));
    expect(await within(key).findByRole("status", { name: say(texts.codeTitle) })).toHaveTextContent(CODE);
    const last = within(key).getByLabelText(say(texts.codeLastGroup));
    await userEvent.type(last, "AAAAA");
    await within(key).findByText(say({ en: "That is not its last group.", ar: "دي مش آخر مجموعة فيه." }));
    await userEvent.clear(last);
    await userEvent.type(last, CODE.slice(-5).toLowerCase());
    await waitFor(() => expect(plain(key.textContent)).toContain(`${say(texts.keyCodeSaved)}: ${say(texts.yes)}`));
    expect(key.textContent).not.toContain(CODE);
    expect(kept.calls).toContain(`POST /backup/recovery-code/confirm {"last_group":"${CODE.slice(-5)}"}`);
  });

  it("restoring: the tenders found in a folder come back, one with its own code", async () => {
    openSettings(dir, "backup");
    const restore = await screen.findByRole("region", { name: say(texts.restore) });
    await userEvent.type(within(restore).getByLabelText(say(texts.restoreFolder)), "/media/usb/Backups{Enter}");
    await within(restore).findByText("Tower sample");
    expect(kept.calls).toContain("GET /backup/found /media/usb/Backups");
    await userEvent.click(within(restore).getAllByRole("button", { name: say(texts.restoreIt) })[0]!); // the first needs nothing
    await within(restore).findByText(say(texts.restored, { name: "Tower sample" }), { exact: false });
    expect(kept.calls).toContain(`POST /backup/restore {"path":"/media/usb/Backups","project_id":"${"1".repeat(32)}"}`);
    expect(within(restore).getByText(say(texts.restoreNeedsProjectCode))).toBeInTheDocument();
    const code = within(restore).getByLabelText(say(texts.restoreCode));
    await userEvent.type(code, "WRONG-CODE{Enter}");
    await within(restore).findByText(say({ en: "That code does not open it.", ar: "الكود ده مش بيفتحه." }));
    expect(code).toHaveValue(""); // a code is not kept
    await userEvent.type(code, `${CODE}{Enter}`);
    await waitFor(() => expect(within(restore).getByText(say(texts.restoreNone))).toBeInTheDocument());
    expect(plain(restore.textContent)).toContain(plain(say(texts.restored, { name: "Hidden sample" })));
  });
});
