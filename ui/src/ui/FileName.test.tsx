import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { FileName, nameParts, splitName } from "./FileName";
import { TIP_DELAY } from "./Tip";

afterEach(() => vi.useRealTimers());

describe("FileName", () => {
  it("isolates the extension left to right after the name", () => {
    expect(splitName("مواصفات - عينة اختبار (sample spec).docx")).toEqual(["مواصفات - عينة اختبار (sample spec)", ".docx"]);
    expect(splitName(".env")).toEqual([".env", ""]);
    expect(splitName("بدون امتداد")).toEqual(["بدون امتداد", ""]);
    const { container } = render(<FileName name="مواصفات.docx" />);
    const outer = container.firstElementChild!;
    expect(outer.tagName).toBe("BDI");
    expect(outer.getAttribute("dir")).toBe("auto");
    expect(outer.querySelector('bdi[dir="ltr"]')?.textContent).toBe(".docx");
    expect(outer.textContent).toBe("مواصفات.docx");
  });

  it("keeps the Latin words at the end of an Arabic name with the extension, one left-to-right run (never «.docx(sample spec»)", () => {
    expect(nameParts("مواصفات - عينة اختبار (sample spec).docx")).toEqual({
      head: "مواصفات - عينة اختبار ",
      tail: "(sample spec)",
      extension: ".docx",
    });
    // a Latin name, or an Arabic one with no Latin end, reads as it is
    expect(nameParts("Al Andalus BOQ.xlsx")).toEqual({ head: "Al Andalus BOQ", tail: "", extension: ".xlsx" });
    expect(nameParts("جدول كميات 2026.xlsx")).toEqual({ head: "جدول كميات 2026", tail: "", extension: ".xlsx" });
    expect(nameParts("Tower B2 - برج الأندلس")).toEqual({ head: "Tower B2 - برج الأندلس", tail: "", extension: "" });
    // a title made of a name: the same
    expect(nameParts("مقايسة العميل — جدول كميات - عينة اختبار (sample BOQ).xlsx").tail).toBe("(sample BOQ)");

    const { container } = render(<FileName name="جدول كميات (sample BOQ).xlsx" />);
    const outer = container.firstElementChild!;
    expect(outer).toHaveAttribute("dir", "auto");
    expect(outer.querySelector('bdi[dir="ltr"]')?.textContent).toBe("(sample BOQ).xlsx");
    expect(outer.textContent).toBe("جدول كميات (sample BOQ).xlsx");
  });

  it("in a list keeps to one line: the words end in an ellipsis, the extension stays whole", () => {
    const name = "جدول كميات - عينة اختبار (sample BOQ).xlsx";
    const { container } = render(<FileName name={name} fit />);
    const outer = container.querySelector("[data-file-name]")!;
    expect(outer.tagName).toBe("BDI");
    expect(outer).toHaveAttribute("dir", "auto");
    expect(outer).toHaveClass("inline-flex", "min-w-0", "max-w-full");
    const [head, tail] = [...outer.children];
    expect(head).toHaveClass("min-w-0", "truncate");
    expect(head).toHaveTextContent("جدول كميات - عينة اختبار");
    expect(tail).toHaveAttribute("dir", "ltr");
    expect(tail).toHaveTextContent("(sample BOQ).xlsx");
    const extension = tail!.lastElementChild!;
    expect(extension).toHaveClass("shrink-0", "whitespace-nowrap");
    expect(extension).toHaveTextContent(".xlsx");
    expect(outer.textContent).toBe(name);
  });

  it("shows the full name in a Tip only while it is cut", () => {
    vi.useFakeTimers();
    const name = "جدول كميات - عينة اختبار (sample BOQ).xlsx";
    const { container } = render(<FileName name={name} fit />);
    const outer = container.querySelector("[data-file-name]")!;
    fireEvent.pointerEnter(outer);
    act(() => void vi.advanceTimersByTime(TIP_DELAY + 10));
    expect(screen.queryByRole("tooltip", { hidden: true })).toBeNull(); // it all fits (jsdom lays out nothing)
    fireEvent.pointerLeave(outer);

    const head = outer.firstElementChild as HTMLElement;
    Object.defineProperty(head, "scrollWidth", { value: 300, configurable: true });
    Object.defineProperty(head, "clientWidth", { value: 120, configurable: true });
    fireEvent.pointerEnter(outer);
    act(() => void vi.advanceTimersByTime(TIP_DELAY + 10));
    expect(screen.getByRole("tooltip", { hidden: true })).toHaveTextContent(name);
  });
});
