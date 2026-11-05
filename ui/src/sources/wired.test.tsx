// The source line, mark and card where the numbers are: a chat reply, a price card's rows, a sheet cell, a
// document reference, a file's frame. Values and titles are sample data.
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Reply } from "../chat/Reply";
import { RowsCard } from "../chat/parts/RowsCard";
import type { CardData } from "../chat/parts/types";
import { canvasApi } from "../canvas/api";
import type { Explained, ViewColumn, ViewRow } from "../deliverables/types";
import { fill, setLanguage, texts } from "../i18n";
import { NumberRef } from "../viewers/document/NumberRef";
import { SheetCell } from "../viewers/sheet/cells";
import { hideSourceLine } from "./line";
import { REVEAL_WAIT_MS } from "./mark";

const DAY = "2026-11-04";
const line = () => document.querySelector('svg[data-source-overlay] [data-source="line"]');
const mark = () => document.querySelector('svg[data-source-overlay] [data-source="mark"]');

/** Gives elements matching `selector` a box on screen (jsdom has no layout). */
function laidOut(boxes: [string, DOMRect][]) {
  vi.spyOn(Element.prototype, "getBoundingClientRect").mockImplementation(function (this: Element) {
    for (const [selector, rect] of boxes) if (this.matches(selector)) return rect;
    return new DOMRect(0, 0, 0, 0);
  });
}

beforeEach(() => setLanguage("ar"));
afterEach(() => {
  hideSourceLine();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  document.body.innerHTML = "";
});

// What prices_propose sends (core/qsone/tools/prices.py): each rate's source, from a quote's row or the chat.
const prices: CardData = {
  kind: "rows",
  title: { en: "Keep these prices?", ar: "أحفظ الأسعار دي؟" },
  detail: { en: "Tick the rows to keep.", ar: "علّم على الصفوف اللي تتحفظ." },
  options: ["keep", "no"],
  status: "pending",
  payload: {
    columns: [
      { key: "description", label: { en: "Item", ar: "البند" } },
      { key: "rate", label: { en: "Rate", ar: "السعر" } },
    ],
    rows: [
      { description: "أسمنت - عينة", rate: "3950", currency: "EGP" },
      { description: "رمل - عينة", rate: "250", currency: "EGP" },
    ],
    number_column: "rate",
    row_sources: [
      { kind: "quote", title: "عرض سعر - عينة.xlsx", file_id: "f1", locator: { sheet: "Quote", row: 2, dated_how: "document" }, dated: DAY, supplier: "مصنع - عينة" },
      { kind: "chat", title: "", locator: {}, dated: DAY, supplier: null },
    ],
    tick: true,
  },
};

describe("a price card's rates", () => {
  it("open in place into their source card: the quote, its row, the supplier and the date, and Open source marks the row", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("matchMedia", vi.fn(() => ({ matches: true, addEventListener() {}, removeEventListener() {} })));
    render(<RowsCard card={prices} onAnswer={() => undefined} sending={false} label={(o) => o} lang="ar" />);
    const rate = screen.getByRole("button", { name: fill(texts.sourceOfNumber.ar, { value: "3950" }) });
    await user.click(rate);
    const card = screen.getByRole("dialog", { name: texts.sheetSource.ar });
    expect(card).toHaveTextContent("السعر");
    expect(card).toHaveTextContent("3,950 EGP");
    expect(card).toHaveTextContent("عرض سعر - عينة.xlsx");
    expect(card).toHaveTextContent(fill(texts.sheetRow.ar, { sheet: "Quote", row: 2 }));
    expect(card).toHaveTextContent(fill(texts.sourceSupplier.ar, { name: "مصنع - عينة" }));
    expect(card).toHaveTextContent(fill(texts.sheetDated.ar, { date: DAY }));
    const openFile = vi.spyOn(canvasApi, "openFile").mockImplementation(() => {
      // the canvas opens the file's frame, and its text shows the quote's row
      const li = document.createElement("li");
      li.setAttribute("data-source-at", "file:f1#sheet=Quote&row=2");
      li.textContent = "أسمنت - عينة طن 3950";
      document.body.append(li);
    });
    laidOut([['li[data-source-at="file:f1#sheet=Quote&row=2"]', new DOMRect(40, 300, 400, 30)]]);
    await user.click(within(card).getByRole("button", { name: texts.sourceOpenFile.ar }));
    expect(openFile).toHaveBeenCalledWith("f1", undefined);
    await waitFor(() => expect(mark()).not.toBeNull(), { timeout: REVEAL_WAIT_MS });
  });

  it("a rate said in the chat says so, and a card with no sources has no buttons", async () => {
    const user = userEvent.setup();
    const { unmount } = render(<RowsCard card={prices} onAnswer={() => undefined} sending={false} label={(o) => o} lang="ar" />);
    await user.click(screen.getByRole("button", { name: fill(texts.sourceOfNumber.ar, { value: "250" }) }));
    expect(screen.getByRole("dialog")).toHaveTextContent(texts.sourceSaidInChat.ar);
    unmount();
    const plain = { ...prices, payload: { ...prices.payload, number_column: undefined, row_sources: undefined } };
    render(<RowsCard card={plain} onAnswer={() => undefined} sending={false} label={(o) => o} lang="ar" />);
    expect(screen.queryByRole("button", { name: /مصدر/ })).toBeNull();
  });
});

