// Back: the documents the engineer left, newest last. Opened documents that are gone are skipped on the way back.
import type { DocKey, Opened } from "../project/types";

export function createHistory(limit = 50) {
  let stack: Opened[] = [];
  return {
    push(o: Opened) {
      stack.push(o);
      if (stack.length > limit) stack = stack.slice(stack.length - limit);
    },
    /** The latest document that still exists, or null when there is none. */
    pop(exists: (k: DocKey) => boolean): Opened | null {
      while (stack.length) {
        const o = stack.pop()!;
        if (exists(o.key)) return o;
      }
      return null;
    },
    clear() {
      stack = [];
    },
    drop(k: DocKey) {
      stack = stack.filter((o) => o.key !== k);
    },
    /** A document now goes by another key (a file replaced by its new version): its places are kept. */
    rename(from: DocKey, to: DocKey) {
      stack = stack.map((o) => (o.key === from ? { ...o, key: to } : o));
    },
  };
}
