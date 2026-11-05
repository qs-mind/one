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
});