describe("a chat reply's numbers", () => {
  const rate: Explained = {
    number: { id: "n-rate", item: { id: "i1", code: "03/02", kind: "boq_item" }, name: "rate", value: "39850.50", unit: null, currency: "EGP", dated: DAY, recorded_at: `${DAY}T08:00:00+00:00`, recorded_by: "lead_qs", current: true, replaced_by: null, reason: null },
    source: { id: "s1", kind: "quote", title: "عرض سعر - عينة", file_id: "f1", locator: { page: 3 }, url: null, dated: DAY },
    calculation: null,
  };

  it("a number one ledger number gave opens into its source card; an unsourced one stays marked", async () => {
    const user = userEvent.setup();
    const fetch = vi.fn(async (_url: string) => Response.json(rate));
    vi.stubGlobal("fetch", fetch);
    const { container } = render(
      <Reply
        text="الفئة 39,850.50 جنيه، والنقل 7,500 جنيه - عينة"
        unsourced={["7,500"]}
        sourced={{ "39,850.50": { id: "n-rate", value: "39850.50" } }}
        projectId="p1"
      />,
    );
    expect(container.querySelector("mark")).toHaveTextContent("7,500");
    await user.click(screen.getByRole("button", { name: fill(texts.sourceOfNumber.ar, { value: "39,850.50" }) }));
    const card = screen.getByRole("dialog");
    await waitFor(() => expect(card).toHaveTextContent("عرض سعر - عينة"));
    expect(card).toHaveTextContent(fill(texts.page.ar, { page: 3 }));
    expect(String(fetch.mock.calls[0]![0])).toContain("/projects/p1/numbers/n-rate/explain");
  });

  it("hovering it draws its source line to the same ledger number in a sheet on screen, and nothing when none is", () => {
    render(<Reply text="الفئة 39,850.50 جنيه - عينة" sourced={{ "39,850.50": { id: "n-rate", value: "39850.50" } }} projectId="p1" />);
    const number = screen.getByRole("button", { name: fill(texts.sourceOfNumber.ar, { value: "39,850.50" }) });
    laidOut([
      ["button", new DOMRect(700, 100, 70, 20)],
      ['[data-source-at="number:n-rate"]', new DOMRect(100, 400, 80, 30)],
    ]);
    fireEvent.pointerEnter(number);
    expect(line()).toBeNull(); // the number is not on screen anywhere else
    fireEvent.pointerLeave(number);
    const cell = document.createElement("span");
    cell.setAttribute("data-source-at", "number:n-rate");
    document.body.append(cell);
    fireEvent.pointerEnter(number);
    expect(line()).not.toBeNull();
    fireEvent.pointerLeave(number);
  });

  it("outside a project nothing opens", () => {
    render(<Reply text="الفئة 39,850.50 جنيه - عينة" sourced={{ "39,850.50": { id: "n-rate", value: "39850.50" } }} />);
    expect(screen.queryByRole("button")).toBeNull();
  });
});

describe("a sheet cell and a document reference", () => {
  const column: ViewColumn = { key: "rate", label: { en: "Rate", ar: "الفئة" }, kind: "number", edit: true, frozen: false, wrap: false, width: 120 };
  const row: ViewRow = { id: "p1", kind: "item", item_id: "i1", version: 1, code: "03/02", cells: { rate: { value: "39850.50", currency: "EGP", number_id: "n-rate", source: "s1", dated: DAY } } };
  const cellProps = { row, column, titleColumn: undefined, direction: "rtl" as const, pending: undefined, marks: undefined, collapsed: false, onToggle() {}, onAccept() {}, onReject() {} };

  it("a sheet number shows where its ledger number is, and hovering it draws its line to its file's row on the canvas", () => {
    const { container } = render(<SheetCell {...cellProps} sourceKeys={["file:f1#sheet=Quote&row=2", "file:f1"]} />);
    const number = container.querySelector<HTMLElement>('[data-source-at="number:n-rate"]')!;
    expect(number).toHaveTextContent("39,850.50");
    const li = document.createElement("li");
    li.setAttribute("data-source-at", "file:f1#sheet=Quote&row=2");
    document.body.append(li);
    laidOut([
      ['[data-source-at="number:n-rate"]', new DOMRect(700, 100, 70, 20)],
      ["li", new DOMRect(100, 400, 300, 30)],
    ]);
    fireEvent.pointerEnter(number);
    expect(line()).not.toBeNull();
    fireEvent.pointerLeave(number);
  });

  it("a number with no source draws no line", () => {
    const bare: ViewRow = { ...row, cells: { rate: { value: "39850.50", number_id: "n-x", source: null, dated: null } } };
    const { container } = render(<SheetCell {...cellProps} row={bare} sourceKeys={[]} />);
    const frame = document.createElement("div");
    frame.dataset.frame = "file:f1";
    document.body.append(frame);
    laidOut([["span, div", new DOMRect(100, 100, 300, 30)]]);
    fireEvent.pointerEnter(container.querySelector('[data-source-at="number:n-x"]')!);
    expect(line()).toBeNull();
  });

  it("a document reference is a place a number shows, and draws its line on focus", () => {
    render(<NumberRef value={{ value: "120", unit: "m3", number_id: "n-q", source: "s2", dated: DAY }} onOpen={() => undefined} sourceKeys={["file:f2#page=4", "file:f2"]} />);
    const ref = screen.getByRole("button");
    expect(ref).toHaveAttribute("data-source-at", "number:n-q");
    const img = document.createElement("img");
    img.setAttribute("data-source-at", "file:f2#page=4");
    document.body.append(img);
    laidOut([
      ["button", new DOMRect(700, 100, 40, 20)],
      ["img", new DOMRect(50, 50, 400, 560)],
    ]);
    fireEvent.focus(ref);
    expect(line()).not.toBeNull();
    fireEvent.blur(ref);
  });
});
