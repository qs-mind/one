import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { NumberCell, Source } from "../../../deliverables/types";
import { fill, setLanguage, texts } from "../../../i18n";
import { BlockBoundary } from "./BlockBoundary";
import type { ViewBlock, ViewData } from "./types";
import { ViewPart } from "./ViewPart";

// Sample data only: a view as the core sends it, its numbers resolved to their cells and sources.
const DAY = "2026-11-02";
const quote: Source = { kind: "quote", title: "عرض سعر - عينة", file_name: "عرض سعر - عينة.xlsx", locator: { sheet: "Quote", row: 1 }, dated: DAY };
const rate: NumberCell = { value: "39850.50", unit: "m3", currency: "EGP", number_id: "n1", source: "s1", dated: DAY, calculated: false };
const quantity: NumberCell = { value: "120", unit: "m3", number_id: "n2", source: "s1", dated: DAY, calculated: false };

function viewOf(blocks: ViewBlock[], extra: Partial<ViewData> = {}): ViewData {
  return { title: "Rates summary (sample)", sample: false, blocks, sources: { s1: quote }, unsourced: [], ...extra };
}

const heading: ViewBlock = { kind: "heading", text: "Reinforced concrete (sample)" };
const prose: ViewBlock = { kind: "prose", text: "The rate is from the supplier's quote.\n\nA second paragraph." };
const figures: ViewBlock = { kind: "figures", items: [{ label: "Rate", value: rate }, { label: "Quantity", value: quantity }] };
const table: ViewBlock = {
  kind: "table",
  label_header: "Item",
  columns: [{ label: "Description" }, { label: "Rate" }],
  rows: [{ label: "03/02 (sample)", texts: ["Reinforced concrete"], numbers: [rate] }],
};
const inSection: ViewBlock[] = [
  { kind: "prose", text: "Inside the section.", section: "About the rate" },
  { kind: "prose", text: "Also inside.", section: "About the rate" },
];

