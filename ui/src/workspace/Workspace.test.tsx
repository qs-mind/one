// The workspace (Task 9): the open document at the inline start with the chat beside it, Back with Alt and the arrow
// that points back in the page's direction, and a selection in the document as the composer's chip. The viewer is a
// stand-in (each viewer has its own tests); the shell's core is the shell tests' mocked fetch.
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useImperativeHandle } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { entry } from "../deliverables/fixtures";
import { setLanguage, texts } from "../i18n";
import { fakeSources } from "../project/fake";
import { currentSelection, select } from "../project/selection";
import type { ViewerProps } from "../project/types";
import { setCurrentProject } from "../records/project";
import { App } from "../shell/App";
import { core, P1 } from "../shell/testing";
import { workspaceApi } from "./api";
import { markFor, openSourceFile } from "./reveal";
import { sourceKeys } from "../sources/targets";
import { DocumentHead, Workspace } from "./Workspace";

const located: { row?: string }[] = [];

// one component for every kind, as the real registry gives (a new one each render would remount the viewer)
function StandIn({ deliverableId, onSelection, ref }: ViewerProps) {
  useImperativeHandle(ref, () => ({
    locate: (anchor) => {
      located.push({ row: anchor.row });
      return new DOMRect(0, 40, 300, 24);
    },
  }));
  return (
    <div data-testid={`viewer-${deliverableId}`}>
      <button type="button" onClick={() => onSelection?.({ row: "3/02" }, "البنود 3/02–3/04")}>
        select rows
      </button>
      <button type="button" onClick={() => onSelection?.(null, null)}>
        clear rows
      </button>
    </div>
  );
}

vi.mock("../viewers/registry", () => ({ viewerFor: () => StandIn }));

const A = entry({ id: "dA", title: "المقايسة المسعّرة - عينة" });
const B = entry({ id: "dB", title: "خطاب العطاء - عينة", kind: "document" });
const file = { id: "f1", name: "عرض سعر - عينة.pdf", status: "read" as const, note: null, replaces: null };

function show() {
  const sources = fakeSources({ deliverables: [A, B], files: [file] });
  const documents = { deliverables: [A, B], clientBoqs: [], files: [file], desks: [] };
  render(
    <>
      <DocumentHead documents={documents} />
      <Workspace projectId="p1" sources={sources} documents={documents} />
    </>,
  );
  return sources;
}

beforeEach(() => {
  setLanguage("ar");
  located.length = 0;
  workspaceApi.reset({ key: "deliverable:dA", anchor: null }, () => true);
});
afterEach(() => {
  select([]);
  setCurrentProject(undefined);
});

