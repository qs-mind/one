// The top bar's motion (docs/specs/2026-11-05-motion-design.md 2.7 and 2.8): the language wipe from its button,
// and the search field that opens the palette from itself.
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { language, setLanguage, texts } from "../i18n";
import { fakeSources } from "../project/fake";
import { setCurrentProject } from "../records/project";
import { resetZoom, zoomIn } from "../ui/scale";
import { workspaceApi } from "../workspace/api";
import { App } from "./App";
import { bodyOf, calls, core, P1 } from "./testing";

const box = () => screen.findByRole("textbox", { name: texts.message.ar });
const topBar = () => screen.getByRole("banner", { name: texts.topBar.ar });
const field = () => within(topBar()).getByRole("button", { name: `${texts.searchField.ar} Ctrl K` });

type Frames = Keyframe[] | PropertyIndexedKeyframes;
const animate = vi.fn((_frames: Frames, _options?: KeyframeAnimationOptions) => ({ finished: Promise.resolve(), finish() {} }));
const animated = () => animate.mock.contexts as Element[];

function reducedMotion(on: boolean) {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: query.includes("reduce") ? on : false,
    media: query,
    addEventListener() {},
    removeEventListener() {},
  }));
}

beforeEach(() => {
  setLanguage("ar");
  setCurrentProject(undefined);
  animate.mockClear();
  Element.prototype.animate = animate as unknown as Element["animate"];
});

afterEach(() => {
  delete (Element.prototype as { animate?: unknown }).animate;
  delete (document as { startViewTransition?: unknown }).startViewTransition;
});

describe("the language wipe", () => {
  it("spreads from the language button's own centre, on an Arabic page too", async () => {
    core();
    const start = vi.fn((update: () => void) => {
      update();
      return { ready: Promise.resolve(), finished: Promise.resolve(), skipTransition() {} };
    });
    Object.defineProperty(document, "startViewTransition", { configurable: true, value: start });
    const user = userEvent.setup();
    render(<App />);
    await user.click(await screen.findByRole("button", { name: texts.more.ar }));
    const button = await screen.findByRole("button", { name: texts.otherLanguage.ar });
    button.getBoundingClientRect = () => new DOMRect(1200, 60, 100, 36);
    await user.click(button);
    expect(start).toHaveBeenCalledTimes(1);
    expect(language()).toBe("en");
    // the More menu closes with the switch: it does not stay open over the new page
    await waitFor(() => expect(screen.queryByRole("button", { name: texts.otherLanguage.en })).toBeNull());
    await waitFor(() =>
      expect(animate).toHaveBeenCalledWith(
        { clipPath: [expect.stringContaining("at 1250px 78px"), expect.stringContaining("at 1250px 78px")] },
        expect.objectContaining({ pseudoElement: "::view-transition-new(root)" }),
      ),
    );
  });
});

