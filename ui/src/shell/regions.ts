// The screen's four regions, in F6 order: top bar, document, chat, command bar (decision 10). Each region is an
// element with `data-region` (a landmark with a name); F6 and Shift+F6 move focus to the next or previous one that
// is on screen, to its `data-region-start` element if it has one. The command bar sits inside the open chat: the
// region focus is in is the innermost one. Also: whether the window is narrow (below 1000 px) or small (below 640).
import { useSyncExternalStore } from "react";

export const REGIONS = ["topbar", "document", "chat", "command"] as const;

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
  const at = regions.findLastIndex((region) => region.contains(document.activeElement));
  const next =
    at === -1 ? (back ? regions.length - 1 : 0) : (at + (back ? -1 : 1) + regions.length) % regions.length;
  const region = regions[next]!;
  (region.querySelector<HTMLElement>("[data-region-start]") ?? region).focus();
}

const NARROW = "(max-width: 999px)";
const SMALL = "(max-width: 639px)";
const COMPACT = "(max-width: 1279px)";

const subscribeTo = (media: string) => (listener: () => void) => {
  const query = globalThis.matchMedia?.(media);
  query?.addEventListener?.("change", listener);
  return () => query?.removeEventListener?.("change", listener);
};
const subscribeNarrow = subscribeTo(NARROW);
const subscribeSmall = subscribeTo(SMALL);
const subscribeCompact = subscribeTo(COMPACT);

const isNarrow = () => globalThis.matchMedia?.(NARROW).matches ?? false;
const isSmall = () => globalThis.matchMedia?.(SMALL).matches ?? false;
const isCompact = () => globalThis.matchMedia?.(COMPACT).matches ?? false;

/** Below 1280 px the top bar keeps the project name and the status whole by folding its tools into "More". */
export function useCompact(): boolean {
  return useSyncExternalStore(subscribeCompact, isCompact);
}

/** Below 1000 px the chat is a panel over the document, opened from the top bar; the status folds into one button. */
export function useNarrow(): boolean {
  return useSyncExternalStore(subscribeNarrow, isNarrow);
}

/** Below 640 px the document takes the whole width: the side margins go, and the chat panel covers it all. */
export function useSmall(): boolean {
  return useSyncExternalStore(subscribeSmall, isSmall);
}
