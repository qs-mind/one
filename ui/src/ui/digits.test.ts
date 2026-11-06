import { describe, expect, it } from "vitest";
import { westernNumbers } from "./digits";

describe("numbers on screen", () => {
  it("Arabic-Indic digits and separators read as Western digits with , and .", () => {
    expect(westernNumbers("الإجمالي ٦٤٠٬٩٨٣٫٣٥ جنيه")).toBe("الإجمالي 640,983.35 جنيه");
    expect(westernNumbers("640٬983٫35")).toBe("640,983.35");
    expect(westernNumbers("۱۲۳٫۵")).toBe("123.5");
  });

  it("leaves Western numbers and words as written", () => {
    const text = "Total 640,983.35 EGP, item 16.8-2، والبند ٣";
    expect(westernNumbers("Total 640,983.35 EGP, item 16.8-2")).toBe("Total 640,983.35 EGP, item 16.8-2");
    expect(westernNumbers(text)).toBe("Total 640,983.35 EGP, item 16.8-2، والبند 3");
  });
});
