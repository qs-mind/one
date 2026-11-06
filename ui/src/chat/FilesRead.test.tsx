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
  it("shows each line in the page language, as ONE's own message", async () => {
    core({ routes: { "GET /api/chat/p1/messages": () => Response.json({ messages: [report] }) } });
    render(<App />);
    const line = await screen.findByText(lines[1]!.ar);
    expect(line).toHaveAttribute("dir", "auto");
    expect(line.closest('[role="status"]')).toHaveTextContent(lines[0]!.ar);
    setLanguage("en");
    expect(await screen.findByText(lines[1]!.en)).toBeInTheDocument();
  });
});
