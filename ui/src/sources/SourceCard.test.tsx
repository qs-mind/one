import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { canvasApi } from "../canvas/api";
import type { Explained, NumberCell, Source } from "../deliverables/types";
import { fill, setLanguage, texts } from "../i18n";
import { DUR, EASE } from "../ui/motion";
import { SourcePopover } from "../viewers/sheet/SourcePopover";
import { dayText, figuresOf, SINK_MS, SUNK } from "./SourceCard";

const DAY = "2026-11-01";

// Numbers as the core's explain sends them; titles and values are sample data.
function number(id: string, value: string, currency: string | null = "EGP"): Explained["number"] {
  return {
    id, item: { id: "i1", code: "03/02", kind: "boq_item" }, name: "rate", value, unit: null, currency, dated: DAY,
    recorded_at: `${DAY}T08:00:00+00:00`, recorded_by: "lead_qs", current: true, replaced_by: null, reason: null,
  };
}
const rate: Explained = {
  number: number("n-rate", "39850.50"),
  source: { id: "s-calc", kind: "calculation", title: "materials + labour", file_id: null, locator: {}, url: null, dated: DAY },
  calculation: {
    id: "c1", formula: "materials + labour", unit: "EGP", stale: false, page: 1, pages: 1,
    inputs: [
      { name: "materials", seq: null, number: "n-mat", value: "31000", unit: "EGP", dated: DAY, source: { kind: "calculation", title: "cement + steel" }, calculated: true },
      { name: "labour", seq: null, number: "n-lab", value: "8850.50", unit: "EGP", dated: DAY, source: { kind: "quote", title: "عرض مقاول - عينة" }, calculated: false },
    ],
    steps: [{ n: 1, text: "materials + labour", op: "+", value: "39850.50", unit: "EGP" }],
  },
};
const materials: Explained = {
  number: number("n-mat", "31000"),
  source: { id: "s-q", kind: "quote", title: "عرض أسمنت - عينة", file_id: "f9", locator: { page: 2 }, url: null, dated: DAY },
  calculation: null,
};

function core() {
  const fetch = vi.fn(async (url: string) => {
    if (url.includes("/numbers/n-rate/")) return Response.json(rate);
    if (url.includes("/numbers/n-mat/")) return Response.json(materials);
    return new Response("{}", { status: 404 });
  });
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

/** A number in a sheet or a chat that opens its card, as the viewers do. */
function Opener({ cell, sources = {}, label }: { cell: NumberCell; sources?: Record<string, Source>; label?: string }) {
  const [from, setFrom] = useState<HTMLElement | null>(null);
  return (
    <div className="relative">
      <button type="button" data-testid="number" onClick={(e) => setFrom(e.currentTarget)}>
        <bdi dir="ltr">39,850.50</bdi>
      </button>
      {from && (
        <SourcePopover projectId="p1" cell={cell} sources={sources} style={{}} focus={false} from={from} label={label} onClose={() => setFrom(null)} />
      )}
    </div>
  );
}

const quote: Source = { kind: "quote", title: "عرض سعر - عينة", file_name: "عرض سعر - عينة.xlsx", file_id: "f1", locator: { sheet: "Quote", row: 12 }, dated: DAY, supplier: "شركة النيل - عينة" };
const cell: NumberCell = { value: "39850.50", currency: "EGP", number_id: "n-rate", source: "s1", dated: DAY };

beforeEach(() => setLanguage("ar"));
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  delete (HTMLElement.prototype as { animate?: unknown }).animate;
});

