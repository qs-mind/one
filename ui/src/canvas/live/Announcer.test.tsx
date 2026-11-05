import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fill, setLanguage, texts } from "../../i18n";
import { fakeSources } from "../fake";
import { startActivity } from "./activity";
import { ANNOUNCE_GAP_MS, Announcer } from "./Announcer";
import { agent } from "./testing";

const role = "مهندس التسعير est - عينة";

describe("the Announcer", () => {
  let controller: AbortController;
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "setInterval", "clearInterval", "Date", "requestAnimationFrame", "cancelAnimationFrame"] });
    setLanguage("ar");
    controller = new AbortController();
  });
  afterEach(() => {
    act(() => controller.abort());
    vi.useRealTimers();
  });

  function start() {
    const fake = fakeSources({ team: { desks: [], agents: [agent("est"), agent("chk", { kind: "checker", role: texts.roleChecker })] } });
    startActivity(fake, controller.signal);
    render(<Announcer />);
    return fake;
  }
  const emit = (fake: ReturnType<typeof fakeSources>, ...agents: ReturnType<typeof agent>[]) =>
    act(() => {
      for (const a of agents) fake.emit({ type: "agent", agent: a });
      vi.advanceTimersByTime(16); // one animation frame
    });

  it("is one polite status region", async () => {
    start();
    const region = screen.getByRole("status");
    expect(region).toHaveAttribute("aria-live", "polite");
  });

  it("says a state change in the page language, and never a move", async () => {
    const fake = start();
    await act(async () => {});
    emit(fake, agent("est", { focus: { frame: "deliverable:other", anchor: { row: "3/02" } } }));
    expect(screen.getByRole("status")).toHaveTextContent(/^$/);
    emit(fake, agent("est", { state: "waiting" }));
    expect(screen.getByRole("status")).toHaveTextContent(fill(texts.announceWaiting.ar, { role }));
    act(() => setLanguage("en"));
    act(() => vi.advanceTimersByTime(ANNOUNCE_GAP_MS));
    emit(fake, agent("est", { state: "done" }));
    expect(screen.getByRole("status")).toHaveTextContent(fill(texts.announceDone.en, { role: "Estimator est (sample)" }));
  });

  it("says at most one thing every 2 s; what comes between is said together, the latest per agent", async () => {
    const fake = start();
    await act(async () => {});
    emit(fake, agent("est", { state: "waiting" }));
    const region = screen.getByRole("status");
    expect(region).toHaveTextContent(fill(texts.announceWaiting.ar, { role }));
    emit(fake, agent("est", { state: "failed" }));
    emit(fake, agent("chk", { kind: "checker", role: texts.roleChecker, state: "waiting" }));
    expect(region).toHaveTextContent(fill(texts.announceWaiting.ar, { role })); // not yet
    act(() => vi.advanceTimersByTime(ANNOUNCE_GAP_MS));
    expect(region).toHaveTextContent(
      `${fill(texts.announceFailed.ar, { role })}. ${fill(texts.announceWaiting.ar, { role: texts.roleChecker.ar })}`,
    );
  });

  it("says when a working agent goes silent", async () => {
    start();
    await act(async () => {});
    act(() => vi.advanceTimersByTime(61_000));
    expect(screen.getByRole("status")).toHaveTextContent(fill(texts.announceNoNews.ar, { role }));
  });
});
