import type { Channel } from "@tauri-apps/api/core";
import { clearMocks, mockIPC } from "@tauri-apps/api/mocks";
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setLanguage, texts } from "../i18n";
import { HealthGate, STARTING_MS } from "./CoreDown";

const logPath = "/tmp/qs-mind-one/core.log";

function health(...answers: (Response | Error)[]) {
  const fetch = vi.fn(async () => {
    const answer = answers.length > 1 ? answers.shift()! : answers[0]!;
    if (answer instanceof Error) throw answer;
    return answer;
  });
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

beforeEach(() => setLanguage("ar"));

describe("HealthGate", () => {
  it("shows the chat when the core answers", async () => {
    health(Response.json({ ok: true }));
    render(<HealthGate logPath={logPath}>chat</HealthGate>);
    expect(await screen.findByText("chat", {}, { timeout: 3000 })).toBeInTheDocument();
  });

  it("when the core is down, says so in both languages with the path to core.log", async () => {
    const fetch = health(new TypeError("Failed to fetch"));
    render(<HealthGate logPath={logPath}>chat</HealthGate>);
    expect(await screen.findByText(texts.coreDown.ar)).toBeInTheDocument();
    expect(screen.getByText(texts.coreDown.en)).toBeInTheDocument();
    expect(screen.getByText(logPath)).toBeInTheDocument();
    expect(screen.queryByText("chat")).not.toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith("/api/health", undefined);
  });

  it("a failing answer from the proxy counts as down", async () => {
    health(new Response("", { status: 502 }));
    render(<HealthGate logPath={logPath}>chat</HealthGate>);
    expect(await screen.findByText(texts.coreDown.en)).toBeInTheDocument();
  });

  it("Retry checks again and opens the chat once the core is up", async () => {
    const fetch = health(new TypeError("Failed to fetch"), Response.json({ ok: true }));
    const user = userEvent.setup();
    render(<HealthGate logPath={logPath}>chat</HealthGate>);
    // the start screen speaks the saved language, else the system's (jsdom's is English)
    await user.click(await screen.findByRole("button", { name: texts.retry.en }));
    expect(await screen.findByText("chat", {}, { timeout: 3000 })).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledTimes(2);
  });
});

// The installed app: the shell started the core, so it knows whether it is still starting and where its log is.
describe("HealthGate in the installed app", () => {
  const shellLog = "/home/x/.local/share/app.qsmind.one/logs/core.log";

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllEnvs();
    clearMocks();
  });

  function shell(states: string[]) {
    vi.stubEnv("PROD", true);
    const calls: string[] = [];
    mockIPC((cmd, args) => {
      calls.push(cmd);
      if (cmd === "core_log_path") return shellLog;
      if (cmd === "core_status") return { state: states.length > 1 ? states.shift() : states[0], log: shellLog };
      if (cmd === "core_fetch") {
        const ch = (args as { onEvent: Channel<unknown> }).onEvent;
        ch.onmessage({ event: "head", status: 200, headers: [["content-type", "application/json"]] });
        ch.onmessage(new TextEncoder().encode('{"ok":true}').buffer);
        ch.onmessage({ event: "end" });
      }
    });
    return calls;
  }

  it("shows the start screen while the core starts, then opens the chat", async () => {
    const calls = shell(["starting", "starting", "up"]);
    render(<HealthGate>chat</HealthGate>);
    expect(screen.getByText(texts.checking.en)).toBeInTheDocument();
    expect(await screen.findByText("chat", {}, { timeout: 3000 })).toBeInTheDocument();
    expect(calls.filter((cmd) => cmd === "core_status")).toHaveLength(3);
    expect(calls).toContain("core_fetch");
  });

  it("calls the core down after a minute of starting, with the log path from the shell", async () => {
    vi.useFakeTimers();
    const calls = shell(["starting"]);
    render(<HealthGate>chat</HealthGate>);
    await act(() => vi.advanceTimersByTimeAsync(STARTING_MS + 1000));
    expect(screen.getByText(texts.coreDown.en)).toBeInTheDocument();
    expect(screen.getByText(shellLog)).toBeInTheDocument();
    expect(calls).not.toContain("core_fetch");
  });
});
