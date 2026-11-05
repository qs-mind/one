// What the rest of the screen asks of the canvas (the chat's Open, the palette, the command bar). The mounted canvas
// registers the real functions; with no canvas on screen every call does nothing.
import type { Anchor, FrameKey, Placed } from "../project/types";

export type CanvasApi = {
  /** `mark`: the frame shows where the view went (a soft outline that fades), when sent there from elsewhere. */
  focusFrame(key: FrameKey, opts?: { anchor?: Anchor; zoom?: number; mark?: boolean }): void;
  fitAll(): void;
  zoomTo(level: number): void;
  openFile(fileId: string, page?: number): void;
  arrange(mode: "stage" | "tidy"): void;
  frames(): Placed[];
};

const idle: CanvasApi = {
  focusFrame() {},
  fitAll() {},
  zoomTo() {},
  openFile() {},
  arrange() {},
  frames: () => [],
};

let mounted: CanvasApi = idle;

export const canvasApi: CanvasApi = {
  focusFrame: (key, opts) => mounted.focusFrame(key, opts),
  fitAll: () => mounted.fitAll(),
  zoomTo: (level) => mounted.zoomTo(level),
  openFile: (fileId, page) => mounted.openFile(fileId, page),
  arrange: (mode) => mounted.arrange(mode),
  frames: () => mounted.frames(),
};

/** Called by the mounted canvas; the returned call unregisters it (only if it is still the one registered). */
export function registerCanvas(api: CanvasApi): () => void {
  mounted = api;
  return () => {
    if (mounted === api) mounted = idle;
  };
}
