// Layout saves, batched (decision 4): frames 500 ms after the last change, the view 1 s after the last pan or zoom,
// merged per frame. `flush` sends what is waiting at once (project switch, pagehide with keepalive). Nothing goes to
// web storage: the layout lives only in the project's encrypted file.
import type { FrameKey, Placed, ProjectSources, View } from "./types";

export type Saver = {
  frames(changed: readonly Placed[], removed: readonly FrameKey[]): void;
  view(view: View): void;
  flush(keepalive?: boolean): void;
};

export function createSaver(
  sources: Pick<ProjectSources, "saveFrames" | "saveView">,
  { frameDelay = 500, viewDelay = 1000 } = {},
): Saver {
  let changed = new Map<FrameKey, Placed>();
  let removed = new Set<FrameKey>();
  let view: View | null = null;
  let frameTimer: ReturnType<typeof setTimeout> | undefined;
  let viewTimer: ReturnType<typeof setTimeout> | undefined;

  function merge(frames: Iterable<Placed>, gone: Iterable<FrameKey>) {
    for (const key of gone) {
      changed.delete(key);
      removed.add(key);
    }
    for (const f of frames) {
      removed.delete(f.key);
      changed.set(f.key, f);
    }
  }

  function sendFrames(keepalive: boolean) {
    clearTimeout(frameTimer);
    frameTimer = undefined;
    if (changed.size === 0 && removed.size === 0) return;
    const frames = [...changed.values()];
    const gone = [...removed];
    changed = new Map();
    removed = new Set();
    sources.saveFrames(frames, gone, keepalive).catch(() => {
      // the core did not take it: send it again with the next save, unless something newer replaced it
      const newer = { changed, removed };
      changed = new Map();
      removed = new Set();
      merge(frames, gone);
      merge(newer.changed.values(), newer.removed);
    });
  }

  function sendView(keepalive: boolean) {
    clearTimeout(viewTimer);
    viewTimer = undefined;
    if (!view) return;
    const v = view;
    view = null;
    sources.saveView(v, keepalive).catch(() => {
      view ??= v;
    });
  }

  return {
    frames(frames, gone) {
      merge(frames, gone);
      clearTimeout(frameTimer);
      frameTimer = setTimeout(() => sendFrames(false), frameDelay);
    },
    view(v) {
      view = v;
      clearTimeout(viewTimer);
      viewTimer = setTimeout(() => sendView(false), viewDelay);
    },
    flush(keepalive = false) {
      sendFrames(keepalive);
      sendView(keepalive);
    },
  };
}
