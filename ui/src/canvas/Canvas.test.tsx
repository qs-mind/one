import { act, createEvent, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { forwardRef, useImperativeHandle } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { count, fill, setLanguage, texts } from "../i18n";
import { canvasApi } from "./api";
import { Canvas } from "./Canvas";
import { fakeSources, type FakeOptions } from "./fake";
import { currentSelection, select } from "./selection";
import type { AgentInfo, DeliverableInfo, Placed, ViewerHandle, ViewerProps } from "./types";

// A stand-in for Plan 6's sheet viewer: one text box, and a locate that finds row "3/02".
vi.mock("./sources", async (original) => ({
  ...(await original<typeof import("./sources")>()),
  viewerFor: (kind: string) => (kind === "sheet" ? FakeViewer : null),
}));

const FakeViewer = forwardRef<ViewerHandle, ViewerProps>(function FakeViewer({ deliverableId, onSelection }, ref) {
  useImperativeHandle(ref, () => ({ locate: (a) => (a.row === "3/02" ? new DOMRect(0, 40, 200, 20) : null) }));
  return (
    <div data-testid={`viewer-${deliverableId}`}>
      <input aria-label="cell" onFocus={() => onSelection?.({ row: "3/02" }, "row 3/02")} />
    </div>
  );
});

// React Flow measures its pane; give it a real size (jsdom has no layout).
const original = Object.getOwnPropertyDescriptors(HTMLElement.prototype);
function paneSize(width = 1200, height = 800) {
  for (const [side, value] of [
    ["offsetWidth", width],
    ["offsetHeight", height],
  ] as const) {
    Object.defineProperty(HTMLElement.prototype, side, {
      configurable: true,
      get(this: HTMLElement) {
        return this.classList.contains("react-flow__renderer") ? value : original[side]!.get!.call(this);
      },
    });
  }
}

const deliverable = (id: string, fields: Partial<DeliverableInfo> = {}): DeliverableInfo => ({
  id,
  kind: "sheet",
  title: `تسعير ${id} - عينة`,
  language: "ar",
  status: "draft",
  code: null,
  same_provider: false,
  revision: null,
  desk: null,
  off_desk: false,
  progress: null,
  open_comments: 0,
  updated_at: "2026-11-05T09:00:00+00:00",
  ...fields,
});

const estimator: AgentInfo = {
  id: "est",
  kind: "specialist",
  role: { en: "Estimator (sample)", ar: "مهندس التسعير - عينة" },
  desk_id: "pricing",
  model: "claude-sonnet-5",
  state: "working",
  line: null,
  brief_id: "b1",
  focus: null,
  at: "2026-11-05T09:00:00+00:00",
};

const frameEl = (name: string) => screen.findByRole("group", { name });
const placedOf = (key: string) => canvasApi.frames().find((f) => f.key === key);

function show(options: FakeOptions) {
  const fake = fakeSources(options);
  const onOpenFull = vi.fn();
  const view = render(
    <div style={{ width: 1200, height: 800 }}>
      <Canvas projectId="p1" sources={fake} onOpenFull={onOpenFull} />
    </div>,
  );
  return { fake, onOpenFull, ...view };
}

const at = (key: Placed["key"], x: number, y: number, w = 960, h = 640): Placed => ({ key, x, y, w, h, z: 0, collapsed: false });
const zoomOne = { x: 0, y: 0, zoom: 1 };

describe("the Project Canvas", () => {
  beforeEach(() => {
    paneSize();
    setLanguage("ar");
  });
  afterEach(() => {
    Object.defineProperties(HTMLElement.prototype, {
      offsetWidth: original.offsetWidth!,
      offsetHeight: original.offsetHeight!,
    });
    select([]);
  });

  it("shows the Project files frame, a frame per Deliverable and the team", async () => {
    show({
      files: [{ id: "f1", name: "مواصفات - عينة.pdf", status: "read", note: null, replaces: null }],
      deliverables: [deliverable("a"), deliverable("b", { kind: "document" })],
    });
    expect(await frameEl(texts.projectFiles.ar)).toHaveTextContent("مواصفات - عينة.pdf");
    expect(await frameEl("تسعير a - عينة")).toBeInTheDocument();
    expect(await frameEl("تسعير b - عينة")).toBeInTheDocument();
    const team = await frameEl(texts.projectTeam.ar);
    expect(team).toHaveTextContent(texts.roleLead.ar);
    expect(team).toHaveTextContent(texts.stateIdle.ar);
    // files get their own frame only when opened
    expect(screen.queryByRole("group", { name: "مواصفات - عينة.pdf" })).toBeNull();
  });

  it("a new Desk starts folded to one line", async () => {
    show({ team: { desks: [{ id: "pricing", name: { en: "Pricing Desk (sample)", ar: "قسم التسعير - عينة" }, stage: "temporary" }], agents: [estimator] } });
    const name = count("deskSummary", 1, { desk: "قسم التسعير - عينة" }, "ar");
    const desk = await frameEl(name);
    expect(desk.querySelector("[data-frame-body]")).toBeNull();
    expect(placedOf("desk:pricing")).toMatchObject({ collapsed: true });
    fireEvent.click(screen.getByRole("button", { name: texts.expand.ar }));
    expect(await screen.findByText("مهندس التسعير - عينة")).toBeInTheDocument();
  });

  it("restores the saved frames and view when the project opens", async () => {
    const frames = [at("deliverable:a", 120.5, -40), at("files:all", -420, 0, 360, 520), at("team:core", -420, 600, 320, 240)];
    const { fake, container } = show({ deliverables: [deliverable("a")], layout: { frames, view: { x: -100, y: 50, zoom: 0.85 } } });
    const node = await frameEl("تسعير a - عينة");
    expect(node.style.transform).toBe("translate(120.5px,-40px)");
    await waitFor(() =>
      expect(container.querySelector<HTMLElement>(".react-flow__viewport")!.style.transform).toBe(
        "translate(-100px,50px) scale(0.85)",
      ),
    );
    expect(canvasApi.frames().sort((a, b) => a.key.localeCompare(b.key))).toEqual(
      [...frames].sort((a, b) => a.key.localeCompare(b.key)),
    );
    expect(fake.saved.frames).toEqual([]); // nothing new to place, nothing gone
  });

  it("removes saved frames whose Deliverable is gone", async () => {
    const frames = [at("deliverable:old", 440, 0), at("files:all", 0, 0, 360, 520), at("team:core", 0, 600, 320, 240)];
    const { fake } = show({ layout: { frames, view: zoomOne } });
    await frameEl(texts.projectFiles.ar);
    await waitFor(() => expect(fake.saved.frames.flatMap((s) => s.removed)).toEqual(["deliverable:old"]));
    expect(placedOf("deliverable:old")).toBeUndefined();
  });

  it("places a new Deliverable from an event without moving the others", async () => {
    const { fake } = show({ deliverables: [deliverable("a")] });
    await frameEl("تسعير a - عينة");
    const before = canvasApi.frames();
    act(() => fake.emit({ type: "deliverable", deliverable: deliverable("new", { kind: "document" }) }));
    expect(await frameEl("تسعير new - عينة")).toBeInTheDocument();
    const after = canvasApi.frames();
    for (const f of before) expect(after.find((x) => x.key === f.key)).toEqual(f);
    const added = after.find((f) => f.key === "deliverable:new")!;
    for (const f of before) {
      const apart = added.x >= f.x + f.w || f.x >= added.x + added.w || added.y >= f.y + f.h || f.y >= added.y + added.h;
      expect(apart, f.key).toBe(true);
    }
    await waitFor(() => expect(fake.saved.frames.flatMap((s) => s.frames.map((f) => f.key))).toContain("deliverable:new"));
  });

  it("an event about a Deliverable already there updates its frame in place", async () => {
    const { fake } = show({ deliverables: [deliverable("a")] });
    const node = await frameEl("تسعير a - عينة");
    const before = placedOf("deliverable:a");
    act(() => fake.emit({ type: "deliverable", deliverable: deliverable("a", { status: "checked", code: "B" }) }));
    await waitFor(() => expect(node).toHaveTextContent(fill(texts.statusChecked.ar, { code: "B" })));
    expect(placedOf("deliverable:a")).toEqual(before);
  });

  it("Delete and Backspace never remove a frame", async () => {
    show({ deliverables: [deliverable("a")] });
    const node = await frameEl("تسعير a - عينة");
    fireEvent.click(node);
    node.focus();
    for (const code of ["Delete", "Backspace"]) {
      fireEvent.keyDown(node, { key: code, code });
      fireEvent.keyDown(document.body, { key: code, code });
    }
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.getByRole("group", { name: "تسعير a - عينة" })).toBeInTheDocument();
    expect(placedOf("deliverable:a")).toBeDefined();
  });

  it("arrows typed in a cell inside a frame do not move the frame", async () => {
    show({ deliverables: [deliverable("a")], layout: { frames: [at("deliverable:a", 0, 0)], view: zoomOne } });
    const node = await frameEl("تسعير a - عينة");
    fireEvent.click(node); // selected, so arrows on the frame itself would move it
    const cell = await screen.findByRole("textbox", { name: "cell" });
    cell.focus();
    for (let i = 0; i < 3; i++) fireEvent.keyDown(cell, { key: "ArrowLeft", code: "ArrowLeft" });
    expect(placedOf("deliverable:a")).toMatchObject({ x: 0, y: 0 });
    // the same key on the frame itself moves it: the test above really tested something
    node.focus();
    fireEvent.keyDown(node, { key: "ArrowLeft", code: "ArrowLeft" });
    await waitFor(() => expect(placedOf("deliverable:a")!.x).toBeLessThan(0));
  });

  it("Enter goes into a frame and Esc comes back, Esc again clears the selection", async () => {
    show({ deliverables: [deliverable("a")], layout: { frames: [at("deliverable:a", 0, 0)], view: zoomOne } });
    const node = await frameEl("تسعير a - عينة");
    await screen.findByRole("textbox", { name: "cell" });
    fireEvent.click(node);
    node.focus();
    fireEvent.keyDown(node, { key: "Enter", code: "Enter" });
    expect(node.querySelector("[data-frame-body]")!.contains(document.activeElement)).toBe(true);
    fireEvent.keyDown(document.activeElement!, { key: "Escape", code: "Escape" });
    expect(document.activeElement).toBe(node);
    fireEvent.keyDown(node, { key: "Escape", code: "Escape" });
    await waitFor(() => expect(currentSelection()).toEqual([]));
  });

  it("selecting a frame fills the selection store with its title", async () => {
    show({ deliverables: [deliverable("a")] });
    fireEvent.click(await frameEl("تسعير a - عينة"));
    await waitFor(() => expect(currentSelection()).toEqual([{ kind: "deliverable", id: "a", title: "تسعير a - عينة" }]));
  });

  it("a selection inside the viewer goes to the store with its label", async () => {
    show({ deliverables: [deliverable("a")], layout: { frames: [at("deliverable:a", 0, 0)], view: zoomOne } });
    fireEvent.focus(await screen.findByRole("textbox", { name: "cell" }));
    expect(currentSelection()).toEqual([
      { kind: "deliverable", id: "a", title: "تسعير a - عينة", anchor: { row: "3/02" }, label: "row 3/02" },
    ]);
  });

  it("a far-out zoom shows the poster, not the live viewer", async () => {
    show({ deliverables: [deliverable("a", { progress: { done: 180, total: 420 } })], layout: { frames: [at("deliverable:a", 0, 0)], view: { x: 0, y: 0, zoom: 0.45 } } });
    const node = await frameEl("تسعير a - عينة");
    expect(node).toHaveTextContent(fill(texts.progressOf.ar, { done: 180, total: 420 }));
    expect(screen.queryByTestId("viewer-a")).toBeNull();
  });

  it("the wheel scrolls a live frame, pans over a poster, and a pinch always zooms the canvas", async () => {
    show({
      deliverables: [deliverable("a"), deliverable("b", { kind: "document" })],
      layout: { frames: [at("deliverable:a", 0, 0), at("deliverable:b", 0, 700, 720, 900)], view: zoomOne },
    });
    await screen.findByTestId("viewer-a");
    const live = (await frameEl("تسعير a - عينة")).querySelector<HTMLElement>("[data-frame-body]")!;
    const poster = (await frameEl("تسعير b - عينة")).querySelector<HTMLElement>("[data-frame-body]")!;
    expect(live).toHaveClass("nowheel", "nodrag", "nopan", "nokey");
    expect(poster).not.toHaveClass("nowheel");
    fireEvent.wheel(live, { deltaY: -100, ctrlKey: true });
    expect(live).not.toHaveClass("nowheel");
    fireEvent.wheel(live, { deltaY: 100 });
    expect(live).toHaveClass("nowheel");
  });

  it("dropping a file adds it to Project Records and opens its frame", async () => {
    const { fake, container } = show({ layout: { frames: [at("files:all", 0, 0, 360, 520)], view: zoomOne } });
    await frameEl(texts.projectFiles.ar);
    const file = new File(["%PDF"], "عرض سعر - عينة.pdf", { type: "application/pdf" });
    const pane = container.querySelector("section")!;
    const drop = createEvent.drop(pane, { dataTransfer: { files: [file], types: ["Files"] } });
    Object.defineProperties(drop, { clientX: { value: 500 }, clientY: { value: 200 } }); // jsdom's drop has no point
    fireEvent(pane, drop);
    expect(await frameEl("عرض سعر - عينة.pdf")).toBeInTheDocument();
    expect(placedOf("file:upload1")).toMatchObject({ x: 500, y: 200 }); // where it was dropped (view at zoom 1)
    expect(fake.uploads).toEqual([file]);
    expect(await frameEl(texts.projectFiles.ar)).toHaveTextContent("عرض سعر - عينة.pdf");
  });

  it("a file added elsewhere (Project Records) comes to the Project files frame from its event", async () => {
    const { fake } = show({});
    const files = await frameEl(texts.projectFiles.ar);
    act(() => fake.emit({ type: "file", file: { id: "f9", name: "جدول كميات - عينة.xlsx", status: "read", note: null, replaces: null } }));
    await waitFor(() => expect(files).toHaveTextContent("جدول كميات - عينة.xlsx"));
  });

  it("an imported client BOQ comes live as its own read-only frame, and is there again after a reload", async () => {
    const boq = { file_id: "f9", name: "مقايسة العميل - عينة.xlsx", items: 2, headings: 1, at: "2026-11-05T09:00:00+00:00" };
    const title = fill(texts.clientBoqTitle.ar, { name: boq.name });
    const { fake, unmount } = show({});
    await frameEl(texts.projectFiles.ar);
    act(() => fake.emit({ type: "client_boq", client_boq: boq }));
    const frame = await frameEl(title);
    expect(frame).toHaveTextContent(texts.clientBoqReadOnly.ar);
    expect(frame).toHaveTextContent(count("clientBoqItems", 2, {}, "ar"));
    expect(screen.queryByRole("button", { name: texts.closeFrame.ar })).toBeNull(); // the client's document stays
    await waitFor(() => expect(fake.saved.frames.flatMap((s) => s.frames.map((f) => f.key))).toContain("clientboq:f9"));
    unmount();
    const saved = at("clientboq:f9", 0, 0);
    show({ clientBoqs: [boq], layout: { frames: [saved], view: zoomOne } });
    expect(await frameEl(title)).toBeInTheDocument();
    expect(placedOf("clientboq:f9")).toEqual(saved);
  });

  it("a file that is not added says why, by name", async () => {
    const { fake, container } = show({});
    await frameEl(texts.projectFiles.ar);
    vi.spyOn(fake, "upload").mockRejectedValueOnce(new Error("refused"));
    const file = new File(["x"], "كبير - عينة.pdf");
    fireEvent.drop(container.querySelector("section")!, { dataTransfer: { files: [file], types: ["Files"] } });
    expect(await screen.findByRole("alert")).toHaveTextContent(`كبير - عينة.pdf ${texts.fileNotAdded.ar}`);
  });

  it("opening a file from the Project files frame gives it its own frame; Close removes only the frame", async () => {
    const { fake } = show({ files: [{ id: "f1", name: "مواصفات - عينة.pdf", status: "read", note: null, replaces: null }] });
    fireEvent.click(await screen.findByRole("button", { name: /مواصفات - عينة.pdf/ }));
    const frame = await frameEl("مواصفات - عينة.pdf");
    fireEvent.click(within(frame).getByRole("button", { name: texts.closeFrame.ar }));
    await waitFor(() => expect(screen.queryByRole("group", { name: "مواصفات - عينة.pdf" })).toBeNull());
    await waitFor(() => expect(fake.saved.frames.flatMap((s) => s.removed)).toContain("file:f1"));
    expect(await fake.files()).toHaveLength(1);
  });

  it("Ctrl+Z after Arrange puts the frames back, Ctrl+Shift+Z arranges again", async () => {
    const frames = [
      at("deliverable:s", 0, 0),
      at("deliverable:d", 1200, 900),
      at("files:all", 3000, 0, 360, 520),
      at("team:core", -800, 2000, 320, 240),
    ];
    const { container } = show({
      deliverables: [deliverable("s", { status: "signed_off" }), deliverable("d")],
      layout: { frames, view: zoomOne },
    });
    await frameEl("تسعير s - عينة");
    const sorted = () => canvasApi.frames().sort((a, b) => a.key.localeCompare(b.key));
    const before = sorted();
    act(() => canvasApi.arrange("stage"));
    const arranged = sorted();
    expect(arranged).not.toEqual(before);
    const pane = container.querySelector("section")!;
    fireEvent.keyDown(pane, { key: "z", code: "KeyZ", ctrlKey: true });
    expect(sorted()).toEqual(before);
    fireEvent.keyDown(pane, { key: "Z", code: "KeyZ", ctrlKey: true, shiftKey: true });
    expect(sorted()).toEqual(arranged);
  });

  it("Arrange by stage is a button in the zoom controls", async () => {
    show({ deliverables: [deliverable("a")] });
    await frameEl("تسعير a - عينة");
    const bar = screen.getByRole("toolbar", { name: texts.zoomControls.ar });
    expect(bar).toHaveAttribute("dir", "rtl");
    expect(bar.style.right).toBe("16px");
    expect(within(bar).getByRole("button", { name: texts.arrangeByStage.ar })).toBeInTheDocument();
  });

  it("the pane is ltr while the page is rtl, and a frame title keeps dir=auto", async () => {
    show({ deliverables: [deliverable("a", { language: "en", title: "BOQ pricing (sample)" })] });
    expect(document.documentElement.dir).toBe("rtl");
    expect(screen.getByRole("region", { name: texts.canvas.ar })).toHaveAttribute("dir", "ltr");
    const node = await frameEl("BOQ pricing (sample)");
    expect(within(node).getByRole("heading", { name: "BOQ pricing (sample)" })).toHaveAttribute("dir", "auto");
    expect(node.querySelector("[data-frame]")).toHaveAttribute("dir", "ltr"); // an English Deliverable reads left to right
  });

  it("Open full screen asks the shell to open the Deliverable", async () => {
    const { onOpenFull } = show({ deliverables: [deliverable("a")] });
    const node = await frameEl("تسعير a - عينة");
    fireEvent.click(within(node).getByRole("button", { name: texts.openFull.ar }));
    expect(onOpenFull).toHaveBeenCalledWith("a");
  });

  it("a canvas that cannot load says so and saves nothing", async () => {
    const fake = fakeSources({ layout: { frames: [at("deliverable:a", 0, 0)], view: null } });
    vi.spyOn(fake, "deliverables").mockRejectedValueOnce(new Error("core down"));
    render(
      <div style={{ width: 1200, height: 800 }}>
        <Canvas projectId="p1" sources={fake} onOpenFull={() => {}} />
      </div>,
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(texts.canvasFailed.ar);
    expect(fake.saved.frames).toEqual([]);
  });

  it("never writes the layout to web storage", async () => {
    const spy = vi.spyOn(Storage.prototype, "setItem");
    const { fake } = show({ deliverables: [deliverable("a")] });
    await frameEl("تسعير a - عينة");
    act(() => canvasApi.arrange("tidy"));
    await waitFor(() => expect(fake.saved.frames.length).toBeGreaterThan(0));
    expect(spy).not.toHaveBeenCalled();
  });
});