describe("the workspace", () => {
  it("shows the open document in a sheet, its title in the head", async () => {
    show();
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(A.title);
    expect(await screen.findByTestId("viewer-dA")).toBeInTheDocument();
    expect(screen.getByTestId("viewer-dA").closest("[data-document-sheet]")).not.toBeNull();
  });

  it("its title and state are in the top bar: no head row takes the sheet's height", async () => {
    setCurrentProject(P1);
    core();
    const sources = fakeSources({ deliverables: [A], workspace: { key: "deliverable:dA", anchor: null } });
    render(<App sourcesFor={() => sources} />);
    await screen.findByTestId("viewer-dA");
    const title = screen.getByRole("heading", { level: 1 });
    expect(title).toHaveTextContent(A.title);
    expect(screen.getByRole("banner")).toContainElement(title);
    const region = document.querySelector<HTMLElement>('[data-region="document"]')!;
    expect(region.firstElementChild).toHaveAttribute("data-document-sheet"); // the sheet is the first thing in it
  });

  it("the document sits before the chat in DOM order: at the inline start", async () => {
    setCurrentProject(P1);
    core();
    const sources = fakeSources({ deliverables: [A], workspace: { key: "deliverable:dA", anchor: null } });
    render(<App sourcesFor={() => sources} />);
    const chat = await screen.findByRole("complementary", { name: texts.projectChat.ar });
    const doc = await screen.findByTestId("viewer-dA");
    expect(doc.compareDocumentPosition(chat) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("Alt+→ goes Back in Arabic, Alt+← in English, to the same row", async () => {
    show();
    await screen.findByTestId("viewer-dA");
    act(() => workspaceApi.open("deliverable:dA", { row: "3/02" }));
    act(() => workspaceApi.open("deliverable:dB"));
    await screen.findByTestId("viewer-dB");
    fireEvent.keyDown(document.body, { code: "ArrowLeft", key: "ArrowLeft", altKey: true }); // forward in Arabic: nothing
    expect(workspaceApi.current()?.key).toBe("deliverable:dB");
    fireEvent.keyDown(document.body, { code: "ArrowRight", key: "ArrowRight", altKey: true });
    expect(workspaceApi.current()).toEqual({ key: "deliverable:dA", anchor: { row: "3/02" } });
    await screen.findByTestId("viewer-dA");
    await waitFor(() => expect(located).toContainEqual({ row: "3/02" })); // back at the same row

    act(() => setLanguage("en"));
    act(() => workspaceApi.open("deliverable:dB"));
    fireEvent.keyDown(document.body, { code: "ArrowLeft", key: "ArrowLeft", altKey: true });
    expect(workspaceApi.current()?.key).toBe("deliverable:dA");
  });

  it("a project opens again at the saved document and its row: the row is brought into view", async () => {
    workspaceApi.reset(null, () => true);
    setCurrentProject(P1);
    core();
    const sources = fakeSources({ deliverables: [A, B], workspace: { key: "deliverable:dB", anchor: { row: "4/07" } } });
    render(<App sourcesFor={() => sources} />);
    expect(await screen.findByTestId("viewer-dB")).toBeInTheDocument();
    expect(workspaceApi.current()).toEqual({ key: "deliverable:dB", anchor: { row: "4/07" } });
    await waitFor(() => expect(located).toContainEqual({ row: "4/07" }));
    expect(sources.saved.workspace).toEqual([]); // the restore itself is not saved back
  });

  it("a Project Records hit from the palette opens its file at the hit, to be marked as a source card's is", async () => {
    setCurrentProject(P1);
    const hit = { file_id: "f1", file_name: file.name, locator: { page: 3 }, text: "خرسانة مسلحة - عينة" };
    core({ routes: { "GET /api/projects/p1/search?q=concrete&k=10": () => Response.json({ results: [hit] }) } });
    const user = userEvent.setup();
    render(<App sourcesFor={() => fakeSources({ deliverables: [A, B], files: [file] })} />);
    await screen.findByRole("heading", { level: 1 });
    fireEvent.keyDown(document, { key: "k", code: "KeyK", ctrlKey: true });
    await user.type(await screen.findByRole("combobox"), "concrete");
    await user.click(await screen.findByText("خرسانة مسلحة - عينة"));
    expect(workspaceApi.current()).toEqual({ key: "file:f1", anchor: { page: 3 } });
    expect(markFor(workspaceApi.current()!)).toEqual({ keys: sourceKeys({ fileId: "f1", locator: { page: 3 } }), figures: [] });
  });

  it("Alt+arrow in the message box moves by word there, never Back", async () => {
    show();
    act(() => workspaceApi.open("deliverable:dB"));
    const box = document.createElement("textarea");
    document.body.append(box);
    fireEvent.keyDown(box, { code: "ArrowRight", key: "ArrowRight", altKey: true });
    expect(workspaceApi.current()?.key).toBe("deliverable:dB");
    box.remove();
  });

  it("a selection in the document becomes the composer's chip, and goes when another document opens", async () => {
    setCurrentProject(P1);
    core();
    const sources = fakeSources({ deliverables: [A, B], workspace: { key: "deliverable:dA", anchor: null } });
    const user = userEvent.setup();
    render(<App sourcesFor={() => sources} />);
    await user.click(await screen.findByRole("button", { name: "select rows" }));
    expect(currentSelection()).toEqual([
      { kind: "deliverable", id: "dA", title: A.title, anchor: { row: "3/02" }, label: "البنود 3/02–3/04" },
    ]);
    const bar = screen.getByRole("region", { name: texts.commandBar.ar });
    expect(within(bar).getByText("البنود 3/02–3/04")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "clear rows" }));
    expect(currentSelection()).toEqual([]);
    await user.click(screen.getByRole("button", { name: "select rows" }));
    act(() => workspaceApi.open("deliverable:dB"));
    expect(currentSelection()).toEqual([]);
  });

  it("a source opened from its card is marked in the file: the sheet row of the file's text", async () => {
    vi.stubGlobal("matchMedia", (query: string) => ({ matches: query.includes("reduce"), media: query, addEventListener() {}, removeEventListener() {} }));
    vi.spyOn(Element.prototype, "getBoundingClientRect").mockReturnValue(new DOMRect(0, 100, 400, 40));
    const boq = { id: "boq", name: "مقايسة العميل - عينة.xlsx", status: "read" as const, note: null, replaces: null };
    const sources = fakeSources({ files: [boq], text: { boq: [{ locator: { sheet: "BOQ", row: 12 }, text: "3/02 خرسانة - عينة" }] } });
    render(<Workspace projectId="p1" sources={sources} documents={{ deliverables: [], clientBoqs: [], files: [boq], desks: [] }} />);
    act(() => openSourceFile("boq", { sheet: "BOQ", row: 12 }, ["3/02"]));
    expect(workspaceApi.current()?.key).toBe("file:boq");
    await waitFor(() => expect(document.querySelector('svg[data-source-overlay] [data-source="mark"]')).not.toBeNull());
    expect(screen.queryByText(texts.sourceNotMarked.ar)).toBeNull();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("a place that cannot be marked (a PDF page) opens the page and says so, once", async () => {
    const spec = { id: "spec", name: "المواصفات - عينة.pdf", status: "read" as const, note: null, replaces: null };
    const sources = fakeSources({ files: [spec], pages: { spec: 4 } });
    render(<Workspace projectId="p1" sources={sources} documents={{ deliverables: [], clientBoqs: [], files: [spec], desks: [] }} />);
    act(() => openSourceFile("spec", { page: 3 }, ["3,450"]));
    expect(workspaceApi.current()).toEqual({ key: "file:spec", anchor: { page: 3 } });
    expect(await screen.findAllByText(texts.sourceNotMarked.ar)).toHaveLength(1);
    act(() => workspaceApi.open("files:all"));
    await waitFor(() => expect(screen.queryByText(texts.sourceNotMarked.ar)).toBeNull());
  });

  it("an agent at work on the open document shows the switcher's dot", async () => {
    const { startActivity } = await import("../project/live/activity");
    const sources = show();
    const stop = new AbortController();
    startActivity(sources, stop.signal, { desks: [], agents: [] });
    act(() =>
      sources.emit({
        type: "agent",
        agent: {
          id: "est", kind: "specialist", role: { en: "Estimator", ar: "مهندس التسعير" }, desk_id: null, model: "m",
          state: "working", line: null, brief_id: "b1", focus: { frame: "deliverable:dA", anchor: { row: "3/02" } }, at: "",
        },
      }),
    );
    await waitFor(() => expect(screen.getByRole("heading", { level: 1 }).querySelector("[data-working-dot]")).not.toBeNull());
    stop.abort();
  });
});
