// The live team in the shell, with the real workspace: who is working now in the chat's head, the document they are
// on marked in the switcher, "waiting" in the top bar from the live store, one Announcer.
import { act, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { entry } from "../deliverables/fixtures";
import { fakeSources } from "../project/fake";
import type { AgentInfo } from "../project/types";
import { count, fill, setLanguage, texts } from "../i18n";
import { setCurrentProject } from "../records/project";
import { App } from "./App";
import { core, P1 } from "./testing";

const topBar = () => screen.getByRole("banner", { name: texts.topBar.ar });
const role = "مهندس التسعير est - عينة";

function agent(fields: Partial<AgentInfo> = {}): AgentInfo {
  return {
    id: "est", kind: "specialist", role: { en: "Estimator est (sample)", ar: role }, desk_id: null, model: "claude-sonnet-5",
    state: "working", line: null, brief_id: "b1", focus: { frame: "deliverable:dB", anchor: null }, at: "2026-11-05T09:00:00+00:00",
    ...fields,
  };
}

describe("the live team in the shell", () => {
  beforeEach(() => {
    setLanguage("ar");
    setCurrentProject(P1);
  });
  afterEach(() => setCurrentProject(undefined));

  it("an agent at work shows in the chat's head and by its document; waiting comes from the stream", async () => {
    core();
    const sources = fakeSources({
      files: [{ id: "f1", name: "مواصفات - عينة.pdf", status: "read", note: null, replaces: null }],
      deliverables: [entry({ id: "dB", title: "خطاب العطاء - عينة" })],
      status: { waiting: 1 },
    });
    render(<App sourcesFor={() => sources} />);
    expect(await within(topBar()).findByRole("button", { name: count("decisionsWaiting", 1) })).toBeInTheDocument();
    await screen.findByRole("heading", { level: 1 });
    act(() => {
      sources.emit({ type: "agent", agent: agent() });
      sources.emit({ type: "waiting", count: 3 });
    });
    const chat = screen.getByRole("complementary", { name: texts.projectChat.ar });
    expect(await within(chat).findByRole("button", { name: fill(texts.workingNow.ar, { role }) })).toBeInTheDocument();
    expect(await within(topBar()).findByRole("button", { name: count("decisionsWaiting", 3) })).toBeInTheDocument();
    expect(screen.getAllByRole("status").filter((el) => el.getAttribute("aria-live") === "polite").length).toBeGreaterThan(0);
    act(() => sources.emit({ type: "agent", agent: agent({ state: "waiting" }) }));
    await waitFor(
      () => expect(screen.getAllByRole("status").some((el) => el.textContent === fill(texts.announceWaiting.ar, { role }))).toBe(true),
      { timeout: 3000 }, // "est is working" was said just before: the next waits its 2 s
    );
  });
});
