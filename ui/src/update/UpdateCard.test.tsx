import type { Channel } from "@tauri-apps/api/core";
import { clearMocks, mockIPC } from "@tauri-apps/api/mocks";
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setLanguage, texts } from "../i18n";
import { EVERY_MS, UpdateCard, type UpdateInfo } from "./UpdateCard";

const found: UpdateInfo = { version: "0.1.1", notes_en: "Fixes for the import", notes_ar: "إصلاحات في الاستيراد" };

type Shell = { checks: number; installs: number };

/** The installed app, with the shell's two update commands answered by `install`. */
function installed(install: (progress: Channel<unknown>) => unknown, update: UpdateInfo | null = found): Shell {
  vi.stubEnv("PROD", true);
  const shell = { checks: 0, installs: 0 };
  mockIPC((cmd, args) => {
    if (cmd === "update_check") {
      shell.checks += 1;
      return update;
    }
    if (cmd === "update_install") {
      shell.installs += 1;
      return install((args as { onProgress: Channel<unknown> }).onProgress);
    }
  });
  return shell;
}

beforeEach(() => {
  setLanguage("ar");
  sessionStorage.clear();
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllEnvs();
  clearMocks();
});

describe("UpdateCard", () => {
  it("shows the notes in the page language and updates on request", async () => {
    const user = userEvent.setup();
    let progress: Channel<unknown> | undefined;
    const shell = installed((channel) => {
      progress = channel;
      return new Promise(() => undefined); // One starts again before the install answers
    });
    render(<UpdateCard />);
    expect(await screen.findByText("ONE 0.1.1 جاهز")).toBeInTheDocument();
    await user.click(screen.getByText(texts.updateNotes.ar));
    expect(screen.getByText(found.notes_ar)).toBeVisible();
    expect(screen.queryByText(found.notes_en)).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: texts.updateNow.ar }));
    expect(shell.installs).toBe(1);
    act(() => progress!.onmessage({ step: "download", percent: 40 }));
    expect(screen.getByRole("status")).toHaveTextContent("بينزّل: 40%");
    act(() => progress!.onmessage({ step: "prepare" }));
    expect(screen.getByRole("status")).toHaveTextContent(texts.updatePreparing.ar);
    act(() => progress!.onmessage({ step: "install" }));
    expect(screen.getByRole("status")).toHaveTextContent(texts.updateInstalling.ar);
    expect(screen.queryByRole("button", { name: texts.updateNow.ar })).not.toBeInTheDocument();
  });

  it("in English, the English notes", async () => {
    setLanguage("en");
    installed(() => undefined);
    render(<UpdateCard />);
    expect(await screen.findByText("ONE 0.1.1 is ready")).toBeInTheDocument();
    expect(screen.getByText(found.notes_en)).toBeInTheDocument(); // in the folded "What changed"
    expect(screen.queryByText(found.notes_ar)).not.toBeInTheDocument();
  });

  it("Later hides the card until the next check", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const shell = installed(() => undefined);
    render(<UpdateCard />);
    await user.click(await screen.findByRole("button", { name: texts.updateLater.ar }));
    expect(screen.queryByText("ONE 0.1.1 جاهز")).not.toBeInTheDocument();
    expect(shell.checks).toBe(1);

    await act(async () => void vi.advanceTimersByTime(EVERY_MS));
    expect(await screen.findByText("ONE 0.1.1 جاهز")).toBeInTheDocument();
    expect(shell.checks).toBe(2);
    expect(shell.installs).toBe(0); // never by itself
  });

  it("a failed update says so in plain words", async () => {
    const user = userEvent.setup();
    const reload = vi.fn();
    installed(() => Promise.reject("the download's signature did not match"));
    render(<UpdateCard reload={reload} />);
    await user.click(await screen.findByRole("button", { name: texts.updateNow.ar }));
    expect(await screen.findByRole("alert")).toHaveTextContent(texts.updateFailed.ar);
    expect(reload).not.toHaveBeenCalled(); // nothing had stopped: the projects are still open
    await user.click(screen.getByRole("button", { name: texts.close.ar }));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("a failed install after the projects closed reloads, then says so", async () => {
    const user = userEvent.setup();
    const reload = vi.fn();
    installed((progress) => {
      progress.onmessage({ step: "prepare" });
      progress.onmessage({ step: "install" });
      return Promise.reject("the installer failed");
    });
    const { unmount } = render(<UpdateCard reload={reload} />);
    await user.click(await screen.findByRole("button", { name: texts.updateNow.ar }));
    await vi.waitFor(() => expect(reload).toHaveBeenCalledOnce());
    unmount();

    installed(() => undefined, null); // after the reload: the same version, nothing new
    render(<UpdateCard />);
    expect(await screen.findByRole("alert")).toHaveTextContent(texts.updateFailed.ar);
  });

  it("outside the installed app it never asks the shell", async () => {
    const shell = installed(() => undefined);
    vi.unstubAllEnvs(); // a dev build
    vi.stubEnv("PROD", false);
    render(<UpdateCard />);
    await act(async () => undefined);
    expect(shell.checks).toBe(0);
    expect(screen.queryByRole("complementary")).not.toBeInTheDocument();
  });
});
