import { act, screen, waitFor } from "@testing-library/react";
import { Profiler } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setLanguage, texts } from "../../i18n";
import { STRIP_H } from "../place";
import { Cursors, STACK_PX, STRIP_INSET } from "./Cursors";
import { agent, paneSize, restorePane, showCanvas } from "./testing";

vi.mock("../../project/sources", async (original) => {
  const { FakeViewer } = await import("../../project/live/testViewer");
  return { ...(await original<typeof import("../../project/sources")>()), viewerFor: (kind: string) => (kind === "sheet" ? FakeViewer : null) };
});

const transform = (id: string) => screen.getByTestId(`cursor-${id}`).style.transform;
const frameName = "تسعير boq - عينة";

describe("the agents' cursors", () => {
  beforeEach(() => {
    paneSize();
    setLanguage("ar");
  });
  afterEach(() => {
    restorePane();
    vi.useRealTimers();
  });

  it("no events, no cursors", async () => {
    showCanvas({}, <Cursors />);
    await screen.findByRole("group", { name: frameName });
    expect(screen.queryByTestId(/cursor-/)).toBeNull();
  });

  it("an agent's cursor appears on its frame with its role name, hidden from screen readers", async () => {
    const { fake } = showCanvas({}, <Cursors />);
    await screen.findByRole("group", { name: frameName });
    act(() => fake.emit({ type: "agent", agent: agent("est") }));
    const cursor = await screen.findByTestId("cursor-est");
    expect(cursor).toHaveTextContent("مهندس التسعير est - عينة");
    expect(cursor.closest('[aria-hidden="true"]')).not.toBeNull();
    // no anchor: the trailing end of the name strip (the page is Arabic, so the left end)
    expect(transform("est")).toBe(`translate(${STRIP_INSET}px, ${STRIP_H / 2}px)`);
  });

  it("the cursor goes to the row the viewer can locate, else to the name strip", async () => {
    const { fake } = showCanvas({}, <Cursors />);
    await screen.findByTestId("viewer-boq");
    act(() => fake.emit({ type: "agent", agent: agent("est", { focus: { frame: "deliverable:boq", anchor: { row: "3/02" } } }) }));
    await waitFor(() => expect(transform("est")).toBe(`translate(10px, ${STRIP_H + 1 + 40}px)`));
    act(() => fake.emit({ type: "agent", agent: agent("est", { focus: { frame: "deliverable:boq", anchor: { row: "9/99" } } }) }));
    await waitFor(() => expect(transform("est")).toBe(`translate(${STRIP_INSET}px, ${STRIP_H / 2}px)`));
  });

  it("cursors on one frame stack 24 px apart; the Checking QS label is outlined", async () => {
    const { fake } = showCanvas({}, <Cursors />);
    await screen.findByRole("group", { name: frameName });
    act(() => {
      fake.emit({ type: "agent", agent: agent("a1") });
      fake.emit({ type: "agent", agent: agent("chk", { kind: "checker", role: texts.roleChecker }) });
    });
    await screen.findByTestId("cursor-chk");
    expect(transform("a1")).toBe(`translate(${STRIP_INSET}px, ${STRIP_H / 2}px)`);
    expect(transform("chk")).toBe(`translate(${STRIP_INSET}px, ${STRIP_H / 2 + STACK_PX}px)`);
    expect(screen.getByTestId("cursor-chk").querySelector("span")).toHaveClass("border-ink", "bg-paper");
    expect(screen.getByTestId("cursor-a1").querySelector("span")).toHaveClass("bg-ink", "text-paper");
  });

  it("100 moves in one frame render once", async () => {
    let commits = 0;
    const { fake } = showCanvas(
      {},
      <Profiler id="cursors" onRender={() => (commits += 1)}>
        <Cursors />
      </Profiler>,
    );
    await screen.findByRole("group", { name: frameName });
    act(() => fake.emit({ type: "agent", agent: agent("est") }));
    await screen.findByTestId("cursor-est");
    await act(() => new Promise((r) => setTimeout(r, 50)));
    const before = commits;
    await act(async () => {
      for (let i = 0; i < 100; i++)
        fake.emit({ type: "agent", agent: agent("est", { line: { en: `item ${i}`, ar: `بند ${i}` } }) });
      await new Promise((r) => requestAnimationFrame(r));
    });
    expect(commits - before).toBe(1);
  });

  it("a finished agent's cursor goes; a silent one says no news after a minute", async () => {
    const { fake } = showCanvas({}, <Cursors />);
    await screen.findByRole("group", { name: frameName });
    act(() => {
      fake.emit({ type: "agent", agent: agent("est") });
      fake.emit({ type: "agent", agent: agent("quiet") });
    });
    await screen.findByTestId("cursor-quiet");
    act(() => fake.emit({ type: "agent", agent: agent("est", { state: "done" }) }));
    await waitFor(() => expect(screen.queryByTestId("cursor-est")).toBeNull());
    expect(screen.getByTestId("cursor-quiet")).not.toHaveTextContent(texts.noNews.ar);
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(Date.now() + 61_000);
    await waitFor(() => expect(screen.getByTestId("cursor-quiet")).toHaveTextContent(texts.noNews.ar), { timeout: 3000 });
  });

  it("reduced motion: the cursor has no transition", async () => {
    vi.stubGlobal("matchMedia", (query: string) => ({ matches: query.includes("reduce"), media: query, addEventListener() {}, removeEventListener() {} }));
    const { fake } = showCanvas({}, <Cursors />);
    await screen.findByRole("group", { name: frameName });
    act(() => fake.emit({ type: "agent", agent: agent("est") }));
    expect((await screen.findByTestId("cursor-est")).style.transition).toBe("none");
  });

  it("without reduced motion the cursor glides by transform", async () => {
    const { fake } = showCanvas({}, <Cursors />);
    await screen.findByRole("group", { name: frameName });
    act(() => fake.emit({ type: "agent", agent: agent("est") }));
    expect((await screen.findByTestId("cursor-est")).style.transition).toBe("transform 300ms ease-out");
  });

  it("an agent on a frame that is not on the canvas has no cursor", async () => {
    const { fake } = showCanvas({}, <Cursors />);
    await screen.findByRole("group", { name: frameName });
    act(() => fake.emit({ type: "agent", agent: agent("est", { focus: { frame: "file:nowhere", anchor: null } }) }));
    await act(() => new Promise((r) => setTimeout(r, 50)));
    expect(screen.queryByTestId("cursor-est")).toBeNull();
  });
});