describe("the search field", () => {
  it("reads Search Ctrl K and opens the palette from itself", async () => {
    core();
    const user = userEvent.setup();
    render(<App />);
    await box();
    field().getBoundingClientRect = () => new DOMRect(900, 12, 240, 32);
    await user.click(field());
    const dialog = await screen.findByRole("dialog", { name: texts.palette.ar });
    await waitFor(() => expect(animated()).toContain(dialog));
    const [frames, options] = animate.mock.calls[animated().indexOf(dialog)]!;
    expect(options).toEqual(expect.objectContaining({ duration: 220 }));
    expect((frames as Keyframe[])[0]!.transform).toMatch(/^translate\(/); // from the field's place
    expect((frames as Keyframe[]).at(-1)!.transform).toBe("none");
    const grown = animate.mock.calls.length;
    await user.type(within(dialog).getByRole("combobox"), "boq");
    expect(animate.mock.calls).toHaveLength(grown); // typing never plays it again
  });

  it("Escape closes it back into the field, and the field has the focus again", async () => {
    core();
    const user = userEvent.setup();
    render(<App />);
    await box();
    await user.click(field());
    const dialog = await screen.findByRole("dialog", { name: texts.palette.ar });
    animate.mockClear();
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(animated()).toContain(dialog); // it closed back to the field
    expect(field()).toHaveFocus();
  });

  it("Ctrl K still opens it, in the middle, with no motion from the field", async () => {
    core();
    render(<App />);
    await box();
    fireEvent.keyDown(document, { code: "KeyK", key: "ن", ctrlKey: true });
    const dialog = await screen.findByRole("dialog", { name: texts.palette.ar });
    expect(animated()).not.toContain(dialog);
  });

  it("with reduced motion it opens and closes with no animation", async () => {
    reducedMotion(true);
    core();
    const user = userEvent.setup();
    render(<App />);
    await box();
    await user.click(field());
    await screen.findByRole("dialog", { name: texts.palette.ar });
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(animate).not.toHaveBeenCalled();
    expect(field()).toHaveFocus();
  });
});

describe("below 1000 px", () => {
  it("More holds Search as a word with its keys as a hint, the overflow set apart from the rest", async () => {
    vi.stubGlobal("matchMedia", (query: string) => ({
      matches: query === "(max-width: 1279px)" || query.includes("999px"), // below 1000 px: search folds too
      media: query,
      addEventListener() {},
      removeEventListener() {},
    }));
    setCurrentProject(P1);
    core();
    const user = userEvent.setup();
    render(<App />);
    await screen.findByRole("heading", { level: 1 }); // narrow: the chat waits behind its button
    await user.click(within(topBar()).getByRole("button", { name: texts.more.ar }));
    const search = await screen.findByRole("button", { name: `${texts.searchField.ar} Ctrl K` });
    expect(search.querySelector("span")).toHaveTextContent(new RegExp(`^${texts.searchField.ar}$`));
    expect(search.querySelector("kbd")).toHaveTextContent(/^Ctrl K$/);
    // Search, then a line, then the rest of More (the Deliverables and Project Records are in the document switcher)
    const order = [...search.parentElement!.children].map((el) => (el.tagName === "HR" ? "—" : (el.textContent ?? "")));
    const at = order.indexOf(`${texts.searchField.ar}Ctrl K`);
    expect(order.slice(at, at + 2)).toEqual([`${texts.searchField.ar}Ctrl K`, "—"]);
    expect(order).not.toContain(texts.deliverablesButton.ar);
    expect(order).not.toContain(texts.records.ar);
    vi.unstubAllGlobals();
  });
});

describe("what is waiting", () => {
  it("one quiet line: a copper dot and «مستنيك قرار واحد», «مستنيك قرارين», or Slate «مافيش حاجة مستنياك»", async () => {
    setCurrentProject(P1);
    core();
    const sources = fakeSources({ status: { waiting: 1 } });
    render(<App sourcesFor={() => sources} />);
    const one = await within(topBar()).findByRole("button", { name: "مستنيك قرار واحد" });
    expect(one).toHaveClass("text-copper");
    expect(one.querySelector("[data-waiting-dot]")).toHaveClass("bg-copper");
    act(() => sources.emit({ type: "waiting", count: 2 }));
    expect(await within(topBar()).findByRole("button", { name: "مستنيك قرارين" })).toBeInTheDocument();
    act(() => sources.emit({ type: "waiting", count: 0 }));
    const none = await within(topBar()).findByText("مافيش حاجة مستنياك");
    expect(none).toHaveClass("text-slate");
    expect(none.closest("button")).toBeNull(); // nothing to go to
  });

  it("no Deliverables or Project Records button: both are in the document switcher", async () => {
    setCurrentProject(P1);
    core();
    render(<App sourcesFor={() => fakeSources({})} />);
    await box();
    expect(within(topBar()).queryByRole("button", { name: texts.deliverablesButton.ar })).toBeNull();
    expect(within(topBar()).queryByRole("button", { name: texts.records.ar })).toBeNull();
  });
});

describe("the zoom in More", () => {
  const zoomSaved = { "PUT /api/settings/zoom": (init: RequestInit) => new Response(init.body as string) };

  it("shows the zoom now, steps it with − and + (staying open), resets it from the figure, and keeps it in the core", async () => {
    const fetch = core({ routes: zoomSaved });
    const user = userEvent.setup();
    render(<App />);
    await user.click(await screen.findByRole("button", { name: texts.more.ar }));
    const row = await screen.findByText(texts.zoom.ar);
    const reset = screen.getByRole("button", { name: `${texts.zoomReset.ar} (100%)` });
    expect(reset).toHaveTextContent("100%");
    await user.click(screen.getByRole("button", { name: texts.zoomIn.ar }));
    await user.click(screen.getByRole("button", { name: texts.zoomIn.ar }));
    expect(row).toBeVisible(); // a step keeps More open
    expect(reset).toHaveTextContent("120%");
    await user.click(screen.getByRole("button", { name: texts.zoomOut.ar }));
    expect(reset).toHaveTextContent("110%");
    await user.click(reset);
    expect(reset).toHaveTextContent("100%");
    const saved = calls(fetch, "PUT", "/api/settings/zoom").map(([, init]) => bodyOf(init).zoom);
    expect(saved).toEqual([1.1, 1.2, 1.1, 1]);
  });

  it("can't go past 80 %: its step is disabled there", async () => {
    core({ routes: zoomSaved });
    const user = userEvent.setup();
    render(<App />);
    await user.click(await screen.findByRole("button", { name: texts.more.ar }));
    const out = await screen.findByRole("button", { name: texts.zoomOut.ar });
    await user.click(out);
    await user.click(out);
    expect(out).toBeDisabled();
    expect(screen.getByRole("button", { name: `${texts.zoomReset.ar} (80%)` })).toBeInTheDocument();
  });
});

describe("Back and the zoom in the top bar", () => {
  it("a small Back arrow, off with nothing to go back to, takes the engineer to the document before", async () => {
    setCurrentProject(P1);
    core({ routes: { "GET /api/projects/p1/files": () => Response.json({ files: [] }) } });
    render(<App sourcesFor={() => fakeSources({ deliverables: [] })} />);
    const back = await within(topBar()).findByRole("button", { name: texts.goBack.ar });
    expect(back).toBeDisabled();
    expect(back).toHaveTextContent("→"); // back points right on an Arabic page
    act(() => workspaceApi.open("files:all"));
    await waitFor(() => expect(back).toBeEnabled());
    fireEvent.click(back);
    await waitFor(() => expect(back).toBeDisabled());
  });

  it("says the zoom as a percent for a moment when it changes", async () => {
    core();
    render(<App />);
    await box();
    expect(document.querySelector("[data-zoom-toast]")).toBeNull();
    act(() => zoomIn());
    expect(document.querySelector("[data-zoom-toast]")).toHaveTextContent("110%");
    await waitFor(() => expect(document.querySelector("[data-zoom-toast]")).toBeNull(), { timeout: 2000 });
    act(() => resetZoom());
  });
});
