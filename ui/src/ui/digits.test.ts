// @vitest-environment jsdom
import { describe, expect, it } from "vitest";
import { perMillion, usd, westernNumbers } from "./digits";
import { setLanguage } from "../i18n";

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

describe("a model's price", () => {
  it("reads «$1.50», at least two decimals, the exact text kept, isolated so Arabic never turns it («1.5$»)", () => {
    expect(usd("1.5")).toBe("⁦$1.50⁩");
    expect(usd("0.25")).toBe("⁦$0.25⁩");
    expect(usd("3")).toBe("⁦$3.00⁩");
    expect(usd("0.075")).toBe("⁦$0.075⁩");
  });

  it("one line in both languages: «$0.25 داخل / $1.50 خارج لكل مليون توكن»", () => {
    setLanguage("ar");
    expect(perMillion("0.25", "1.5")).toBe(`${usd("0.25")} داخل / ${usd("1.5")} خارج لكل مليون توكن`);
    setLanguage("en");
    expect(perMillion("0.25", "1.5")).toBe(`${usd("0.25")} in / ${usd("1.5")} out per million tokens`);
  });
});
