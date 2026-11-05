// The live team in the shell, with the real canvas: cursors mounted in it, the team now and "Waiting for you" in
// the top bar from the live store, one Announcer.
import { act, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { fakeSources } from "../canvas/fake";
import { agent, layout, paneSize, restorePane } from "../canvas/live/testing";
import { fill, setLanguage, texts } from "../i18n";
import { setCurrentProject } from "../records/project";
import { App } from "./App";
import { core, P1 } from "./testing";

const topBar = () => screen.getByRole("banner", { name: texts.topBar.ar });

describe("the live team in the shell", () => {
  beforeEach(() => {
    paneSize();
    setLanguage("ar");
    setCurrentProject(P1);
  });
  afterEach(() => {
    restorePane();
    setCurrentProject(undefined);
  });

  it("an agent at work shows its cursor on the canvas and in the top bar; waiting comes from the stream", async () => {
    core();
    const sources = fakeSources({ layout, status: { waiting: 1 } });
    render(<App sourcesFor={() => sources} />);
    expect(await within(topBar()).findByRole("button", { name: fill(texts.waitingForYou.ar, { n: 1 }) })).toBeInTheDocument();
    await screen.findByRole("group", { name: texts.projectTeam.ar });
    act(() => {
      sources.emit({ type: "agent", agent: agent("est", { focus: { frame: "team:core", anchor: null } }) });
      sources.emit({ type: "waiting", count: 3 });
    });
    expect(await screen.findByTestId("cursor-est")).toHaveTextContent("مهندس التسعير est - عينة");
    expect(await within(topBar()).findByRole("button", { name: fill(texts.teamNowCount.ar, { n: 1 }) })).toBeInTheDocument();
    expect(await within(topBar()).findByRole("button", { name: fill(texts.waitingForYou.ar, { n: 3 }) })).toBeInTheDocument();
    expect(screen.getAllByRole("status").filter((el) => el.getAttribute("aria-live") === "polite").length).toBeGreaterThan(0);
    act(() => sources.emit({ type: "agent", agent: agent("est", { state: "waiting" }) }));
    await waitFor(() =>
      expect(screen.getAllByRole("status").some((el) => el.textContent === fill(texts.announceWaiting.ar, { role: "مهندس التسعير est - عينة" }))).toBe(true),
      { timeout: 3000 }, // "est is working" was said just before: the next waits its 2 s
    );
  });
});
