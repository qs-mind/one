import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { setLanguage, texts } from "../i18n";
import { HealthGate } from "./CoreDown";

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
    expect(await screen.findByText("chat")).toBeInTheDocument();
  });

  it("when the core is down, says so in both languages with the path to core.log", async () => {
    const fetch = health(new TypeError("Failed to fetch"));
    render(<HealthGate logPath={logPath}>chat</HealthGate>);
    expect(await screen.findByText(texts.coreDown.ar)).toBeInTheDocument();
    expect(screen.getByText(texts.coreDown.en)).toBeInTheDocument();
    expect(screen.getByText(logPath)).toBeInTheDocument();
    expect(screen.queryByText("chat")).not.toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith("/api/health");
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
    await user.click(await screen.findByRole("button", { name: texts.retry.ar }));
    expect(await screen.findByText("chat")).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledTimes(2);
  });
});
