// C3: the import summary says "reading…" only while the Lead QS's Brief reads the folder. When that Brief waits on
// the "I understood this" card, or has ended, it says so and folds small, so it never covers the card.
import { act, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setLanguage, texts } from "../i18n";
import { setCurrentProject } from "../records/project";
import { ACTIVITY_POLL } from "../shell/chatActivity";
import { importFolders, resetImports } from "./importer";
import { ImportReports } from "./ImportReport";

let activity: { chat_id: string; brief_id: string; state: string; name: string | null }[] = [];

function mockCore() {
  const fetch = vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = String(input).replace(/^\/api/, "").split("?")[0]!;
    const key = `${init.method ?? "GET"} ${url}`;
    if (key === "POST /projects") return Response.json({ id: "p1", name: "مناقصة", created_at: "2026-11-05T08:00:00Z", open: true }, { status: 201 });
    if (key === "POST /projects/p1/files") return Response.json({ status: "read" }, { status: 201 });
    if (key === "POST /projects/p1/understand") return Response.json({ brief_id: "b1" }, { status: 202 });
    if (key === "GET /briefs/activity") return Response.json({ chats: activity });
    return new Response(null, { status: 204 });
  });
  vi.stubGlobal("fetch", fetch);
}

const file = (name: string, path: string) => {
  const f = new File(["x"], name);
  Object.defineProperty(f, "webkitRelativePath", { value: path });
  return f;
};

beforeEach(() => {
  setLanguage("en");
  setCurrentProject(undefined);
  activity = [];
  ACTIVITY_POLL.ms = 20;
  mockCore();
});
afterEach(() => {
  resetImports();
  ACTIVITY_POLL.ms = 2000;
});

describe("the import summary", () => {
  it("says nothing once every file came in: the files list and the chat say the rest (Kareem, 8 Nov)", async () => {
    activity = [{ chat_id: "p1", brief_id: "b1", state: "working", name: "مناقصة - عينة" }];
    render(<ImportReports />);
    await act(() => importFolders([file("عقد.pdf", "مناقصة/عقد.pdf")], { old: false }));
    await waitFor(() => expect(document.querySelector("[data-import-report]")).toBeNull());
    expect(screen.queryByText(texts.importReportTitle.en)).toBeNull();
    expect(screen.queryByText(texts.importUnderstanding.en)).toBeNull();
  });
});
