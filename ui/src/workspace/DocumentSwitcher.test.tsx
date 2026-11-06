import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { entry } from "../deliverables/fixtures";
import { fill, setLanguage, texts } from "../i18n";
import type { ClientBoqInfo, DocKey, FileInfo } from "../project/types";
import { DocumentSwitcher } from "./DocumentSwitcher";
import { workspaceApi } from "./api";
import { openView } from "./views";

const old = entry({ id: "d-old", title: "الكميات القديمة", updated_at: "2026-11-01T09:00:00+00:00" });
const fresh = entry({ id: "d-new", title: "المقايسة المسعّرة", updated_at: "2026-11-05T09:00:00+00:00", revision: 2, sample: true });
const boq: ClientBoqInfo = { file_id: "f1", name: "عميل.xlsx", items: 3, headings: 1, at: "2026-11-02T00:00:00+00:00" };
const file: FileInfo = { id: "x", name: "جدول كميات (sample BOQ).xlsx", status: "read", note: null, replaces: null };

function show(over: Partial<Parameters<typeof DocumentSwitcher>[0]> = {}) {
  return render(
    <DocumentSwitcher
      deliverables={[old, fresh]}
      clientBoqs={[boq]}
      files={[file]}
      opened={{ key: "deliverable:d-new", anchor: null }}
      working={new Set<DocKey>()}
      {...over}
    />,
  );
}

beforeEach(() => {
  setLanguage("ar");
  workspaceApi.reset(null, () => true);
});

