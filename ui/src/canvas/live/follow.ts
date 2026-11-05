// Following an agent: the view moves to the agent's frame now and each time it moves to another frame. Any pan or
// zoom by the engineer stops it, and so does the agent finishing. Built like i18n.ts: one value for the page.
import { useReactFlow, useStoreApi } from "@xyflow/react";
import { useEffect, useRef, useSyncExternalStore } from "react";
import { STRIP_H } from "../place";
import { cursorShown, useAgent } from "./activity";
import { glide } from "./motion";

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
  const moving = useRef(0); // our own moves under way: the view changes they make are not the engineer's
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
    moving.current += 1;
    void flow
      .setCenter(x + w / 2, y + h / 2, { zoom: state.transform[2], duration: glide() })
      .finally(() => {
        moving.current -= 1;
      });
  }, [id, target, flow, store]);

  useEffect(() => {
    if (!id) return;
    return store.subscribe((state, previous) => {
      if (state.transform !== previous.transform && moving.current === 0) stopFollowing();
    });
  }, [id, store]);
}