function explainFetch() {
  const fetch = vi.fn(async (_input: RequestInfo | URL) =>
    Response.json({
      number: { id: "n1", name: "rate", value: "39850.50", unit: "m3", currency: "EGP", dated: DAY, recorded_by: "lead_qs" },
      source: { id: "s1", ...quote },
      calculation: null,
    }),
  );
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

beforeEach(() => setLanguage("en"));
afterEach(() => vi.restoreAllMocks());

describe("ViewPart", () => {
  it("draws each block: heading, prose, figures, table, and blocks under their section title", () => {
    render(<ViewPart view={viewOf([heading, prose, figures, table, ...inSection])} projectId="p1" />);
    const view = screen.getByRole("region", { name: "Rates summary (sample)" });
    expect(within(view).getByRole("heading", { name: "Reinforced concrete (sample)" })).toBeInTheDocument();
    expect(within(view).getByText("The rate is from the supplier's quote.")).toBeInTheDocument();
    expect(within(view).getByText("A second paragraph.")).toBeInTheDocument(); // a blank line starts a paragraph
    // the figures, exactly as the ledger holds them, never worked out on screen
    expect(within(view).getByText("Rate", { selector: "dt" })).toBeInTheDocument();
    expect(within(view).getAllByText("39,850.50 EGP/m3")).toHaveLength(2); // the figure and the table cell
    expect(within(view).getByText("120 m3")).toBeInTheDocument();
    const grid = within(view).getByRole("table");
    expect(within(grid).getByRole("columnheader", { name: "Rate" })).toBeInTheDocument();
    // a row is its label, its texts, then its numbers, under the columns in that order
    const [header, row] = within(grid).getAllByRole("row");
    // the label's header is its own field, then the columns of the texts and the numbers
    expect(within(header!).getAllByRole("columnheader").map((c) => c.textContent)).toEqual(["Item", "Description", "Rate"]);
    expect(within(row!).getByRole("rowheader", { name: "03/02 (sample)" })).toBeInTheDocument();
    const [words, number] = within(row!).getAllByRole("cell");
    expect(words).toHaveTextContent("Reinforced concrete");
    expect(within(number!).getByText("39,850.50 EGP/m3")).toBeInTheDocument();
    expect(within(grid).getByRole("columnheader", { name: "Rate" })).toHaveClass("text-end");
    // the blocks of one section stand together under its title, once
    const inner = within(view).getByRole("region", { name: "About the rate" });
    expect(within(inner).getByText("Inside the section.")).toBeInTheDocument();
    expect(within(inner).getByText("Also inside.")).toBeInTheDocument();
    expect(within(view).getAllByText("About the rate")).toHaveLength(1);
  });

  it("every number has a source chip with its source's name", () => {
    render(<ViewPart view={viewOf([figures, table])} projectId="p1" />);
    const chips = screen.getAllByRole("button", { name: fill(texts.viewSourceOf.en, { value: "39,850.50 EGP/m3" }) });
    expect(chips).toHaveLength(2);
    expect(chips[0]).toHaveTextContent("عرض سعر - عينة");
    expect(screen.getByRole("button", { name: fill(texts.viewSourceOf.en, { value: "120 m3" }) })).toBeInTheDocument();
  });

  it("a source chip opens the number's source in the source popover, and Escape closes it", async () => {
    const fetch = explainFetch();
    const user = userEvent.setup();
    render(<ViewPart view={viewOf([figures])} projectId="p1" />);
    const chip = screen.getByRole("button", { name: fill(texts.viewSourceOf.en, { value: "39,850.50 EGP/m3" }) });
    await user.click(chip);
    const popover = await screen.findByRole("dialog", { name: texts.sheetSource.en });
    expect(within(popover).getAllByText("عرض سعر - عينة").length).toBeGreaterThan(0);
    expect(String(fetch.mock.calls[0]![0])).toContain("n1");
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(chip).toHaveFocus(); // back where it was opened from
  });

  it("with no project open the chip names the source but opens nothing", () => {
    render(<ViewPart view={viewOf([figures])} />);
    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.getAllByText("عرض سعر - عينة")).toHaveLength(2);
  });

  it("a block of a kind this app does not know shows nothing, and the rest still shows", () => {
    const unknown = { kind: "chart", type: "bar" } as unknown as ViewBlock;
    render(<ViewPart view={viewOf([unknown, heading])} projectId="p1" />);
    const view = screen.getByRole("region", { name: "Rates summary (sample)" });
    expect(within(view).getByRole("heading", { name: "Reinforced concrete (sample)" })).toBeInTheDocument();
    expect(within(view).queryByText(texts.viewBlockFailed.en)).toBeNull();
    expect(view.textContent).not.toContain("chart");
  });

  it("a block that throws costs only itself: its boundary holds and the others show", () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined); // React reports the caught error
    const broken = { kind: "figures" } as unknown as ViewBlock; // no items: its renderer throws
    render(<ViewPart view={viewOf([broken, heading])} projectId="p1" />);
    expect(screen.getByText(texts.viewBlockFailed.en)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Reinforced concrete (sample)" })).toBeInTheDocument();
  });

  it("a renderer that throws is held by its own boundary", () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    const Throws = () => {
      throw new Error("sample failure");
    };
    render(<BlockBoundary block={{ kind: "bad" }} registry={{ bad: Throws }} />);
    expect(screen.getByText(texts.viewBlockFailed.en)).toBeInTheDocument();
  });

  it("an Arabic view reads right to left, even on an English page", () => {
    const arabic = viewOf(
      [
        { kind: "heading", text: "فئة الخرسانة - عينة" },
        { kind: "table", label_header: "البند", columns: [{ label: "الفئة" }], rows: [{ label: "خرسانة مسلحة - عينة", texts: [], numbers: [rate] }] },
      ],
      { title: "ملخص التسعير - عينة" },
    );
    render(<ViewPart view={arabic} projectId="p1" />);
    const view = screen.getByRole("region", { name: "ملخص التسعير - عينة" });
    expect(view).toHaveAttribute("dir", "rtl");
    expect(within(view).getByRole("columnheader", { name: "الفئة" })).toHaveClass("text-end");
    // the number and its unit keep their order: the run takes its direction from its unit (audit C17: «م3 1,200»)
    expect(within(view).getByText("39,850.50 EGP/m3")).toHaveAttribute("dir", "auto");
  });

  it("a number with an Arabic unit reads number first in an Arabic view, in one isolated run", () => {
    const cubic: NumberCell = { ...quantity, value: "1200", unit: "م3" };
    render(<ViewPart view={viewOf([{ kind: "figures", items: [{ label: "الكمية", value: cubic }] }], { title: "ملخص - عينة" })} projectId="p1" />);
    const run = screen.getByText("1,200 م3");
    expect(run.tagName).toBe("BDI");
    expect(run).toHaveAttribute("dir", "auto"); // its first strong letter is Arabic: right to left, the number first
  });

  it("a calculated number's chip says it is calculated, never its formula's raw keys", () => {
    const amount: NumberCell = { value: "102000", currency: "EGP", number_id: "n3", source: "s2", dated: DAY, calculated: true };
    const calc: Source = { kind: "calculation", title: "quantity * rate", file_name: null, locator: {}, dated: DAY };
    setLanguage("ar");
    render(<ViewPart view={viewOf([{ kind: "figures", items: [{ label: "الإجمالي", value: amount }] }], { title: "ملخص - عينة", sources: { s2: calc } })} projectId="p1" />);
    expect(screen.queryByText("quantity * rate")).toBeNull();
    expect(screen.getByRole("button", { name: fill(texts.viewSourceOf.ar, { value: "102,000 EGP" }) })).toHaveTextContent(texts.calculated.ar);
  });

  it("figure cards line up in a grid of equal columns", () => {
    render(<ViewPart view={viewOf([figures])} projectId="p1" />);
    const list = document.querySelector("dl")!;
    expect(list.className).toContain("grid");
    expect(list.className).toContain("minmax(");
  });

  it("speaks Arabic on an Arabic page", () => {
    setLanguage("ar");
    render(<ViewPart view={viewOf([figures], { title: "ملخص - عينة", sample: true })} projectId="p1" />);
    expect(screen.getByText(texts.sampleData.ar)).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: fill(texts.viewSourceOf.ar, { value: "39,850.50 EGP/m3" }) })).toHaveLength(1);
  });

  it("a sample view carries the sample-data label; a real one does not", () => {
    const { unmount } = render(<ViewPart view={viewOf([heading], { sample: true })} projectId="p1" />);
    expect(screen.getByText(texts.sampleData.en)).toBeInTheDocument();
    unmount();
    render(<ViewPart view={viewOf([heading])} projectId="p1" />);
    expect(screen.queryByText(texts.sampleData.en)).toBeNull();
  });

  it("a number in the words with no source is marked where it stands, with the note", () => {
    const words: ViewBlock = { kind: "prose", text: "The quantity is 777 m3, not 1777 m3." };
    render(<ViewPart view={viewOf([words], { unsourced: ["777"] })} projectId="p1" />);
    const [mark] = document.querySelectorAll("mark");
    expect(document.querySelectorAll("mark")).toHaveLength(1); // the whole number only, not inside 1777
    expect(mark).toHaveTextContent("777");
    expect(mark).toHaveAttribute("title", texts.noSource.en);
    expect(screen.getByText(texts.noSourceNote.en)).toBeInTheDocument();
  });
});
