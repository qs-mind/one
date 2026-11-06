import { describe, expect, it } from "vitest";
import { withoutIds } from "./ids";

const boq = "1b2746c511134ef18d8b1c38e591d9a0";
const names = new Map([[boq, "مقايسة - عينة"]]);

describe("ids in the Lead QS's words", () => {
  it("an id of a document this project has reads as its name", () => {
    expect(withoutIds(`المستند (المعرف): ${boq}`, names)).toBe("المستند مقايسة - عينة");
    expect(withoutIds(`Saved in \`${boq}\`.`, names)).toBe("Saved in `مقايسة - عينة`.");
  });

  it("any other id goes, with the words that only introduced it", () => {
    expect(withoutIds("Imported 53 items (Import ID: 8ec3c3de5f2a4b0c9d1e2f3a4b5c6d7e).", names)).toBe("Imported 53 items.");
    expect(withoutIds("الملف 8ec3c3de… فيه 54 بند", names)).toBe("الملف فيه 54 بند");
  });

  it("numbers and codes are left as written", () => {
    const text = "Item 16.8-2 is 127,000 SAR; ref A-123456; total 640983.35; DB-N4A-1F";
    expect(withoutIds(text, names)).toBe(text);
  });
});
