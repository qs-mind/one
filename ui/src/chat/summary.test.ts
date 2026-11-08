// A reply shows its summary; the rest folds under Details (Kareem, 8 Nov).
import { describe, expect, it } from "vitest";
import { splitSummary } from "./Chat";

describe("a reply's summary", () => {
  it("a short reply is all summary", () => {
    expect(splitSummary("Read 7 files.\n\nOne question: import the 21 items?")).toEqual(["Read 7 files.\n\nOne question: import the 21 items?", ""]);
  });

  it("whole paragraphs up to about four lines; the rest is details", () => {
    const first = "Read 7 files: 1 estimate (21 items), 1 drawing, 4 photos.";
    const long = "x".repeat(400);
    expect(splitSummary(`${first}\n\n${long}\n\nmore`)).toEqual([first, `${long}\n\nmore`]);
  });

  it("one long first list shows its first lines", () => {
    const list = Array.from({ length: 20 }, (_, i) => `- item ${i} ${"w".repeat(40)}`).join("\n");
    const [summary, rest] = splitSummary(list);
    expect(summary.split("\n").length).toBeLessThan(8);
    expect(`${summary}\n${rest}`).toBe(list);
  });
});
