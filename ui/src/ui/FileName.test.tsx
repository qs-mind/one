import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { FileName, splitName } from "./FileName";

describe("FileName", () => {
  it("isolates the extension left to right after the name", () => {
    expect(splitName("مواصفات - عينة اختبار (sample spec).docx")).toEqual(["مواصفات - عينة اختبار (sample spec)", ".docx"]);
    expect(splitName(".env")).toEqual([".env", ""]);
    expect(splitName("بدون امتداد")).toEqual(["بدون امتداد", ""]);
    const { container } = render(<FileName name="جدول كميات (sample BOQ).xlsx" />);
    const outer = container.firstElementChild!;
    expect(outer.tagName).toBe("BDI");
    expect(outer.getAttribute("dir")).toBe("auto");
    expect(outer.querySelector('bdi[dir="ltr"]')?.textContent).toBe(".xlsx");
    expect(outer.textContent).toBe("جدول كميات (sample BOQ).xlsx");
  });

  it("in a list keeps to one line: the stem ends in an ellipsis, the extension stays whole, the full name is its title", () => {
    const name = "جدول كميات - عينة اختبار (sample BOQ).xlsx";
    const { container } = render(<FileName name={name} fit />);
    const outer = container.firstElementChild!;
    expect(outer).toHaveAttribute("title", name);
    expect(outer).toHaveAttribute("dir", "auto");
    expect(outer).toHaveClass("inline-flex", "min-w-0", "max-w-full");
    const [stem, extension] = [...outer.children];
    expect(stem).toHaveClass("min-w-0", "truncate");
    expect(stem).toHaveTextContent("جدول كميات - عينة اختبار (sample BOQ)");
    expect(extension).toHaveAttribute("dir", "ltr");
    expect(extension).toHaveClass("shrink-0", "whitespace-nowrap");
    expect(extension).toHaveTextContent(".xlsx");
  });
});
