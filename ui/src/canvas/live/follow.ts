// Following an agent: the view moves to the agent's frame now and each time it moves to another frame. Any pan or
// zoom by the engineer stops it, and so does the agent finishing. Built like i18n.ts: one value for the page.
import { useReactFlow, useStoreApi } from "@xyflow/react";
import { useEffect, useRef, useSyncExternalStore } from "react";
import { freeArea } from "../cover";
import { STRIP_H } from "../place";
import { cursorShown, useAgent } from "../../project/live/activity";
import { glide } from "../../project/live/motion";

const listeners = new Set<() => void>();
let followed: string | null = null;

function set(next: string | null) {
  if (next === followed) return;
  followed = next;
  for (const listener of [...listeners]) listener();
}

export function follow(agentId: string) {
  set(agentId);
}

export function stopFollowing() {
  set(null);
}

export function following(): string | null {
  return followed;
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** The id of the agent being followed, or null. */
export function useFollowing(): string | null {
  return useSyncExternalStore(subscribe, following);
}

/** Moves the view while following; mounted once inside the canvas (by the cursors). */
export function useFollowCamera() {
  const id = useFollowing();
  const agent = useAgent(id ?? "");
  const flow = useReactFlow();
  const store = useStoreApi();
  // Until then the view moves by our own hand, not the engineer's. A time, not the move's promise: a move the
  // engineer interrupts never settles.
  const ownUntil = useRef(0);
  const target = agent && cursorShown(agent) ? agent.focus!.frame : null;

  useEffect(() => {
    if (id && !target) stopFollowing(); // the agent finished, went away, or is on nothing
  }, [id, target]);

  useEffect(() => {
    if (!id || !target) return;
    const state = store.getState();
    const node = state.nodeLookup.get(target);
    if (!node) return;
    const w = node.width ?? node.measured.width ?? 0;
    const h = node.height ?? node.measured.height ?? STRIP_H;
    const { x, y } = node.internals.positionAbsolute;
    const duration = glide();
    ownUntil.current = performance.now() + duration + 100;
    // the middle of what the engineer sees: not under the open chat or the bars at the bottom
    const area = freeArea(state.domNode, { width: state.width, height: state.height });
    const zoom = state.transform[2];
    void flow.setViewport(
      { x: area.x + area.w / 2 - (x + w / 2) * zoom, y: area.y + area.h / 2 - (y + h / 2) * zoom, zoom },
      { duration },
    );
  }, [id, target, flow, store]);

  useEffect(() => {
    if (!id) return;
    return store.subscribe((state, previous) => {
      if (state.transform !== previous.transform && performance.now() >= ownUntil.current) stopFollowing();
    });
  }, [id, store]);
}
