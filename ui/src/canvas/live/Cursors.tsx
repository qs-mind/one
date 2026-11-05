// The agents' cursors on the canvas (decision 8): each points at the frame its agent works on, at the row, cell or
// page when the frame's viewer can find it, else at the frame's name strip. They live in React Flow's viewport, so a
// pan moves them with the frames for free; each is one element moved by `transform` only, and re-renders only when
// its own agent or frame changes. They are hidden from screen readers: the agent cards and the Announcer say it.
import { useStore, ViewportPortal, type ReactFlowState } from "@xyflow/react";
import { memo, useLayoutEffect, useReducer } from "react";
import { dir, pick, t, useLanguage } from "../../i18n";
import { viewerHandles } from "../frames/DeliverableFrame";
import { lod } from "../lod";
import { STRIP_H } from "../place";
import type { FrameKey } from "../../project/types";
import { useAgent, useAgentsOn, useCursorIds } from "../../project/live/activity";
import { useFollowCamera } from "./follow";
import { useReducedMotion } from "../../project/live/motion";

/** Cursors on one frame stack this far apart. */
export const STACK_PX = 24;
/** On the name strip, the cursor sits this far in from the strip's trailing end. */
export const STRIP_INSET = 24;

type Box = { x: number; y: number; w: number; h: number };

const boxOf = (s: ReactFlowState, key: FrameKey | undefined): Box | null => {
  const node = key ? s.nodeLookup.get(key) : undefined;
  if (!node) return null;
  const { x, y } = node.internals.positionAbsolute;
  return { x, y, w: node.width ?? node.measured.width ?? 0, h: node.height ?? node.measured.height ?? STRIP_H };
};
const sameBox = (a: Box | null, b: Box | null) =>
  a === b || (!!a && !!b && a.x === b.x && a.y === b.y && a.w === b.w && a.h === b.h);

/** Where the cursor's tip goes, in world pixels: the target the viewer locates (its box is relative to the viewer,
 * which starts under the strip and its 1 px line), or the strip's trailing end in the page's direction. */
export function cursorPoint(box: Box, located: DOMRect | null, rtl: boolean): { x: number; y: number } {
  if (located) {
    const x = box.x + located.x;
    const y = box.y + STRIP_H + 1 + located.y;
    if (x >= box.x && x <= box.x + box.w && y >= box.y + STRIP_H && y <= box.y + box.h) return { x, y };
  }
  return { x: rtl ? box.x + STRIP_INSET : box.x + box.w - STRIP_INSET, y: box.y + STRIP_H / 2 };
}

export function Cursors() {
  useFollowCamera();
  const ids = useCursorIds();
  const zoom = useStore((s) => s.transform[2]);
  if (!ids.length) return null;
  return (
    <ViewportPortal>
      {/* the cursors keep their size on screen at every zoom */}
      <div aria-hidden="true" style={{ ["--cursor-scale" as string]: 1 / zoom }}>
        {ids.map((id) => (
          <Cursor key={id} id={id} />
        ))}
      </div>
    </ViewportPortal>
  );
}

const Cursor = memo(function Cursor({ id }: { id: string }) {
  useLanguage();
  const agent = useAgent(id);
  const frame = agent?.focus?.frame;
  const stack = useAgentsOn(frame ?? "files:none");
  const box = useStore((s) => boxOf(s, frame), sameBox);
  useStore((s) => (frame ? lod(s.transform[2]) : null)); // a viewer comes or goes with the level of detail
  useStore((s) => (frame ? s.nodeLookup.get(frame)?.data.live : undefined));
  const reduced = useReducedMotion();
  const [, again] = useReducer((n: number) => n + 1, 0);
  const handle = frame ? viewerHandles.get(frame) : undefined;
  // The viewer registers its handle when it mounts, after this render: look again once it is there.
  useLayoutEffect(() => {
    if (frame && viewerHandles.get(frame) !== handle) again();
  });
  if (!agent || !frame || !box) return null;
  const anchor = agent.focus!.anchor;
  const located = anchor && handle ? handle.locate(anchor) : null;
  const tip = cursorPoint(box, located, dir() === "rtl");
  const y = tip.y + Math.max(0, stack.indexOf(id)) * STACK_PX;
  const outlined = agent.kind === "checker";
  return (
    <div
      data-testid={`cursor-${id}`}
      className="pointer-events-none absolute left-0 top-0"
      style={{ transform: `translate(${tip.x}px, ${y}px)`, transition: reduced ? "none" : "transform 300ms ease-out" }}
    >
      <div style={{ transform: "scale(var(--cursor-scale, 1))", transformOrigin: "0 0" }}>
        <svg width="14" height="20" viewBox="0 0 14 20" className="block overflow-visible">
          <path d="M1 1 L1 17 L5.2 13 L8.2 19.5 L10.8 18.4 L7.9 12 L13.4 12 Z" fill="#0E0F12" stroke="#F9F8F4" strokeWidth="1.5" strokeLinejoin="round" />
        </svg>
        <span
          dir={dir()}
          className={`absolute left-3 top-4 whitespace-nowrap rounded-md px-1.5 py-0.5 text-[13px] leading-tight ${
            outlined ? "border-[1.5px] border-ink bg-paper text-ink" : "bg-ink text-paper"
          }`}
        >
          {pick(agent.role)}
          {agent.noNews && <span className="block">{t("noNews")}</span>}
        </span>
      </div>
    </div>
  );
});
