import { describe, expect, it } from "vitest";
import { createHistory } from "./history";

describe("createHistory", () => {
  it("back skips documents that are gone", () => {
    const h = createHistory();
    h.push({ key: "file:a", anchor: null });
    h.push({ key: "file:gone", anchor: null });
    h.push({ key: "file:b", anchor: { page: 2 } });
    expect(h.pop((k) => k !== "file:gone")).toEqual({ key: "file:b", anchor: { page: 2 } });
    expect(h.pop((k) => k !== "file:gone")).toEqual({ key: "file:a", anchor: null });
    expect(h.pop(() => true)).toBeNull();
  });

  it("the 51st push drops the oldest", () => {
    const h = createHistory();
    for (let i = 0; i < 51; i++) h.push({ key: `file:${i}`, anchor: null });
    let last: string | undefined;
    for (let o = h.pop(() => true); o; o = h.pop(() => true)) last = o.key;
    expect(last).toBe("file:1");
  });

  it("drop and clear", () => {
    const h = createHistory();
    h.push({ key: "file:a", anchor: null });
    h.push({ key: "file:b", anchor: null });
    h.drop("file:b");
    expect(h.pop(() => true)?.key).toBe("file:a");
    h.push({ key: "file:c", anchor: null });
    h.clear();
    expect(h.pop(() => true)).toBeNull();
  });
});