describe("DocumentSwitcher", () => {
  it("the head is an h1 with the title as the menu button, then the state, Revision and sample label", () => {
    show();
    const h1 = screen.getByRole("heading", { level: 1 });
    expect(within(h1).getByRole("button", { name: /المقايسة المسعّرة/ })).toBeTruthy();
    expect(h1.parentElement!.textContent).toContain(`${texts.statusDraft.ar} · ${fill(texts.docRevision.ar, { n: 2 })}`);
    expect(screen.getByText(texts.sampleNumbers.ar)).toBeTruthy();
  });

  it("no sample label for real numbers", () => {
    show({ opened: { key: "deliverable:d-old", anchor: null }, deliverables: [{ ...old, sample: false }] });
    expect(screen.queryByText(texts.sampleNumbers.ar)).toBeNull();
  });

  it("the list: Deliverables newest first, then client BOQs, then Project files", async () => {
    show();
    await userEvent.click(screen.getByRole("button", { name: /المقايسة المسعّرة/ }));
    const names = screen.getAllByRole("menuitem").map((i) => i.textContent ?? "");
    expect(names).toHaveLength(5);
    expect(names[0]).toContain("المقايسة المسعّرة");
    expect(names[1]).toContain("الكميات القديمة");
    expect(names[2]).toContain(texts.docClientBoq.ar);
    expect(names[2]).toContain("عميل.xlsx");
    expect(names[3]).toContain(texts.projectMap.ar);
    expect(names[4]).toContain(texts.projectFiles.ar);
  });

  it("picking a client BOQ opens clientboq:<id>", async () => {
    show();
    await userEvent.click(screen.getByRole("button", { name: /المقايسة المسعّرة/ }));
    await userEvent.click(screen.getByRole("menuitem", { name: /عميل\.xlsx/ }));
    expect(workspaceApi.current()?.key).toBe("clientboq:f1");
    expect(screen.queryByRole("menu")).toBeNull();
  });

  it("a working document has a dot and says it is being worked on", async () => {
    show({ working: new Set<DocKey>(["deliverable:d-old"]) });
    await userEvent.click(screen.getByRole("button", { name: /المقايسة المسعّرة/ }));
    const working = screen.getByRole("menuitem", { name: new RegExp(texts.docWorkingOn.ar) });
    expect(working.textContent).toContain("الكميات القديمة");
    expect(working.querySelector("[data-working-dot]")).toBeTruthy();
    expect(screen.getAllByRole("menuitem", { name: new RegExp(texts.docWorkingOn.ar) })).toHaveLength(1);
  });

  it("the arrow keys move between the items", async () => {
    show();
    await userEvent.click(screen.getByRole("button", { name: /المقايسة المسعّرة/ }));
    const items = screen.getAllByRole("menuitem");
    act(() => items[0]!.focus());
    await userEvent.keyboard("{ArrowDown}");
    expect(document.activeElement).toBe(items[1]);
    await userEvent.keyboard("{ArrowUp}");
    expect(document.activeElement).toBe(items[0]);
  });

  it("ArrowUp before any item is focused goes to the last item; Home and End jump", async () => {
    show();
    await userEvent.click(screen.getByRole("button", { name: /المقايسة المسعّرة/ }));
    const items = screen.getAllByRole("menuitem");
    expect(items[4]!.textContent).toContain(texts.projectFiles.ar);
    act(() => screen.getByRole("menu").focus());
    await userEvent.keyboard("{ArrowUp}");
    expect(document.activeElement).toBe(items[4]);
    await userEvent.keyboard("{Home}");
    expect(document.activeElement).toBe(items[0]);
    await userEvent.keyboard("{End}");
    expect(document.activeElement).toBe(items[4]);
  });

  it("the trigger says it opens a menu", () => {
    show();
    expect(screen.getByRole("button", { name: /المقايسة المسعّرة/ }).getAttribute("aria-haspopup")).toBe("menu");
  });

  it("Esc closes the list and focus returns to the title; Project files opens files:all", async () => {
    show();
    const title = screen.getByRole("button", { name: /المقايسة المسعّرة/ });
    await userEvent.click(title);
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("menu")).toBeNull();
    expect(document.activeElement).toBe(title);
    await userEvent.click(title);
    await userEvent.click(screen.getByRole("menuitem", { name: new RegExp(texts.projectFiles.ar) }));
    expect(workspaceApi.current()?.key).toBe("files:all");
  });

  it("the rows say Revision as the head does: «إصدار», an issued Revision, never «نسخة», a saved version", async () => {
    show();
    await userEvent.click(screen.getByRole("button", { name: /المقايسة المسعّرة/ }));
    const row = screen.getAllByRole("menuitem")[0]!;
    expect(row.textContent).toContain("إصدار 2");
    expect(row.textContent).not.toContain("نسخة 2");
  });

  it("the head of file:x shows the file's name whole", () => {
    show({ opened: { key: "file:x", anchor: null } });
    const h1 = screen.getByRole("heading", { level: 1 });
    expect(h1.textContent).toContain("جدول كميات (sample BOQ).xlsx");
    expect(h1.querySelector("bdi")).toBeTruthy();
    expect(screen.queryByText(texts.statusDraft.ar)).toBeNull();
  });

  it("renders in English", async () => {
    setLanguage("en");
    show();
    expect(screen.getByRole("heading", { level: 1 }).parentElement!.textContent).toContain("Draft · Revision 2");
    expect(screen.getByText("Sample numbers")).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: /المقايسة المسعّرة/ }));
    expect(screen.getByRole("menuitem", { name: /Project files/ })).toBeTruthy();
  });
});

it("names the sample top-items view opened as a document", () => {
  const view = { title: "Top electrical items — sample", sample: true, blocks: [], sources: {}, unsourced: [] };
  openView("sample-top-items", view);
  show({ opened: workspaceApi.current()! });
  expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(view.title);
  expect(screen.getByText(texts.sampleNumbers.ar)).toBeInTheDocument();
});


it("opens Project Map through the document switcher and names its open view", async () => {
  const {rerender} = show();
  await userEvent.click(screen.getByRole("button", {name:/المقايسة المسعّرة/}));
  await userEvent.click(screen.getByRole("menuitem", {name:texts.projectMap.ar}));
  expect(workspaceApi.current()?.key).toBe("view:project-map");
  rerender(<DocumentSwitcher deliverables={[]} clientBoqs={[]} files={[]} opened={{key:"view:project-map",anchor:null}} working={new Set()} />);
  expect(screen.getByRole("heading", {level:1})).toHaveTextContent(texts.projectMap.ar);
});
