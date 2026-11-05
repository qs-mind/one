// Level of detail by zoom (decision 6): from 0.6 up a frame shows its live viewer, from 0.3 a poster, below 0.3 its
// name strip only. At most six live viewers at once: the focused frame, then the selected, then the nearest.
import type { FrameKey } from "../project/types";

export type Detail = "live" | "poster" | "title";
export const LIVE_CAP = 6;

export function lod(zoom: number): Detail {
  return zoom >= 0.6 ? "live" : zoom >= 0.3 ? "poster" : "title";
}

export function pickLive(
  visible: readonly FrameKey[],
  focused: FrameKey | undefined,
  selected: readonly FrameKey[],
  centreDistance: ReadonlyMap<FrameKey, number>,
  cap = LIVE_CAP,
): Set<FrameKey> {
  const shown = new Set(visible);
  const live = new Set<FrameKey>();
  const add = (key: FrameKey) => {
    if (live.size < cap && shown.has(key)) live.add(key);
  };
  if (focused) add(focused);
  for (const key of selected) add(key);
  const far = (key: FrameKey) => centreDistance.get(key) ?? Infinity;
  for (const key of [...visible].sort((a, b) => far(a) - far(b))) add(key);
  return live;
}
