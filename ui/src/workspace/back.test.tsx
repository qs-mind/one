// Back from a source file comes back to the number's place (final review, finding 8): a number's card opens its file
// at the page, and Back returns to the same row of the sheet, the same paragraph of the letter. Real viewers, with the
// shell's mocked core; the project's lists are fake sources.
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { columns, D, DOC, entry, letter, sheet, viewRoutes } from "../deliverables/fixtures";
import type { NumberCell, Source } from "../deliverables/types";
import { setLanguage, texts } from "../i18n";
import { fakeSources } from "../project/fake";
import { setCurrentProject } from "../records/project";
import { App } from "../shell/App";
import { core, P1 } from "../shell/testing";
import { workspaceApi } from "./api";

// jsdom has no scrolling; the grid scrolls its active cell into view.
Element.prototype.scrollIntoView ??= () => {};

const quote: Source = {
  kind: "quote", title: "عرض سعر خرسانة - عينة", file_name: "عرض سعر خرسانة - عينة.pdf", file_id: "f1",
  locator: { page: 2 }, url: null, dated: "2026-11-01",
};
const SHEET = "e".repeat(32);
const ref: NumberCell = { value: "39850.50", currency: "EGP", number_id: "n-rate", source: "sq", dated: "2026-11-01" };

const col = (key: string) => columns.findIndex((c) => c.key === key) + 1;
function cellOf(code: string, key: string): HTMLElement {
  const row = screen.getAllByRole("row").find((r) => within(r).queryByText(code));
  if (!row) throw new Error(`no row ${code}`);
  return row.querySelector<HTMLElement>(`[role="gridcell"][aria-colindex="${col(key)}"]`)!;
}

function open(key: `deliverable:${string}`, routes: Record<string, unknown>) {
  setCurrentProject(P1);
  core({ routes: routes as never });
  const sources = fakeSources({
    deliverables: [entry(), entry({ id: DOC, kind: "document", title: "خطاب العطاء - عينة" })],
    files: [{ id: "f1", name: quote.file_name!, status: "read", note: null, replaces: null }],
    pages: { f1: 3 },
    workspace: { key, anchor: null },
  });
  render(<App sourcesFor={() => sources} />);
}

async function openThePageAndBack() {
  const user = userEvent.setup();
  const card = await screen.findByRole("dialog", { name: texts.sheetSource.ar });
  await user.click(await within(card).findByRole("button", { name: texts.sourceOpenPage.ar }));
  await waitFor(() => expect(workspaceApi.current()?.key).toBe("file:f1"));
  act(() => workspaceApi.back());
}

beforeEach(() => setLanguage("ar"));
afterEach(() => {
  vi.restoreAllMocks();
  setCurrentProject(undefined);
});

describe("Back from a number's source file", () => {
  it("comes back to the sheet's row", async () => {
    open(`deliverable:${D}`, viewRoutes(sheet({ sources: { ...sheet().sources, s1: quote } })));
    await screen.findByText("03/02");
    await userEvent.setup().click(cellOf("03/02", "rate"));
    await openThePageAndBack();
    expect(workspaceApi.current()).toEqual({ key: `deliverable:${D}`, anchor: { row: "p3", column: "rate" } });
  });

  it("comes back to the letter's paragraph", async () => {
    const view = letter({
      blocks: [
        { id: "b1", version: 1, node: { type: "h1", children: [{ text: "خطاب تقديم العطاء - عينة" }] } },
        {
          id: "b2", version: 1,
          node: {
            type: "p",
            children: [
              { text: "سعر الخرسانة المسلحة " },
              { type: "cell", deliverable: SHEET, row: "p3", column: "rate", children: [{ text: "" }] },
              { text: " جنيه للمتر - عينة." },
            ],
          },
        },
      ],
      refs: { [`cell:${SHEET}:p3:rate`]: ref },
      sources: { sq: quote },
    });
    open(`deliverable:${DOC}`, viewRoutes(view));
    const value = await screen.findByRole("button", { name: "39,850.50" });
    await userEvent.setup().click(value);
    await openThePageAndBack();
    expect(workspaceApi.current()).toMatchObject({ key: `deliverable:${DOC}`, anchor: { row: "b2" } });
  });
});
