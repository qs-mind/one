// A Brief that failed keeps its line in its reply, with the fix, after later messages too (audit B7): the provider's
// reason in plain words, and Open AI settings.
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { setLanguage, texts } from "../i18n";
import { setCurrentProject } from "../records/project";
import { App } from "../shell/App";
import { core, reply, streamed } from "../shell/testing";

vi.mock("../workspace/Workspace", async () => ({ Workspace: (await import("../shell/testing")).WorkspaceStandIn, DocumentHead: () => null }));

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

describe("a stopped Brief's line", () => {
  it("says it stopped and what changed, never ending silently", async () => {
    const said = { en: "Stopped. Nothing was changed.", ar: "وقفت. ماتغيرش حاجة." };
    const stoppedRun = [
      { type: "start", messageId: "m0" },
      { type: "start-step" },
      { type: "data-status", id: "b1", data: { state: "stopped", step: said } },
      { type: "finish-step" },
      { type: "finish" },
    ];
    core({ routes: { "POST /api/chat": (init) => streamed(stoppedRun, init) } });
    const user = userEvent.setup();
    render(<App />);
    await user.type(await box(), "سعّر{enter}");
    expect(await screen.findByText(said.ar)).toBeInTheDocument();
    setLanguage("en");
    expect(await screen.findByText(said.en)).toBeInTheDocument();
  });
});

// What web_search sends when ONE has no search at all (core: tools/web._no_search; audit B8).
const noSearch = {
  en: "No web search is set up. Add a search key, connect an AI that can search (Claude), or subscribe to QS Mind.",
  ar: "مفيش بحث على الويب متظبط. ضيف مفتاح بحث، أو وصّل ذكاء اصطناعي بيعرف يدوّر (Claude)، أو اشترك في QS Mind.",
};

describe("the no-search notice", () => {
  it("says search is not set up, with the way to the search setting in AI settings", async () => {
    const notice = { type: "data-notice", id: "b1-no-search", data: { text: noSearch, fix: "search" } };
    core({ routes: { "POST /api/chat": (init) => streamed([...reply.slice(0, 2), notice, ...reply.slice(2)], init) } });
    const user = userEvent.setup();
    render(<App />);
    await user.type(await box(), "دوّر على سعر الحديد النهارده{enter}");
    const line = (await screen.findByText(noSearch.ar)).closest("[role=status]") as HTMLElement;
    await user.click(within(line).getByRole("button", { name: texts.setUpSearch.ar }));
    expect(await screen.findByRole("heading", { name: texts.searchTitle.ar })).toBeInTheDocument();
  });
});
