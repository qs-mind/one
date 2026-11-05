import { render, screen } from "@testing-library/react";
import { ReactFlow, ReactFlowProvider } from "@xyflow/react";
import { describe, expect, it, vi } from "vitest";
import { texts } from "../i18n";
import { CommandDialog, CommandInput, CommandItem, CommandList } from "../ui/command";
import { canvasApi, registerCanvas, type CanvasApi } from "./api";
import { Canvas } from "./Canvas";
import { DESKS_START_COLLAPSED, FILE_FRAMES } from "./choices";
import { fakeSources, sampleSources } from "./fake";
import { currentSelection, select, subscribeSelection } from "./selection";
import type { ActivityEvent, AgentInfo, SelectionItem } from "./types";

const lead: AgentInfo = {
  id: "run1",
  kind: "lead",
  role: { en: "Lead QS", ar: "كبير مهندسي الكميات" },
  desk_id: null,
  model: "claude-sonnet-5",
  state: "thinking",
  line: null,
  brief_id: "b1",
  focus: null,
  at: "2026-11-05T10:00:00+00:00",
};

describe("canvas foundation", () => {
  it("React Flow mounts in jsdom with the mocks", () => {
    render(
      <ReactFlowProvider>
        <div style={{ width: 800, height: 600 }}>
          <ReactFlow nodes={[{ id: "a", position: { x: 0, y: 0 }, data: { label: "a" } }]} edges={[]} />
        </div>
      </ReactFlowProvider>,
    );
    expect(document.querySelector(".react-flow__node")).toBeInTheDocument();
  });

  it("the mocks read sizes and scale from inline style", () => {
    const el = document.createElement("div");
    el.style.width = "320px";
    el.style.height = "240px";
    expect([el.offsetWidth, el.offsetHeight]).toEqual([320, 240]);
    expect(new DOMMatrixReadOnly("scale(0.6)").m22).toBe(0.6);
    const seen: number[][] = [];
    new ResizeObserver((entries) => seen.push([entries[0]!.contentRect.width, entries[0]!.contentRect.height])).observe(el);
    expect(seen).toEqual([[320, 240]]);
  });

  it("every new text has both languages", () => {
    for (const key of ["canvas", "commandBox", "generalChat", "noNews", "sampleData", "frame", "commandBar"] as const) {
      expect(texts[key].en.trim()).not.toBe("");
      expect(texts[key].ar.trim()).not.toBe("");
    }
    expect(texts.canvas.ar).toBe("كانفاس المشروع");
    expect(texts.frame.ar).toBe("إطار");
    expect(texts.commandBar.ar).toBe("شريط الأوامر");
    expect(texts.sampleData.ar).toBe("بيانات تجريبية");
  });

  it("no canvas text calls the canvas «لوحة»", () => {
    for (const [key, text] of Object.entries(texts)) {
      if (/canvas|frame|commandBar/i.test(key)) expect(text.ar, key).not.toContain("لوحة");
    }
  });

  it("the founder's open choices start at the recommended defaults", () => {
    expect(DESKS_START_COLLAPSED).toBe(true);
    expect(FILE_FRAMES).toBe("opened");
  });

  it("selection store notifies and replaces", () => {
    const item: SelectionItem = { kind: "deliverable", id: "d1", title: "تسعير المقايسة - عينة", label: "rows 3/01–3/04" };
    const listener = vi.fn();
    const stop = subscribeSelection(listener);
    select([item]);
    expect(currentSelection()).toEqual([item]);
    expect(listener).toHaveBeenCalledTimes(1);
    select([]);
    expect(currentSelection()).toEqual([]);
    stop();
    select([item]);
    expect(listener).toHaveBeenCalledTimes(2);
    select([]);
  });

  it("canvasApi does nothing before a canvas mounts, then calls the mounted one", () => {
    expect(() => canvasApi.fitAll()).not.toThrow();
    expect(canvasApi.frames()).toEqual([]);
    const fitAll = vi.fn();
    const unregister = registerCanvas({ ...stubApi(), fitAll });
    canvasApi.fitAll();
    expect(fitAll).toHaveBeenCalledOnce();
    unregister();
    canvasApi.fitAll();
    expect(fitAll).toHaveBeenCalledOnce();
  });

  it("fake sources serve their lists and record saves", async () => {
    const fake = fakeSources({ files: [{ id: "f1", name: "مواصفات - عينة.pdf", status: "read", note: null, replaces: null }] });
    expect((await fake.files()).map((f) => f.id)).toEqual(["f1"]);
    expect(await fake.deliverables()).toEqual([]);
    expect(await fake.team()).toEqual({ desks: [], agents: [] });
    expect(await fake.layout()).toEqual({ frames: [], view: null });
    await fake.saveFrames([{ key: "files:all", x: 0, y: 0, w: 360, h: 520, z: 0, collapsed: false }], ["file:gone"]);
    await fake.saveView({ x: 1, y: 2, zoom: 0.85 });
    expect(fake.saved.frames).toEqual([{ frames: [expect.objectContaining({ key: "files:all" })], removed: ["file:gone"], keepalive: false }]);
    expect(fake.saved.views).toEqual([{ view: { x: 1, y: 2, zoom: 0.85 }, keepalive: false }]);
    expect(await fake.layout()).toEqual({ frames: [expect.objectContaining({ key: "files:all" })], view: { x: 1, y: 2, zoom: 0.85 } });
  });

  it("fake sources emit events to the listener until aborted", () => {
    const fake = fakeSources({});
    const got: ActivityEvent[] = [];
    const controller = new AbortController();
    fake.activity((event) => got.push(event), controller.signal);
    fake.emit({ type: "agent", agent: lead });
    controller.abort();
    fake.emit({ type: "agent-gone", id: "run1" });
    expect(got).toEqual([{ type: "agent", agent: lead }]);
  });

  it("sample sources label every title as sample", async () => {
    const sample = sampleSources();
    const files = await sample.files();
    const deliverables = await sample.deliverables();
    const { desks } = await sample.team();
    expect(files.length).toBeGreaterThan(0);
    expect(deliverables.length).toBeGreaterThan(0);
    for (const f of files) expect(f.name).toMatch(/عينة|sample/);
    for (const d of deliverables) expect(d.title).toMatch(/عينة|sample/);
    for (const d of desks) expect(`${d.name.ar} ${d.name.en}`).toMatch(/عينة|sample/);
  });

  it("the palette dialog is named and holds the command list", async () => {
    render(
      <CommandDialog title={texts.palette.ar} open onOpenChange={() => {}}>
        <CommandInput placeholder={texts.palette.ar} />
        <CommandList>
          <CommandItem>{texts.fitAll.ar}</CommandItem>
        </CommandList>
      </CommandDialog>,
    );
    expect(await screen.findByRole("dialog", { name: texts.palette.ar })).toHaveTextContent(texts.fitAll.ar);
  });

  it("the Canvas stub renders a labelled region with its children", () => {
    render(
      <Canvas projectId="p1" sources={fakeSources({})} onOpenFull={() => {}}>
        <span>inside</span>
      </Canvas>,
    );
    expect(screen.getByRole("region", { name: texts.canvas.ar })).toHaveTextContent("inside");
  });
});

function stubApi(): CanvasApi {
  return { focusFrame() {}, fitAll() {}, zoomTo() {}, openFile() {}, arrange() {}, frames: () => [] };
}
