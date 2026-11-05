// The work log in the chat: once the running Brief sends it, Thinking shimmers once, at the head of its steps; when
// the Brief ends it settles to the real time and step count.
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { setLanguage, texts } from "../i18n";
import { setCurrentProject } from "../records/project";
import { App } from "../shell/App";
import { core, reply, running, streamed } from "../shell/testing";

vi.mock("../canvas/Canvas", async () => ({ Canvas: (await import("../shell/testing")).CanvasStandIn }));

const lead = { en: "Lead QS", ar: "كبير مهندسي الكميات" };
const read = { en: "reading A-101.dwg", ar: "بيقرا A-101.dwg" };
const T0 = "2026-11-05T08:00:00.000Z";
const log = (ended: string | null, until: string | null) => ({
  type: "data-worklog",
  id: "b1",
  data: { started: T0, ended, steps: [{ agent: lead, text: read, at: T0, until }] },
});
const box = () => screen.findByRole("textbox", { name: texts.message.ar });

beforeEach(() => {
  setLanguage("ar");
  setCurrentProject(undefined);
  vi.stubGlobal("matchMedia", (query: string) => ({ matches: false, media: query, addEventListener() {}, removeEventListener() {} }));
});

describe("the work log in the chat", () => {
  it("shows Thinking once, at the head of the running steps", async () => {
    core({ routes: { "POST /api/chat": (init) => streamed([...reply.slice(0, 2), running, log(null, null)], init, false) } });
    const user = userEvent.setup();
    render(<App />);
    await user.type(await box(), "سعّر{enter}");
    expect(await screen.findByText(read.ar)).toBeInTheDocument();
    await waitFor(() => expect(screen.getAllByText(texts.thinking.ar)).toHaveLength(1));
  });

  it("settles to the real time and step count when the Brief ends", async () => {
    const done = { type: "data-status", id: "b1", data: { state: "done", step: null } };
    const end = "2026-11-05T08:00:42.000Z";
    core({ routes: { "POST /api/chat": (init) => streamed([...reply.slice(0, 2), log(end, end), done, ...reply.slice(2)], init) } });
    const user = userEvent.setup();
    render(<App />);
    await user.type(await box(), "سعّر{enter}");
    expect(await screen.findByRole("button", { name: "اشتغل 42 ثانية · خطوة واحدة" })).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText(texts.thinking.ar)).toBeNull();
  });

  it("an Arabic Brief's log reads in English once the page is English: what is stored in both shows in the page's (tender day)", async () => {
    const done = { type: "data-status", id: "b1", data: { state: "done", step: null } };
    const said = { type: "data-progress", id: "p1", data: { agent: lead, text: read, lang: "ar" } };
    const end = "2026-11-05T08:00:42.000Z";
    core({ routes: { "POST /api/chat": (init) => streamed([...reply.slice(0, 2), said, log(end, end), done, ...reply.slice(2)], init) } });
    const user = userEvent.setup();
    render(<App />);
    await user.type(await box(), "سعّر{enter}");
    await screen.findByRole("button", { name: "اشتغل 42 ثانية · خطوة واحدة" });
    act(() => setLanguage("en"));
    const folded = await screen.findByRole("button", { name: /42/ });
    expect(folded.textContent).not.toMatch(/[؀-ۿ]/);
    expect(folded.closest("[lang]")).toHaveAttribute("lang", "en");
  });
});
