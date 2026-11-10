import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { client } from "@/api/client";
import { listening, scenario, startFakeCore } from "@/api/fakeCore";
import { DIRS, renderIn, resetPage, stubBrowser } from "@/design/test/harness";
import { firstlaunch } from "@/texts/firstlaunch";
import { text } from "@/texts/useText";
import { SetupStrip } from "./SetupStrip";

startFakeCore();
beforeEach(stubBrowser);
afterEach(resetPage);

// The words as the screen writes them, without the marks that keep an inserted value in one piece.
const plain = (value: string | null | undefined) => (value ?? "").replace(/[⁦⁨⁩]/g, "");

describe.each(DIRS)("SetupStrip (%s)", (dir) => {
  const lang = dir === "rtl" ? "ar" : "en";
  const say = (pair: { en: string; ar: string }, vars?: Record<string, string | number>) => plain(text(pair, lang, vars));

  it("shows nothing when every part is present", async () => {
    renderIn(dir, <SetupStrip />);
    await waitFor(() => expect(listening("general")).toBe(1));
    await act(async () => {}); // the first answer arrived
    expect(document.body.textContent).toBe("");
  });

  it("one bar for everything, naming the part being downloaded, with megabytes in words", async () => {
    scenario("setup:downloading");
    renderIn(dir, <SetupStrip />);
    const bar = await screen.findByRole("progressbar");
    // 90,400,000 of 173,390,915 bytes: present 28.4 MB, the search model 62 of 135.4 MB, the DWG reader queued.
    expect(bar).toHaveAttribute("aria-valuenow", "52");
    expect(plain(bar.getAttribute("aria-valuetext"))).toBe(say(firstlaunch.megabytes, { done: 90, total: 173 }));
    const part = lang === "ar" ? "موديل البحث" : "Search model";
    expect(plain(bar.textContent)).toContain(say(firstlaunch.setupGetting, { part })); // the bar's name too
  });

  it("offline, it says what waits for the internet", async () => {
    scenario("setup:offline");
    renderIn(dir, <SetupStrip />);
    await screen.findByRole("progressbar");
    const parts = new Intl.ListFormat(lang === "ar" ? "ar-u-nu-latn" : "en-GB", { type: "conjunction" }).format(
      lang === "ar" ? ["موديل البحث", "قارئ ملفات DWG"] : ["Search model", "DWG reader"],
    );
    expect(plain(document.body.textContent)).toContain(say(firstlaunch.setupOffline, { parts }));
  });

  it("a failed part says what will not work and why; Try again queues it", async () => {
    scenario("setup:failed");
    renderIn(dir, <SetupStrip />);
    const affects = lang === "ar" ? "قراءة رسومات DWG" : "Reading DWG drawings";
    await waitFor(() => expect(plain(document.body.textContent)).toContain(say(firstlaunch.notAvailable, { affects })));
    expect(document.body).toHaveTextContent(lang === "ar" ? "الملف نزل بايظ 3 مرات ورا بعض." : "The downloaded file was damaged three times in a row.");
    expect(screen.queryByRole("progressbar")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: text(firstlaunch.tryAgain, lang) }));
    await screen.findByRole("progressbar"); // queued again: it is downloaded with the rest
    expect(screen.queryByRole("button", { name: text(firstlaunch.tryAgain, lang) })).toBeNull();
    expect((await client.GET("/setup/parts")).data!.parts.find((part) => part.id === "dwg-reader")!.state).toBe("queued");
  });

  it("a part that cannot run here says why, with nothing to retry", async () => {
    scenario("setup:unavailable");
    renderIn(dir, <SetupStrip />);
    const affects = lang === "ar" ? "البحث بالمعنى في ملفات العطاء" : "Search by meaning in the tender files";
    await waitFor(() => expect(plain(document.body.textContent)).toContain(say(firstlaunch.notAvailable, { affects })));
    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.queryByRole("progressbar")).toBeNull();
  });

  it("moves with the setup event, no reload", async () => {
    renderIn(dir, <SetupStrip />);
    await waitFor(() => expect(listening("general")).toBe(1));
    await act(async () => {});
    expect(document.body.textContent).toBe("");
    act(() => scenario("setup:downloading"));
    expect(await screen.findByRole("progressbar")).toBeInTheDocument();
    act(() => scenario("setup"));
    await waitFor(() => expect(document.body.textContent).toBe(""));
  });
});
