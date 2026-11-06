import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ProjectStatus } from "../project/types";
import { count, setLanguage, texts } from "../i18n";
import { fitting, StatusStrip } from "./StatusStrip";

const boq = (value: string): ProjectStatus => ({
  boq_value: { value, currency: "EGP", deliverable_id: "boq1", revision: 2, status: "checked", sample: true },
});

beforeEach(() => setLanguage("en"));
afterEach(() => {
  delete (Element.prototype as { animate?: unknown }).animate;
});

describe("StatusStrip", () => {
  it("the BOQ so far rolls to the core's new total when it changes, and shows still at first", () => {
    const animate = vi.fn(() => ({ finished: new Promise(() => {}), finish() {}, cancel() {} }));
    Object.defineProperty(Element.prototype, "animate", { configurable: true, writable: true, value: animate });
    const { rerender } = render(<StatusStrip status={boq("48200000.00")} />);
    expect(animate).not.toHaveBeenCalled();
    rerender(<StatusStrip status={boq("48900000.00")} />);
    expect(animate).toHaveBeenCalled();
    const chip = screen.getByRole("button", { name: new RegExp(texts.boqSoFar.en) });
    expect(chip.querySelector(".sr-only")?.textContent).toBe(new Intl.NumberFormat("en-GB", { style: "currency", currency: "EGP", notation: "compact", maximumFractionDigits: 1 }).format(48900000));
    expect(chip).toHaveTextContent(texts.sampleData.en); // still labelled sample data
  });

  it("says what the BOQ so far covers: 4 of 325 items", () => {
    const covers = (items: number, of?: number): ProjectStatus => ({ boq_value: { ...boq("1400000.00").boq_value!, items, of } });
    const { rerender } = render(<StatusStrip status={covers(4, 325)} />);
    expect(screen.getByRole("button", { name: new RegExp(texts.boqSoFar.en) })).toHaveTextContent("4 of 325 items");
    setLanguage("ar");
    rerender(<StatusStrip status={covers(4, 325)} />);
    expect(screen.getByRole("button", { name: new RegExp(texts.boqSoFar.ar) })).toHaveTextContent("4 من 325 بند");
    rerender(<StatusStrip status={covers(6)} />);
    expect(screen.getByRole("button", { name: new RegExp(texts.boqSoFar.ar) })).toHaveTextContent("6 بنود");
  });

  it("says how many items are left to price, and nothing when all are", () => {
    const left = (priced: number): ProjectStatus => ({ boq_value: { ...boq("1104000.00").boq_value!, items: 5, priced } });
    setLanguage("ar");
    const { rerender, container } = render(<StatusStrip status={left(1)} />);
    expect(container.querySelector('[data-status="left"]')).toHaveTextContent(count("itemsLeft", 4, {}, "ar"));
    expect(count("itemsLeft", 4, {}, "ar")).toBe("فاضل 4 بنود");
    rerender(<StatusStrip status={left(5)} />);
    expect(container.querySelector('[data-status="left"]')).toBeNull();
  });
});

describe("what fits in the top bar", () => {
  // widths in priority order: the submission, the items left, the BOQ so far, the open comments
  it("all of two that fit; past two, the first two beside More status", () => {
    expect(fitting([160, 90], 300, 80)).toEqual([0, 1]);
    expect(fitting([160, 90, 380, 120], 400, 80)).toEqual([0, 1]);
  });

  it("an item too wide for the room is passed over for the next that fits (1440 px, Arabic)", () => {
    // no submission date: the BOQ so far is too wide, the items left and the open comments fit
    expect(fitting([90, 380, 120], 357, 67)).toEqual([0, 2]);
    expect(fitting([380], 300, 67)).toEqual([]);
  });

  it("never more than two", () => {
    expect(fitting([40, 40, 40, 40], 1000, 60)).toEqual([0, 1]);
  });
});
