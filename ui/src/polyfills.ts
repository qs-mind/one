// react-data-grid calls Map/WeakMap.prototype.getOrInsertComputed (a 2026 addition). Older webviews (WebKitGTK,
// macOS Safari, older WebView2) and Node 24 lack it, so add it where it is missing.
export function installUpsert(): void {
  for (const proto of [Map.prototype, WeakMap.prototype]) {
    if ("getOrInsertComputed" in proto) continue;
    Object.defineProperty(proto, "getOrInsertComputed", {
      configurable: true,
      writable: true,
      value(this: Map<unknown, unknown>, key: unknown, make: (key: unknown) => unknown) {
        if (this.has(key)) return this.get(key);
        const value = make(key);
        this.set(key, value);
        return value;
      },
    });
  }
}

installUpsert();
