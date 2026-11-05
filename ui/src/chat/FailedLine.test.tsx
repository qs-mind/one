// A Brief that failed keeps its line in its reply, with the fix, after later messages too (audit B7): the provider's
// reason in plain words, and Open AI settings.
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { setLanguage, texts } from "../i18n";
import { setCurrentProject } from "../records/project";
import { App } from "../shell/App";
import { core, reply, streamed } from "../shell/testing";

vi.mock("../canvas/Canvas", async () => ({ Canvas: (await import("../shell/testing")).CanvasStandIn }));

// What the core sends for Google's 404 on a retired model (core: connectors.provider_reason).
const gone = {
  en: "Google says gemini-2.5-flash-lite is no longer available; try gemini-3.5-flash-lite. Pick it in AI settings.",
  ar: "Google بيقول إن gemini-2.5-flash-lite مبقاش متاح؛ جرّب gemini-3.5-flash-lite. اختاره من إعدادات الذكاء الاصطناعي.",
};
const failedRun = [
  { type: "start", messageId: "m0" },
  { type: "start-step" },
  { type: "data-status", id: "b1", data: { state: "failed", step: gone, fix: "ai" } },
  { type: "error", errorText: JSON.stringify({ ...gone, fix: "ai" }) },
];
const box = () => screen.findByRole("textbox", { name: texts.message.ar });

beforeEach(() => {
  setLanguage("ar");
  setCurrentProject(undefined);
  vi.stubGlobal("matchMedia", (query: string) => ({ matches: false, media: query, addEventListener() {}, removeEventListener() {} }));
});

describe("a failed Brief's line", () => {
  it("says the reason once, with Open AI settings, and stays after the next message", async () => {
    let calls = 0;
    core({ routes: { "POST /api/chat": (init) => streamed(++calls === 1 ? failedRun : reply, init) } });
    const user = userEvent.setup();
    render(<App />);
    await user.type(await box(), "سعّر{enter}");
    const line = await screen.findByText(gone.ar);
    expect(screen.getAllByText(gone.ar)).toHaveLength(1); // the reply's line, not a second error line under it
    const said = line.closest("[role=alert]") as HTMLElement;
    expect(within(said).getByRole("button", { name: texts.openAiSettings.ar })).toBeInTheDocument();
    await user.type(await box(), "تاني{enter}");
    expect(await screen.findByText(/مرحبا/)).toBeInTheDocument();
    expect(screen.getByText(gone.ar)).toBeInTheDocument();
  });
});
