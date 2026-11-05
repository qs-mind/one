import { expect, test } from "vitest";
import { ALLOW, gate, licenceOf, permissive } from "./notices.mjs";

test("the gate refuses GPL and lets an allowed package through with its reason", () => {
  expect(() => gate([{ name: "x", licence: "GPL-3.0-only" }], {})).toThrow(/x.*GPL/);
  expect(gate([{ name: "y", licence: "LGPL-2.1" }], { y: "not shipped: build tool only" })).toBeTruthy();
  expect(gate([{ name: "y", licence: "LGPL-2.1" }], { y: "not shipped: build tool only" })[0].allowed).toMatch(/build tool/);
});

test("the gate refuses AGPL, SSPL, a classifier's words and a missing licence, and names every one", () => {
  const list = [
    { name: "a", licence: "AGPL-3.0-or-later" },
    { name: "b", licence: "SSPL-1.0" },
    { name: "c", licence: "GNU Library or Lesser General Public License (LGPL)" },
    { name: "d", licence: "" },
    { name: "e", licence: "MIT" },
  ];
  expect(() => gate(list, {})).toThrow(/a \(AGPL.*b \(SSPL.*c \(GNU.*d \(no licence found\)/);
  expect(() => gate(list, { a: "", b: " " })).toThrow(/a \(AGPL/); // a reason is required
});

test("a choice that includes a permissive licence passes; a conjunction with GPL does not", () => {
  expect(permissive("MIT OR Apache-2.0 OR LGPL-2.1-or-later")).toBe(true);
  expect(permissive("(MIT OR Apache-2.0) AND Unicode-3.0")).toBe(true);
  expect(permissive("Apache-2.0 WITH LLVM-exception")).toBe(true);
  expect(permissive("MPL-2.0 AND MIT")).toBe(true);
  expect(permissive("MIT AND GPL-2.0-only")).toBe(false);
  expect(permissive("(GPL-2.0-only OR GPL-3.0-only) AND MIT")).toBe(false);
  expect(permissive("")).toBe(false);
});

test("licenceOf reads Python, npm and Cargo metadata", () => {
  expect(licenceOf({ license_expression: "BSD-3-Clause", license: "ignored" })).toBe("BSD-3-Clause");
  expect(licenceOf({ license: "MIT" })).toBe("MIT");
  expect(licenceOf({ license: "Long\nlicence text pasted into the field", classifiers: ["License :: OSI Approved :: BSD License"] })).toBe("BSD License");
  expect(licenceOf({ license: "UNKNOWN", classifiers: ["License :: OSI Approved :: MIT License", "Programming Language :: Python"] })).toBe("MIT License");
  expect(licenceOf({ licenses: [{ type: "MIT" }, { type: "Apache-2.0" }] })).toBe("MIT OR Apache-2.0");
  expect(licenceOf({ license: "MIT/Apache-2.0", cargo: true })).toBe("MIT OR Apache-2.0");
  expect(licenceOf({})).toBe("");
});

test("every allowed package says why", () => {
  for (const [name, reason] of Object.entries(ALLOW)) expect(reason.trim().length, name).toBeGreaterThan(10);
});
