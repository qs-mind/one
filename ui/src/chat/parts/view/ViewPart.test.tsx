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
  columns: [
    { key: "item", label: "Item", type: "text" },
    { key: "rate", label: "Rate", type: "number" },
  ],
  rows: [{ item: "03/02 (sample)", rate }],
};
const group: ViewBlock = { kind: "group", title: "About the rate", blocks: [{ kind: "prose", text: "Inside the group." }] };

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
  it("draws each block: heading, prose, figures, table and group", () => {
    render(<ViewPart view={viewOf([heading, prose, figures, table, group])} projectId="p1" />);
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
    expect(within(grid).getByRole("cell", { name: /03\/02/ })).toBeInTheDocument();
    const inner = within(view).getByRole("region", { name: "About the rate" });
    expect(within(inner).getByText("Inside the group.")).toBeInTheDocument();
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
        { kind: "table", columns: [{ key: "item", label: "البند", type: "text" }, { key: "rate", label: "الفئة", type: "number" }], rows: [{ item: "خرسانة مسلحة - عينة", rate }] },
      ],
      { title: "ملخص التسعير - عينة" },
    );
    render(<ViewPart view={arabic} projectId="p1" />);
    const view = screen.getByRole("region", { name: "ملخص التسعير - عينة" });
    expect(view).toHaveAttribute("dir", "rtl");
    expect(within(view).getByRole("columnheader", { name: "الفئة" })).toHaveClass("text-end");
    // the number keeps its own left-to-right order inside the Arabic table
    expect(within(view).getByText("39,850.50 EGP/m3")).toHaveAttribute("dir", "ltr");
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
