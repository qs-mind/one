// Test helpers for the live layer: a canvas on fake sources with a stand-in viewer, sized for jsdom.
import { render } from "@testing-library/react";
import type { ReactNode } from "react";
import { Canvas } from "../Canvas";
import { fakeSources, type FakeOptions } from "../../project/fake";
import type { AgentInfo, DeliverableInfo, Placed } from "../../project/types";

const original = Object.getOwnPropertyDescriptors(HTMLElement.prototype);

/** React Flow measures its pane; jsdom has no layout. */
export function paneSize(width = 1200, height = 800) {
  for (const [side, value] of [
    ["offsetWidth", width],
    ["offsetHeight", height],
  ] as const) {
    Object.defineProperty(HTMLElement.prototype, side, {
      configurable: true,
      get(this: HTMLElement) {
        return this.classList.contains("react-flow__renderer") ? value : original[side]!.get!.call(this);
      },
    });
  }
}

export function restorePane() {
  Object.defineProperties(HTMLElement.prototype, { offsetWidth: original.offsetWidth!, offsetHeight: original.offsetHeight! });
}

export const deliverable = (id: string, fields: Partial<DeliverableInfo> = {}): DeliverableInfo => ({
  id,
  kind: "sheet",
  title: `تسعير ${id} - عينة`,
  language: "ar",
  status: "draft",
  code: null,
  same_provider: false,
  revision: null,
  desk: null,
  off_desk: false,
  progress: null,
  open_comments: 0,
  updated_at: "2026-11-05T09:00:00+00:00",
  ...fields,
});

export const agent = (id: string, fields: Partial<AgentInfo> = {}): AgentInfo => ({
  id,
  kind: "specialist",
  role: { en: `Estimator ${id} (sample)`, ar: `مهندس التسعير ${id} - عينة` },
  desk_id: null,
  model: "claude-sonnet-5",
  state: "working",
  line: null,
  brief_id: "b1",
  focus: { frame: "deliverable:boq", anchor: null },
  at: "2026-11-05T09:00:00+00:00",
  ...fields,
});

export const at = (key: Placed["key"], x: number, y: number, w: number, h: number): Placed => ({ key, x, y, w, h, z: 0, collapsed: false });

/** Two Deliverables and the team, all in view at zoom 1 (1200 × 800). */
export const layout = {
  frames: [
    at("deliverable:boq", 0, 0, 700, 500),
    at("deliverable:quotes", 3000, 0, 700, 500),
    at("team:core", 760, 0, 400, 760),
    at("files:all", 0, 560, 360, 200),
  ],
  view: { x: 0, y: 0, zoom: 1 },
};

export function showCanvas(options: FakeOptions = {}, children: ReactNode = null, beside: ReactNode = null) {
  const fake = fakeSources({ deliverables: [deliverable("boq"), deliverable("quotes")], layout, ...options });
  const view = render(
    <>
      <div style={{ width: 1200, height: 800 }}>
        <Canvas projectId="p1" sources={fake} onOpenFull={() => {}}>
          {children}
        </Canvas>
      </div>
      {beside}
    </>,
  );
  return { fake, ...view };
}

/** The viewport's transform, as React Flow writes it. */
export const viewport = (container: HTMLElement) => container.querySelector<HTMLElement>(".react-flow__viewport")!.style.transform;