describe("a number opens in place into its source card", () => {
  it("shows what the number is, its source, the supplier, date, file and cell, and Open source", async () => {
    const user = userEvent.setup();
    core();
    render(<Opener cell={cell} sources={{ s1: quote }} label="الفئة" />);
    await user.click(screen.getByTestId("number"));
    const card = screen.getByRole("dialog", { name: texts.sheetSource.ar });
    expect(card).toHaveTextContent("الفئة");
    expect(card).toHaveTextContent("39,850.50 ج.م.");
    expect(card).toHaveTextContent("عرض سعر - عينة");
    expect(card).toHaveTextContent(fill(texts.sourceSupplier.ar, { name: "شركة النيل - عينة" }));
    expect(card).toHaveTextContent(fill(texts.sheetRow.ar, { sheet: "Quote", row: 12 }));
    expect(card).toHaveTextContent(fill(texts.sheetDated.ar, { date: dayText(DAY) }));
    const openFile = vi.spyOn(canvasApi, "openFile").mockImplementation(() => {});
    await user.click(within(card).getByRole("button", { name: texts.sourceOpenFile.ar }));
    expect(openFile).toHaveBeenCalledWith("f1", undefined);
  });

  it("is drawn in the top layer by its number, flipped above it near the window's foot, never cut by its frame", async () => {
    const user = userEvent.setup();
    core();
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (this: HTMLElement) {
      if (this.dataset.testid === "number") return new DOMRect(600, innerHeight - 60, 80, 20); // a rate near the foot
      return new DOMRect(0, 0, 0, 0);
    });
    vi.spyOn(HTMLElement.prototype, "offsetWidth", "get").mockReturnValue(320);
    vi.spyOn(HTMLElement.prototype, "scrollHeight", "get").mockReturnValue(300);
    const { container } = render(
      <div style={{ overflow: "hidden" }} data-testid="frame">
        <Opener cell={cell} sources={{ s1: quote }} />
      </div>,
    );
    await user.click(screen.getByTestId("number"));
    const card = screen.getByRole("dialog", { name: texts.sheetSource.ar });
    expect(container.contains(card)).toBe(false); // not inside the frame that would cut it
    expect(card.parentElement).toBe(document.body);
    expect(card).toHaveClass("fixed");
    expect(card.style.top).toBe(`${innerHeight - 60 - 6 - 300}px`); // above the number, whole
    expect(Number.parseFloat(card.style.maxHeight)).toBeLessThanOrEqual(innerHeight - 16);
    expect(within(card).getByRole("button", { name: texts.sourceOpenFile.ar })).toBeInTheDocument();
  });

  it("says who entered the number in words, its date in the app's style and money as the page writes it", async () => {
    const user = userEvent.setup();
    core();
    render(<Opener cell={cell} sources={{ s1: quote }} />);
    await user.click(screen.getByTestId("number"));
    const card = screen.getByRole("dialog");
    await waitFor(() => expect(card).toHaveTextContent(texts.enteredByLead.ar));
    expect(card).not.toHaveTextContent("Lead QS");
    expect(card).toHaveTextContent("1 نوفمبر 2026");
    expect(card).not.toHaveTextContent(DAY);
    expect(card).toHaveTextContent("39,850.50 ج.م.");
    expect(card).not.toHaveTextContent("EGP");
  });

  it("the number glides from where it was clicked into the header (FLIP, 300 ms, the calm ease)", async () => {
    const user = userEvent.setup();
    core();
    const animate = vi.fn(() => ({ finished: Promise.resolve(), finish() {} }));
    HTMLElement.prototype.animate = animate as unknown as typeof HTMLElement.prototype.animate;
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (this: HTMLElement) {
      if (this.dataset.cardValue !== undefined) return new DOMRect(300, 220, 100, 24);
      if (this.tagName === "BDI" && this.closest("[data-testid]")) return new DOMRect(320, 100, 80, 20);
      return new DOMRect(0, 0, 0, 0);
    });
    document.documentElement.dir = "rtl";
    render(<Opener cell={cell} sources={{ s1: quote }} />);
    await user.click(screen.getByTestId("number"));
    const value = document.querySelector<HTMLElement>("[data-card-value]")!;
    // lined up on the inline-start edge (the right in Arabic): 400 → 400, 100 − 220 up, 20/24 the size
    expect(animate).toHaveBeenCalledWith([{ transform: `translate(0px, -120px) scale(${20 / 24})` }, { transform: "none" }], { duration: DUR.long, easing: EASE });
    expect(value.style.transformOrigin).toBe("top right");
    expect((animate.mock.calls as unknown as [Keyframe[]][]).flatMap(([frames]) => frames).every((f) => Object.keys(f).every((k) => ["transform", "opacity"].includes(k)))).toBe(true);
  });

  it("Escape closes it and gives the focus back to the number, wherever the focus was", async () => {
    const user = userEvent.setup();
    core();
    render(<Opener cell={cell} sources={{ s1: quote }} />);
    await user.click(screen.getByTestId("number"));
    (document.activeElement as HTMLElement).blur(); // WebKit never focuses a clicked button
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.getByTestId("number")).toHaveFocus();
    await user.click(screen.getByTestId("number"));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: texts.close.ar }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.getByTestId("number")).toHaveFocus();
  });

  it("a rate's build-up opens level by level, the one under sinking behind; Back says where it goes and works", async () => {
    const user = userEvent.setup();
    core();
    const animate = vi.fn(() => ({ finished: Promise.resolve(), finish() {} }));
    HTMLElement.prototype.animate = animate as unknown as typeof HTMLElement.prototype.animate;
    render(<Opener cell={{ ...cell, source: null }} />);
    await user.click(screen.getByTestId("number"));
    const card = screen.getByRole("dialog");
    await waitFor(() => expect(card).toHaveTextContent("materials + labour"));
    await user.click(within(card).getByRole("button", { name: /materials/ }));
    await waitFor(() => expect(card).toHaveTextContent("عرض أسمنت - عينة"));
    expect(document.querySelector("[data-card-value]")).toHaveTextContent("31,000 ج.م.");
    const [first, second] = [...card.querySelectorAll<HTMLElement>("[data-level]")];
    expect(first!.style.transform).toBe(SUNK);
    expect(first).toHaveAttribute("aria-hidden", "true");
    expect(second).not.toHaveAttribute("aria-hidden");
    expect(animate).toHaveBeenCalledWith([{ transform: "none", opacity: 1 }, { transform: SUNK, opacity: 0.5 }], { duration: SINK_MS, easing: EASE });
    await user.click(within(card).getByRole("button", { name: fill(texts.sourceBackTo.ar, { value: "39,850.50 ج.م." }) }));
    expect(card.querySelectorAll("[data-level]")).toHaveLength(1);
    expect(document.querySelector("[data-card-value]")).toHaveTextContent("39,850.50 ج.م.");
    expect(within(card).queryByRole("button", { name: /ارجع/ })).toBeNull();
    expect(animate).toHaveBeenLastCalledWith([{ transform: SUNK, opacity: 0.5 }, { transform: "none", opacity: 1 }], { duration: SINK_MS, easing: EASE });
  });

  it("with reduced motion it opens and goes in its end state at once", async () => {
    const user = userEvent.setup();
    core();
    vi.stubGlobal("matchMedia", vi.fn(() => ({ matches: true, addEventListener() {}, removeEventListener() {} })));
    const animate = vi.fn();
    HTMLElement.prototype.animate = animate as unknown as typeof HTMLElement.prototype.animate;
    render(<Opener cell={cell} sources={{ s1: quote }} />);
    await user.click(screen.getByTestId("number"));
    expect(screen.getByRole("dialog")).toHaveTextContent("عرض سعر - عينة");
    expect(animate).not.toHaveBeenCalled();
  });

  it("a number with no source says so, and offers nothing to open", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("fetch", vi.fn(async () => new Response("{}", { status: 404 })));
    render(<Opener cell={{ value: "120", number_id: null, source: null, dated: null }} />);
    await user.click(screen.getByTestId("number"));
    const card = screen.getByRole("dialog");
    expect(card).toHaveTextContent(texts.noSource.ar);
    expect(within(card).queryByRole("button", { name: texts.sourceOpenFile.ar })).toBeNull();
  });

  it("a price said in the chat says so", async () => {
    const user = userEvent.setup();
    render(<Opener cell={{ value: "3950", currency: "EGP", number_id: null, source: "r0", dated: DAY }} sources={{ r0: { kind: "chat", title: "", locator: {}, dated: DAY } }} />);
    await user.click(screen.getByTestId("number"));
    expect(screen.getByRole("dialog")).toHaveTextContent(texts.sourceSaidInChat.ar);
  });
});

describe("the figure as a file writes it", () => {
  it("is looked for with and without grouping and trailing zeros", () => {
    expect(figuresOf("39850.50")).toEqual(["39,850.50", "39850.50", "39850.5", "39,850.5"]);
    expect(figuresOf("120")).toEqual(["120"]);
  });
});
