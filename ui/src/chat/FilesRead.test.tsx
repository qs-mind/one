// What ONE found in a drop of files, in the project chat without being asked (core: records/report.py; real walk:
// dropping the tender files started nothing). Each line comes from the core's own reading, in both languages.
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { setLanguage } from "../i18n";
import { setCurrentProject } from "../records/project";
import { App } from "../shell/App";
import { core, P1 } from "../shell/testing";

vi.mock("../workspace/Workspace", async () => ({ Workspace: (await import("../shell/testing")).WorkspaceStandIn, DocumentHead: () => null }));

const lines = [
  { en: "ONE read 1 file:", ar: "ONE قرا ملف واحد:" },
  { en: "Sheet «BOQ»: 3 items in 2 sections (rows 2–7).", ar: "شيت «BOQ»: 3 بنود في قسمين (الصفوف 2–7)." },
];
const report = { id: "files-r1", role: "assistant", parts: [{ type: "data-files_read", id: "r1", data: { lines } }] };

beforeEach(() => {
  setLanguage("ar");
  setCurrentProject(P1);
  vi.stubGlobal("matchMedia", (query: string) => ({ matches: false, media: query, addEventListener() {}, removeEventListener() {} }));
});

describe("the report of a drop", () => {
  it("uses the Brief language from progress for an Arabic reply, even on an English page", async () => {
    setLanguage("en");
    const message = { id: "reply-sample", role: "assistant", parts: [
      { type: "data-progress", id: "sample", data: { agent: { en: "Lead QS", ar: "كبير مهندسي الكميات" }, text: { en: "Read", ar: "قرا" }, lang: "ar" } },
      { type: "text", text: "BOQ قرا الملف." },
    ] };
    core({ routes: { "GET /api/chat/p1/messages": () => Response.json({ messages: [message] }) } });
    render(<App />);
    const paragraph = await screen.findByText((_, el) => el?.tagName === "P" && el.textContent === "BOQ قرا الملف.");
    expect(paragraph).toHaveAttribute("dir", "rtl");
  });

  it("shows its first line, the rest under Details, in the page language, as ONE's own message", async () => {
    core({ routes: { "GET /api/chat/p1/messages": () => Response.json({ messages: [report] }) } });
    render(<App />);
    const line = await screen.findByText((_, el) => el?.tagName === "P" && el.textContent === lines[1]!.ar);
    expect(line).toHaveAttribute("dir", "rtl");
    expect(line.closest("[data-details]")).not.toBeNull(); // folded
    expect(screen.getAllByRole("status").some((el) => el.textContent?.includes(lines[0]!.ar) && !el.closest("[data-details]"))).toBe(true); // the summary, in sight
    setLanguage("en");
    expect(await screen.findByText((_, el) => el?.tagName === "P" && el.textContent === lines[1]!.en)).toBeInTheDocument();
  });
});
