import { afterEach, describe, expect, it } from "vitest";
import { installUpsert } from "./polyfills";

type Upsert<K, V> = { getOrInsertComputed(key: K, make: (key: K) => V): V };
const natives = [Map.prototype, WeakMap.prototype].map((proto) => Object.getOwnPropertyDescriptor(proto, "getOrInsertComputed"));

afterEach(() => {
  [Map.prototype, WeakMap.prototype].forEach((proto, i) => {
    const native = natives[i];
    if (native) Object.defineProperty(proto, "getOrInsertComputed", native);
  });
});

describe("getOrInsertComputed", () => {
  it("is added where missing: computes once, then returns the stored value, on Map and WeakMap", () => {
    for (const proto of [Map.prototype, WeakMap.prototype]) delete (proto as unknown as Record<string, unknown>).getOrInsertComputed;
    installUpsert();
    const map = new Map<string, number>() as Map<string, number> & Upsert<string, number>;
    let calls = 0;
    expect(map.getOrInsertComputed("a", () => ++calls)).toBe(1);
    expect(map.getOrInsertComputed("a", () => ++calls)).toBe(1);
    expect(calls).toBe(1);
    const key = {};
    const weak = new WeakMap<object, string>() as WeakMap<object, string> & Upsert<object, string>;
    expect(weak.getOrInsertComputed(key, () => "x")).toBe("x");
    expect(weak.get(key)).toBe("x");
  });
});
