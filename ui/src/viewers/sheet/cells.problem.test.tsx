// A row whose records hold two current numbers of one name shows the core's plain-words problem on its code cell
// (tender day, 5 Nov 2026: the priced BOQ did not open at all, a raw error with hex ids).
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import type { ViewColumn, ViewRow } from "../../deliverables/types";
import { setLanguage } from "../../i18n";
import { SheetCell } from "./cells";

const column = { key: "code", from: "code", label: { en: "Item", ar: "البند" }, kind: "text" } as unknown as ViewColumn;
const row = (problem?: { en: string; ar: string }): ViewRow =>
  ({ id: "r1", kind: "item", item_id: "i1", version: 1, code: "1-1", cells: {}, problem }) as ViewRow;
const cell = (r: ViewRow) => (
  <SheetCell
    row={r}
    column={column}
    titleColumn="description"
    direction="rtl"
    pending={undefined}
    marks={undefined}
    collapsed={false}
    onToggle={() => undefined}
    onAccept={() => undefined}
    onReject={() => undefined}
  />
);

beforeEach(() => setLanguage("ar"));

describe("a row with a problem", () => {
  it("says it in plain words on the code cell", () => {
    render(cell(row({ en: "Two rates: 14, 15.", ar: "فئتين: 14 و15." })));
    expect(screen.getByText("1-1")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "فئتين: 14 و15." })).toBeInTheDocument();
  });

  it("shows nothing more without one", () => {
    render(cell(row()));
    expect(screen.queryByRole("img")).toBeNull();
  });
});
