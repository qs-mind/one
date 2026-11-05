import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ProjectStatus } from "../canvas/types";
import { setLanguage, texts } from "../i18n";
import { StatusStrip } from "./StatusStrip";

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
});
