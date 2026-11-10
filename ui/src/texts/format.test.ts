import { describe, expect, it } from "vitest";
import { common } from "./common";
import { formatDate, formatNumber, intlLocale } from "./format";
import { plural, text } from "./useText";

const EASTERN_DIGITS = /[٠-٩۰-۹]/;

describe("format", () => {
  it("fixes the locale: Western digits, Gregorian calendar", () => {
    expect(intlLocale("ar")).toBe("ar-u-nu-latn");
    expect(intlLocale("en")).toBe("en-GB");
  });

  it("formats numbers with Western digits and keeps the minus on the left in Arabic", () => {
    expect(formatNumber(-1800, "ar")).toBe("‎-1,800");
    expect(formatNumber(2203200, "en")).toBe("2,203,200");
    for (const value of [0, 7, 1234.5, -98765, 2203200]) {
      expect(formatNumber(value, "ar")).not.toMatch(EASTERN_DIGITS);
      expect(formatNumber(value, "en")).not.toMatch(EASTERN_DIGITS);
    }
  });

  it("formats dates as day and month name", () => {
    const date = new Date(2026, 10, 21);
    expect(formatDate(date, "ar")).toBe("21 نوفمبر");
    expect(formatDate(date, "en")).toBe("21 November");
    expect(formatDate(date, "ar", { year: "numeric", month: "numeric", day: "numeric" })).not.toMatch(EASTERN_DIGITS);
  });
});

describe("text and plural", () => {
  it("isolates a number and a string value, and throws on a missing value", () => {
    expect(text(common.stepOf, "en", { step: 2, total: 3 })).toBe("Step ⁦2⁩ of ⁦3⁩");
    expect(text({ en: "Hi {name}", ar: "أهلا {name}" }, "ar", { name: "Lead QS" })).toBe("أهلا ⁨Lead QS⁩");
    expect(() => text(common.stepOf, "en", { step: 2 })).toThrow(/total/);
  });

  it("picks the Arabic plural forms one, two, few and many", () => {
    expect(plural(common.daysLeft, 1, "ar")).toBe("باقي يوم");
    expect(plural(common.daysLeft, 2, "ar")).toBe("باقي يومين");
    expect(plural(common.daysLeft, 5, "ar")).toBe("باقي ⁦5⁩ أيام");
    expect(plural(common.daysLeft, 12, "ar")).toBe("باقي ⁦12⁩ يوم");
    expect(plural(common.daysLeft, 1, "en")).toBe("⁦1⁩ day left");
    expect(plural(common.daysLeft, 12, "en")).toBe("⁦12⁩ days left");
  });
});
