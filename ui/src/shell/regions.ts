// The screen's four regions, in F6 order: top bar, canvas, chat, command bar (decision 10). Each region is an
// element with `data-region` (a landmark with a name); F6 and Shift+F6 move focus to the next or previous one that
// is on screen, to its `data-region-start` element if it has one. Also: whether the window is narrow (below 900 px).
import { useSyncExternalStore } from "react";

export const REGIONS = ["topbar", "canvas", "chat", "command"] as const;

function present(root: ParentNode): HTMLElement[] {
  return REGIONS.flatMap((name) => {
    const region = root.querySelector<HTMLElement>(`[data-region="${name}"]`);
    return region && !region.closest("[inert]") ? [region] : [];
  });
}

/** Moves focus to the next region (or the previous one, `back`); from outside every region, to the first or last. */
export function moveRegion(back: boolean, root: ParentNode = document) {
  const regions = present(root);
  if (regions.length === 0) return;
  const at = regions.findIndex((region) => region.contains(document.activeElement));
  const next =
    at === -1 ? (back ? regions.length - 1 : 0) : (at + (back ? -1 : 1) + regions.length) % regions.length;
  const region = regions[next]!;
  (region.querySelector<HTMLElement>("[data-region-start]") ?? region).focus();
}

const NARROW = "(max-width: 899px)";

function subscribeNarrow(listener: () => void): () => void {
  const query = globalThis.matchMedia?.(NARROW);
  query?.addEventListener?.("change", listener);
  return () => query?.removeEventListener?.("change", listener);
}

const isNarrow = () => globalThis.matchMedia?.(NARROW).matches ?? false;

/** Below 900 px the chat is a sheet, the status folds into one button and the rest into "More". */
export function useNarrow(): boolean {
  return useSyncExternalStore(subscribeNarrow, isNarrow);
}
