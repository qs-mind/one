import { render, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setLanguage } from "../i18n";
import type { AgentInfo, Anchor, ViewerHandle } from "../project/types";
import { WorkingLine } from "./WorkingLine";

const OPENED = "deliverable:d1" as const;

function agent(over: Partial<AgentInfo> = {}): AgentInfo {
  return {
    id: "a1",
    kind: "worker",
    role: { en: "Estimator", ar: "مقدّر" },
    desk_id: null,
    model: "m",
    state: "working",
    line: null,
    brief_id: null,
    focus: { frame: OPENED, anchor: { row: "3/02" } },
    at: "2026-11-05T10:00:00Z",
    ...over,
  } as AgentInfo;
}

function box(top = 0, bottom = 500) {
  const el = document.createElement("div");
  el.getBoundingClientRect = () => ({ top, bottom, left: 0, right: 300, width: 300, height: bottom - top, x: 0, y: top, toJSON() {} });
  return el;
}

const handleAt = (rect: DOMRect | null): ViewerHandle => ({ locate: vi.fn((_: Anchor) => rect) });
const rect = (y: number, h = 24) => new DOMRect(0, y, 300, h);
const lines = () => document.querySelectorAll("[data-working-line]");

beforeEach(() => {
  setLanguage("en");
  vi.stubGlobal("requestAnimationFrame", (cb: FrameRequestCallback) => (cb(0), 1));
  vi.stubGlobal("cancelAnimationFrame", () => {});
});
afterEach(() => vi.unstubAllGlobals());

describe("WorkingLine", () => {
  it("draws one aria-hidden line, as tall as the row, titled with the role", async () => {
    render(<WorkingLine handle={handleAt(rect(40, 24))} agents={[agent()]} opened={OPENED} box={box()} />);
    await waitFor(() => expect(lines()).toHaveLength(1));
    const line = lines()[0] as HTMLElement;
    expect(line.getAttribute("title")).toBe("Estimator");
    expect(line.getAttribute("aria-hidden")).toBe("true");
    expect(line.style.height).toBe("24px");
    expect(line.style.transform).toContain("40px");
  });

  it.each(["waiting", "done"] as const)("draws none for a %s agent", (state) => {
    render(<WorkingLine handle={handleAt(rect(40))} agents={[agent({ state })]} opened={OPENED} box={box()} />);
    expect(lines()).toHaveLength(0);
  });

  it("draws none for an agent on another document or without an anchor", () => {
    const other = agent({ focus: { frame: "deliverable:d2", anchor: { row: "3/02" } } });
    const bare = agent({ id: "a2", focus: { frame: OPENED, anchor: null } });
    render(<WorkingLine handle={handleAt(rect(40))} agents={[other, bare]} opened={OPENED} box={box()} />);
    expect(lines()).toHaveLength(0);
  });

  it("draws nothing when locate finds no row or it is outside the box", () => {
    const { rerender } = render(<WorkingLine handle={handleAt(null)} agents={[agent()]} opened={OPENED} box={box()} />);
    expect(lines()).toHaveLength(0);
    rerender(<WorkingLine handle={handleAt(rect(900))} agents={[agent()]} opened={OPENED} box={box(0, 500)} />);
    expect(lines()).toHaveLength(0);
  });

  it("draws one line for two agents on one row, titled with both roles", async () => {
    const second = agent({ id: "a2", state: "thinking", role: { en: "Checker", ar: "مراجع" } });
    render(<WorkingLine handle={handleAt(rect(40))} agents={[agent(), second]} opened={OPENED} box={box()} />);
    await waitFor(() => expect(lines()).toHaveLength(1));
    expect(lines()[0]!.getAttribute("title")).toBe("Estimator, Checker");
  });

  it("joins the roles with an Arabic comma in Arabic", async () => {
    setLanguage("ar");
    const second = agent({ id: "a2", role: { en: "Checker", ar: "مراجع" } });
    render(<WorkingLine handle={handleAt(rect(40))} agents={[agent(), second]} opened={OPENED} box={box()} />);
    await waitFor(() => expect(lines()).toHaveLength(1));
    expect(lines()[0]!.getAttribute("title")).toBe("مقدّر، مراجع");
  });

  it("is hoverable: the line takes pointer events and carries the title, the layer does not", async () => {
    render(<WorkingLine handle={handleAt(rect(40))} agents={[agent()]} opened={OPENED} box={box()} />);
    await waitFor(() => expect(lines()).toHaveLength(1));
    const line = lines()[0] as HTMLElement;
    expect(line.style.pointerEvents).toBe("auto");
    expect(line.getAttribute("title")).toBe("Estimator");
    expect(line.parentElement!.className).toContain("pointer-events-none");
  });

  it("sits at the inline start, right in Arabic", async () => {
    setLanguage("ar");
    render(<WorkingLine handle={handleAt(rect(40))} agents={[agent()]} opened={OPENED} box={box()} />);
    await waitFor(() => expect(lines()).toHaveLength(1));
    const line = lines()[0] as HTMLElement;
    expect(line.parentElement!.getAttribute("dir")).toBe("rtl");
    expect(line.style.insetInlineStart).toBe("0px");
  });

  it("draws nothing for a row fully above the box, and a line for a partly visible one", async () => {
    const { rerender } = render(<WorkingLine handle={handleAt(rect(-30, 24))} agents={[agent()]} opened={OPENED} box={box(0, 500)} />);
    expect(lines()).toHaveLength(0);
    rerender(<WorkingLine handle={handleAt(rect(-10, 24))} agents={[agent()]} opened={OPENED} box={box(0, 500)} />);
    await waitFor(() => expect(lines()).toHaveLength(1));
  });
});
