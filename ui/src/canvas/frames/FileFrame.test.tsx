import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fill, setLanguage, texts } from "../../i18n";
import { canvasApi } from "../api";
import { Canvas } from "../Canvas";
import { fakeSources, type FakeOptions } from "../fake";
import type { FileInfo, Placed } from "../types";

// React Flow measures its renderer element; give it a real size (jsdom has no layout).
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

const spec: FileInfo = { id: "spec", name: "المواصفات الفنية - عينة.pdf", status: "read", note: null, replaces: null };
const boq: FileInfo = { id: "boq", name: "مقايسة العميل - عينة.xlsx", status: "read", note: null, replaces: null };
const frame = (key: Placed["key"], x = 0): Placed => ({ key, x, y: 0, w: 480, h: 640, z: 0, collapsed: false });

function show(options: FakeOptions, frames: Placed[]) {
  const fake = fakeSources({ ...options, layout: { frames, view: { x: 0, y: 0, zoom: 1 } } });
  render(
    <div style={{ width: 1200, height: 800 }}>
      <Canvas projectId="p1" sources={fake} onOpenFull={() => {}} />
    </div>,
  );
  return fake;
}

describe("a file frame", () => {
  beforeEach(() => {
    paneSize();
    setLanguage("ar");
  });
  afterEach(() => {
    Object.defineProperties(HTMLElement.prototype, { offsetWidth: original.offsetWidth!, offsetHeight: original.offsetHeight! });
  });

  it("a PDF frame shows the page image and moves between pages", async () => {
    const sources = show({ files: [spec], pages: { spec: 18 } }, [frame("file:spec")]);
    const image = vi.spyOn(sources, "pageImage");
    const node = await screen.findByRole("group", { name: spec.name });
    const page1 = await within(node).findByRole("img", { name: fill(texts.sheetPageOf.ar, { page: 1, pages: 18 }) });
    expect(page1).toHaveAttribute("src", "data:image/png;fake,spec/1/600");
    expect(within(node).getByRole("button", { name: texts.sheetPreviousPage.ar })).toBeDisabled();
    fireEvent.click(within(node).getByRole("button", { name: texts.sheetNextPage.ar }));
    expect(await within(node).findByRole("img", { name: fill(texts.sheetPageOf.ar, { page: 2, pages: 18 }) })).toHaveAttribute(
      "src",
      "data:image/png;fake,spec/2/600",
    );
    expect(image).toHaveBeenLastCalledWith("spec", 2, 600);
  });

  it("a page that cannot be shown says so", async () => {
    const fake = show({ files: [spec], pages: { spec: 3 } }, [frame("file:spec")]);
    vi.spyOn(fake, "pageImage").mockRejectedValue(new Error("no"));
    fireEvent.click(await screen.findByRole("button", { name: texts.sheetNextPage.ar }));
    expect(await screen.findByRole("alert")).toHaveTextContent(texts.pageNotShown.ar);
  });

  it("a scanned page says so in the page language", async () => {
    show({ files: [spec], pages: { spec: 2 }, text: { spec: [{ locator: { page: 2 }, text: "القسم ٣ - نص عينة" }] } }, [
      frame("file:spec"),
    ]);
    fireEvent.click(await screen.findByRole("button", { name: texts.showPageText.ar }));
    expect(await screen.findByText(texts.pageScanned.ar)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: texts.sheetNextPage.ar }));
    expect(await screen.findByText("القسم ٣ - نص عينة")).toHaveAttribute("dir", "auto");
    fireEvent.click(screen.getByRole("button", { name: texts.sheetPreviousPage.ar }));
    expect(await screen.findByText(texts.pageScanned.ar)).toBeInTheDocument();
    act(() => setLanguage("en"));
    expect(await screen.findByText(texts.pageScanned.en)).toBeInTheDocument();
    act(() => setLanguage("ar"));
  });

  it("another file shows the text One read, with its sheet and row", async () => {
    show({ files: [boq], text: { boq: [{ locator: { sheet: "BOQ", row: 12 }, text: "3/02 خرسانة مسلحة - عينة" }] } }, [frame("file:boq")]);
    const node = await screen.findByRole("group", { name: boq.name });
    expect(await within(node).findByText("3/02 خرسانة مسلحة - عينة")).toBeInTheDocument();
    expect(node).toHaveTextContent(fill(texts.sheetRow.ar, { sheet: "BOQ", row: 12 }));
    expect(within(node).queryByRole("img")).toBeNull();
  });

  it("a file with no text says so", async () => {
    show({ files: [boq] }, [frame("file:boq")]);
    expect(await screen.findByText(texts.fileNoText.ar)).toBeInTheDocument();
  });

  it("an answer that cites a page opens the frame at that page", async () => {
    const fake = show({ files: [spec], pages: { spec: 18 } }, []);
    await waitFor(() => expect(canvasApi.frames().length).toBeGreaterThan(0));
    act(() => canvasApi.openFile("spec", 7));
    expect(await screen.findByRole("img", { name: fill(texts.sheetPageOf.ar, { page: 7, pages: 18 }) })).toBeInTheDocument();
    await waitFor(() => expect(fake.saved.frames.flatMap((s) => s.frames.map((f) => f.key))).toContain("file:spec"));
  });
});
