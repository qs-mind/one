// The Project Canvas: the project's files, Deliverables and team as frames on a React Flow pane. What is on it comes
// from the project's data; the canvas keeps only where each thing sits, saved in the project's encrypted file. The
// pane is always left to right (world coordinates never flip); each frame follows its own content's direction.
import "@xyflow/react/dist/base.css";
import {
  applyNodeChanges,
  Background,
  BackgroundVariant,
  MiniMap,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
  useStore,
  useStoreApi,
  type Edge,
  type NodeChange,
  type OnSelectionChangeParams,
  type Viewport,
} from "@xyflow/react";
import { useCallback, useEffect, useId, useMemo, useRef, useState, type DragEvent, type FocusEvent, type KeyboardEvent, type ReactNode } from "react";
import { dir, fill, pick, t, texts, useLanguage, type Text } from "../i18n";
import { registerCanvas } from "./api";
import { arrange } from "./arrange";
import { DESKS_START_COLLAPSED, FILE_FRAMES } from "./choices";
import { DeliverableFrame } from "./frames/DeliverableFrame";
import { DeskFrame } from "./frames/DeskFrame";
import { FileFrame } from "./frames/FileFrame";
import { FilesFrame } from "./frames/FilesFrame";
import {
  CanvasActionsContext,
  frameTitle,
  idOf,
  kindOf,
  type CanvasActions,
  type FrameNode,
} from "./frames/Frame";
import { TeamFrame } from "./frames/TeamFrame";
import { deskCounts, startActivity, useDeskCounts } from "./live/activity";
import { isMac, isMod, isTyping, matches } from "./keys";
import { pickLive } from "./lod";
import { createSaver } from "./persist";
import { place, sizeFor, STRIP_H, type Incoming } from "./place";
import { select } from "./selection";
import { SourceError } from "./sources";
import type {
  ActivityEvent,
  Anchor,
  DeliverableInfo,
  DeskInfo,
  FileInfo,
  FrameKey,
  Placed,
  ProjectSources,
  SelectionItem,
} from "./types";

export type CanvasProps = {
  projectId: string;
  sources: ProjectSources;
  /** "Open full screen" on a Deliverable frame. */
  onOpenFull(deliverableId: string): void;
  /** Drawn over the pane, inside it (the live cursors). */
  children?: ReactNode;
};

const nodeTypes = { files: FilesFrame, file: FileFrame, deliverable: DeliverableFrame, desk: DeskFrame, team: TeamFrame };
const NO_EDGES: Edge[] = [];
const GAP = 80;
const ROW_GAP = 120;
const UNDO_STEPS = 50;
const FOCUS_RING = "rounded-[14px] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink";

type Things = {
  files: FileInfo[];
  deliverables: Map<string, DeliverableInfo>;
  desks: Map<string, DeskInfo>;
};

const nothing = (): Things => ({ files: [], deliverables: new Map(), desks: new Map() });

const reduced = () => globalThis.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
const duration = () => (reduced() ? 0 : 300);

function exists(key: FrameKey, things: Things): boolean {
  const id = idOf(key);
  switch (kindOf(key)) {
    case "files":
      return id === "all";
    case "team":
      return id === "core";
    case "file":
      return things.files.some((f) => f.id === id);
    case "deliverable":
      return things.deliverables.has(id);
    case "desk":
      return things.desks.has(id);
  }
}


/** What should be on the canvas: Project files, every Deliverable, the team and every Desk. */
function wanted(things: Things): Incoming[] {
  const out: Incoming[] = [{ key: "files:all", ...sizeFor("files:all") }];
  for (const d of things.deliverables.values()) out.push({ key: `deliverable:${d.id}`, ...sizeFor(`deliverable:${d.id}`, d) });
  out.push({ key: "team:core", ...sizeFor("team:core") });
  for (const desk of things.desks.values()) {
    const agents = deskCounts().get(desk.id)?.members ?? 0;
    out.push({ key: `desk:${desk.id}`, ...sizeFor(`desk:${desk.id}`, { agents }), collapsed: DESKS_START_COLLAPSED });
  }
  if (FILE_FRAMES === "every") for (const f of things.files) out.push({ key: `file:${f.id}`, ...sizeFor(`file:${f.id}`) });
  return out;
}

function nodeFor(p: Placed, things: Things, previous?: FrameNode): FrameNode | null {
  const id = idOf(p.key);
  const base = { collapsed: p.collapsed, live: previous?.data.live ?? false, h: p.h };
  const common = {
    id: p.key,
    position: { x: p.x, y: p.y },
    width: p.w,
    height: p.collapsed ? STRIP_H : p.h,
    zIndex: p.z,
    className: FOCUS_RING,
    selected: previous?.selected,
  };
  let node: FrameNode;
  switch (kindOf(p.key)) {
    case "files":
      node = { ...common, type: "files", data: { ...base, files: things.files } };
      break;
    case "file": {
      const file = things.files.find((f) => f.id === id);
      if (!file) return null;
      const page = previous?.type === "file" ? previous.data.page : undefined;
      node = { ...common, type: "file", data: { ...base, file, ...(page ? { page } : {}) } };
      break;
    }
    case "deliverable": {
      const deliverable = things.deliverables.get(id);
      if (!deliverable) return null;
      node = { ...common, type: "deliverable", data: { ...base, deliverable } };
      break;
    }
    case "desk": {
      const desk = things.desks.get(id);
      if (!desk) return null;
      node = { ...common, type: "desk", data: { ...base, desk, working: deskCounts().get(id)?.working ?? 0 } };
      break;
    }
    case "team":
      node = { ...common, type: "team", data: { ...base } };
      break;
  }
  node.ariaLabel = frameTitle(node);
  return node;
}

function placedOf(n: FrameNode): Placed {
  return {
    key: n.id as FrameKey,
    x: n.position.x,
    y: n.position.y,
    w: n.width ?? n.measured?.width ?? 0,
    h: n.data.collapsed ? n.data.h : (n.height ?? n.measured?.height ?? n.data.h),
    z: n.zIndex ?? 0,
    collapsed: n.data.collapsed,
  };
}

const samePlace = (a: Placed, b: Placed | undefined) =>
  !!b && a.x === b.x && a.y === b.y && a.w === b.w && a.h === b.h && a.z === b.z && a.collapsed === b.collapsed;

function sameData(a: object, b: object): boolean {
  const ka = Object.keys(a) as (keyof typeof a)[];
  return ka.length === Object.keys(b).length && ka.every((k) => a[k] === b[k]);
}

function itemFor(n: FrameNode): SelectionItem {
  return { kind: kindOf(n.id as FrameKey), id: idOf(n.id), title: frameTitle(n) };
}

const focusables = 'button, [href], input, select, textarea, [contenteditable="true"], [tabindex]:not([tabindex="-1"])';

export function Canvas(props: CanvasProps) {
  return (
    <ReactFlowProvider>
      <Pane {...props} />
    </ReactFlowProvider>
  );
}

function Pane({ projectId, sources, onOpenFull, children }: CanvasProps) {
  const lang = useLanguage();
  const flow = useReactFlow<FrameNode>();
  const store = useStoreApi<FrameNode>();
  const help = useId();
  const [nodes, setNodesState] = useState<FrameNode[]>([]);
  const nodesRef = useRef<FrameNode[]>([]);
  const things = useRef<Things>(nothing());
  const [state, setState] = useState<"loading" | "ready" | "failed">("loading");
  const [attempt, setAttempt] = useState(0);
  const [problems, setProblems] = useState<{ name: string; line: Text }[]>([]);
  const saver = useMemo(() => createSaver(sources), [sources]);
  const committed = useRef(new Map<FrameKey, Placed>());
  const history = useRef<{ past: Placed[][]; future: Placed[][] }>({ past: [], future: [] });
  const focused = useRef<FrameKey | undefined>(undefined);
  const openFullRef = useRef(onOpenFull);
  openFullRef.current = onOpenFull;

  const setNodes = useCallback((next: FrameNode[]) => {
    nodesRef.current = next;
    setNodesState(next);
  }, []);

  const opts = () => ({ dir: dir(), gap: GAP, rowGap: ROW_GAP });

  /** Which Deliverable frames run their live viewer: at most six, by focus, selection and nearness (decision 6). */
  const refreshLive = useCallback(() => {
    const { transform, width, height } = store.getState();
    const [tx, ty, zoom] = transform;
    const view = { x: -tx / zoom, y: -ty / zoom, w: width / zoom, h: height / zoom };
    const centre = { x: view.x + view.w / 2, y: view.y + view.h / 2 };
    const visible: FrameKey[] = [];
    const distance = new Map<FrameKey, number>();
    const selected: FrameKey[] = [];
    for (const n of nodesRef.current) {
      if (n.type !== "deliverable" || n.data.collapsed) continue;
      const p = placedOf(n);
      if (p.x > view.x + view.w || p.x + p.w < view.x || p.y > view.y + view.h || p.y + p.h < view.y) continue;
      const key = n.id as FrameKey;
      visible.push(key);
      distance.set(key, Math.hypot(p.x + p.w / 2 - centre.x, p.y + p.h / 2 - centre.y));
      if (n.selected) selected.push(key);
    }
    const live = pickLive(visible, focused.current, selected, distance);
    let changed = false;
    const next = nodesRef.current.map((n) => {
      const should = live.has(n.id as FrameKey);
      if (n.type !== "deliverable" || n.data.live === should) return n;
      changed = true;
      return { ...n, data: { ...n.data, live: should } };
    });
    if (changed) setNodes(next);
  }, [store, setNodes]);

  /** Brings the frames in line with the project's data: new things placed, gone things removed, data refreshed. */
  const rebuild = useCallback(() => {
    const kept: FrameNode[] = [];
    const removed: FrameKey[] = [];
    for (const n of nodesRef.current) {
      const fresh = nodeFor(placedOf(n), things.current, n);
      if (!fresh) {
        removed.push(n.id as FrameKey);
        continue;
      }
      kept.push(sameData(n.data, fresh.data) && n.ariaLabel === fresh.ariaLabel ? n : ({ ...n, data: fresh.data, ariaLabel: fresh.ariaLabel } as FrameNode));
    }
    const have = new Set(kept.map((n) => n.id));
    const incoming = wanted(things.current).filter((i) => !have.has(i.key));
    const all = place(kept.map(placedOf), incoming, opts());
    const added = all.slice(kept.length);
    for (const p of added) {
      const node = nodeFor(p, things.current);
      if (node) kept.push(node);
      committed.current.set(p.key, p);
    }
    for (const key of removed) committed.current.delete(key);
    if (added.length || removed.length || kept.some((n, i) => n !== nodesRef.current[i])) setNodes(kept);
    if (added.length || removed.length) saver.frames(added, removed);
  }, [saver, setNodes]);

  /** Moves frames to a layout (arrange, undo, redo, fold); saves what changed. */
  const applyLayout = useCallback(
    (target: readonly Placed[]) => {
      const byKey = new Map(target.map((p) => [p.key, p]));
      const changed: Placed[] = [];
      const next = nodesRef.current.map((n) => {
        const p = byKey.get(n.id as FrameKey);
        if (!p || samePlace(placedOf(n), p)) return n;
        changed.push(p);
        return {
          ...n,
          position: { x: p.x, y: p.y },
          width: p.w,
          height: p.collapsed ? STRIP_H : p.h,
          zIndex: p.z,
          data: { ...n.data, collapsed: p.collapsed, h: p.h },
          ariaLabel: n.ariaLabel,
        } as FrameNode;
      });
      if (!changed.length) return;
      setNodes(next.map((n) => (byKey.has(n.id as FrameKey) ? { ...n, ariaLabel: frameTitle(n) } : n)));
      for (const p of changed) committed.current.set(p.key, p);
      saver.frames(changed, []);
    },
    [saver, setNodes],
  );

  const snapshot = () => [...committed.current.values()];
  const remember = () => {
    const { past } = history.current;
    past.push(snapshot());
    if (past.length > UNDO_STEPS) past.shift();
    history.current.future = [];
  };

  /** The engineer finished moving or resizing these frames: one undo step, one save. */
  const commit = useCallback(
    (keys: Iterable<string>) => {
      const changed: Placed[] = [];
      for (const key of keys) {
        const n = nodesRef.current.find((x) => x.id === key);
        if (!n) continue;
        const p = placedOf(n);
        if (!samePlace(p, committed.current.get(p.key))) changed.push(p);
      }
      if (!changed.length) return;
      remember();
      for (const p of changed) committed.current.set(p.key, p);
      saver.frames(changed, []);
    },
    [saver],
  );

  const undo = useCallback(() => {
    const step = history.current.past.pop();
    if (!step) return;
    history.current.future.push(snapshot());
    applyLayout(step);
  }, [applyLayout]);

  const redo = useCallback(() => {
    const step = history.current.future.pop();
    if (!step) return;
    history.current.past.push(snapshot());
    applyLayout(step);
  }, [applyLayout]);

  /** Shows these frames in the middle of the pane. Computed from the layout itself, not from React Flow's measured
   * nodes: with onlyRenderVisibleElements a frame off screen is never measured, so fitView would leave it out. */
  const fitTo = useCallback(
    (frames: readonly Placed[], { padding = 0.1, maxZoom = 1, animate = true } = {}) => {
      if (!frames.length) return;
      const { width, height } = store.getState();
      const minX = Math.min(...frames.map((f) => f.x));
      const minY = Math.min(...frames.map((f) => f.y));
      const w = Math.max(...frames.map((f) => f.x + f.w)) - minX || 1;
      const h = Math.max(...frames.map((f) => f.y + (f.collapsed ? STRIP_H : f.h))) - minY || 1;
      const fit = Math.min((width * (1 - 2 * padding)) / w, (height * (1 - 2 * padding)) / h);
      const zoom = Math.min(maxZoom, 2, Math.max(0.1, fit));
      void flow.setViewport(
        { x: width / 2 - (minX + w / 2) * zoom, y: height / 2 - (minY + h / 2) * zoom, zoom },
        { duration: animate ? duration() : 0 },
      );
    },
    [flow, store],
  );

  const doArrange = useCallback(
    (mode: "stage" | "tidy") => {
      const status = new Map<FrameKey, DeliverableInfo["status"]>();
      for (const d of things.current.deliverables.values()) status.set(`deliverable:${d.id}`, d.status);
      const target = arrange(nodesRef.current.map(placedOf), status, mode, { dir: dir() });
      remember();
      applyLayout(target);
      fitTo(target);
    },
    [applyLayout, fitTo],
  );

  const focusFrame = useCallback(
    (key: FrameKey, opts?: { anchor?: Anchor; zoom?: number }) => {
      const node = nodesRef.current.find((n) => n.id === key);
      if (!node) return;
      setNodes(nodesRef.current.map((n) => (n.selected === (n.id === key) ? n : { ...n, selected: n.id === key })));
      fitTo([placedOf(node)], { padding: 0.2, maxZoom: opts?.zoom ?? 1 });
      requestAnimationFrame(() => {
        document.querySelector<HTMLElement>(`.react-flow__node[data-id="${CSS.escape(key)}"]`)?.focus({ preventScroll: true });
      });
    },
    [fitTo, setNodes],
  );

  /** Opens a file's frame (or brings it forward), at the first free slot or where it was dropped. */
  const openFile = useCallback(
    (fileId: string, page?: number, at?: { x: number; y: number }) => {
      const key: FrameKey = `file:${fileId}`;
      if (!things.current.files.some((f) => f.id === fileId)) return;
      const existing = nodesRef.current.find((n) => n.id === key);
      if (existing) {
        if (page && existing.type === "file")
          setNodes(nodesRef.current.map((n) => (n === existing ? { ...existing, data: { ...existing.data, page } } : n)));
      } else {
        const size = sizeFor(key);
        const p: Placed = at
          ? { key, x: at.x, y: at.y, ...size, z: 0, collapsed: false }
          : place(nodesRef.current.map(placedOf), [{ key, ...size }], opts()).at(-1)!;
        const node = nodeFor(p, things.current);
        if (!node) return;
        if (page && node.type === "file") node.data = { ...node.data, page };
        setNodes([...nodesRef.current, node]);
        committed.current.set(key, p);
        saver.frames([p], []);
      }
      focusFrame(key);
    },
    [focusFrame, saver, setNodes],
  );

  const addFiles = useCallback(
    async (files: File[], at?: { x: number; y: number }) => {
      for (const [index, file] of files.entries()) {
        try {
          const info = await sources.upload(file);
          things.current.files = [info, ...things.current.files.filter((f) => f.id !== info.id && f.id !== info.replaces)];
          rebuild();
          if (at) openFile(info.id, undefined, { x: at.x + index * 40, y: at.y + index * 40 });
        } catch (error) {
          const line = error instanceof SourceError ? error.line : texts.fileNotAdded;
          setProblems((list) => [...list, { name: file.name, line }]);
        }
      }
    },
    [sources, rebuild, openFile],
  );

  // Loading the project: its things and its saved layout; saved frames whose thing is gone are removed.
  useEffect(() => {
    let live = true;
    const team = new AbortController(); // the live team (agents, cursors) runs while this project is on the canvas
    setState("loading");
    setNodes([]);
    void (async () => {
      try {
        const [files, deliverables, loaded, layout] = await Promise.all([
          sources.files(),
          sources.deliverables(),
          sources.team(),
          sources.layout(),
        ]);
        if (!live) return;
        things.current = {
          files,
          deliverables: new Map(deliverables.map((d) => [d.id, d])),
          desks: new Map(loaded.desks.map((d) => [d.id, d])),
        };
        startActivity(sources, team.signal, loaded);
        const kept = layout.frames.filter((f) => exists(f.key, things.current));
        const removed = layout.frames.filter((f) => !exists(f.key, things.current)).map((f) => f.key);
        const all = place(kept, wanted(things.current), opts());
        const added = all.slice(kept.length);
        committed.current = new Map(all.map((p) => [p.key, p]));
        history.current = { past: [], future: [] };
        setNodes(all.flatMap((p) => nodeFor(p, things.current) ?? []));
        if (added.length || removed.length) {
          saver.frames(added, removed);
          saver.flush();
        }
        setState("ready");
        if (layout.view) void flow.setViewport(layout.view);
        else fitTo(all, { animate: false });
      } catch {
        if (live) setState("failed");
      }
    })();
    return () => {
      live = false;
      team.abort();
      saver.flush(true);
    };
  }, [projectId, sources, attempt]);

  // Live events: new and changed Deliverables and Desks; after a reconnect the lists are read again. Agents are the
  // live store's (live/activity.ts): the canvas sees only each Desk's counts, for its folded line.
  useEffect(() => {
    if (state !== "ready") return;
    const controller = new AbortController();
    const onEvent = (event: ActivityEvent) => {
      const now = things.current;
      if (event.type === "deliverable") now.deliverables.set(event.deliverable.id, event.deliverable);
      else if (event.type === "desk") now.desks.set(event.desk.id, event.desk);
      else return;
      things.current = { ...now };
      rebuild();
    };
    const reload = () => {
      void Promise.all([sources.deliverables(), sources.team()]).then(
        ([deliverables, team]) => {
          if (controller.signal.aborted) return;
          things.current = {
            ...things.current,
            deliverables: new Map(deliverables.map((d) => [d.id, d])),
            desks: new Map(team.desks.map((d) => [d.id, d])),
          };
          rebuild();
        },
        () => {}, // the lists stay as they were; the next reconnect tries again
      );
    };
    sources.activity(onEvent, controller.signal, reload);
    return () => controller.abort();
  }, [state, sources, rebuild]);

  // A Desk's folded line counts its working agents: refreshed when a count changes, never on an agent's move.
  const counts = useDeskCounts();
  useEffect(() => {
    if (state === "ready") rebuild();
  }, [counts, state, rebuild]);

  useEffect(() => {
    const leave = () => saver.flush(true);
    window.addEventListener("pagehide", leave);
    return () => window.removeEventListener("pagehide", leave);
  }, [saver]);

  // Titles follow the page language.
  useEffect(() => {
    if (nodesRef.current.some((n) => n.ariaLabel !== frameTitle(n)))
      setNodes(nodesRef.current.map((n) => (n.ariaLabel === frameTitle(n) ? n : { ...n, ariaLabel: frameTitle(n) })));
  }, [lang, setNodes]);

  useEffect(() => {
    if (state === "ready") refreshLive();
  }, [state, nodes.length, refreshLive]);

  useEffect(
    () =>
      registerCanvas({
        focusFrame: (key, opts) => (kindOf(key) === "file" && !nodesRef.current.some((n) => n.id === key) ? openFile(idOf(key), opts?.anchor?.page) : focusFrame(key, opts)),
        fitAll: () => fitTo(nodesRef.current.map(placedOf)),
        zoomTo: (level) => void flow.zoomTo(level, { duration: duration() }),
        openFile: (fileId, page) => openFile(fileId, page),
        arrange: doArrange,
        frames: () => nodesRef.current.map(placedOf),
      }),
    [flow, fitTo, focusFrame, openFile, doArrange],
  );

  const actions = useMemo<CanvasActions>(
    () => ({
      projectId,
      sources,
      toggle(key) {
        const n = nodesRef.current.find((x) => x.id === key);
        if (!n) return;
        remember();
        const p = placedOf(n);
        applyLayout([{ ...p, collapsed: !p.collapsed }]);
      },
      close(key) {
        if (!nodesRef.current.some((n) => n.id === key)) return;
        setNodes(nodesRef.current.filter((n) => n.id !== key));
        committed.current.delete(key);
        saver.frames([], [key]);
        select(nodesRef.current.filter((n) => n.selected).map(itemFor));
      },
      openFull: (id) => openFullRef.current(id),
      openFile: (fileId, page) => openFile(fileId, page),
      addFiles: (files) => void addFiles(files),
      viewerSelection(key, anchor, label) {
        const n = nodesRef.current.find((x) => x.id === key);
        if (!n) return;
        if (anchor) select([{ ...itemFor(n), anchor, ...(label ? { label } : {}) }]);
        else select(nodesRef.current.filter((x) => x.selected).map(itemFor));
      },
    }),
    [projectId, sources, applyLayout, saver, setNodes, openFile, addFiles],
  );

  const onNodesChange = useCallback(
    (changes: NodeChange<FrameNode>[]) => {
      setNodes(applyNodeChanges(changes, nodesRef.current));
      const done = new Set<string>();
      for (const c of changes) {
        if (c.type === "position" && c.dragging === false) done.add(c.id);
        if (c.type === "dimensions" && c.resizing === false && c.setAttributes) done.add(c.id);
      }
      if (done.size) commit(done);
    },
    [setNodes, commit],
  );

  const onSelectionChange = useCallback(
    ({ nodes: chosen }: OnSelectionChangeParams<FrameNode>) => {
      select(chosen.map(itemFor));
      refreshLive();
    },
    [refreshLive],
  );

  const onMoveEnd = useCallback(
    (_: unknown, viewport: Viewport) => {
      saver.view(viewport);
      refreshLive();
    },
    [saver, refreshLive],
  );

  function onKeyDown(event: KeyboardEvent<HTMLElement>) {
    const target = event.target as HTMLElement;
    const node = target.closest<HTMLElement>(".react-flow__node");
    const body = target.closest<HTMLElement>("[data-frame-body]");
    if ((event.code === "Enter" || event.code === "NumpadEnter") && node === target) {
      const inside = target.querySelector<HTMLElement>("[data-frame-body]");
      if (!inside) return;
      event.preventDefault();
      (inside.querySelector<HTMLElement>(focusables) ?? inside).focus();
    } else if (event.code === "Escape" && body && node) {
      if (event.defaultPrevented) return; // the viewer used it (closing its own popover)
      event.preventDefault();
      node.focus();
    } else if (event.code === "Escape" && node === target) {
      setNodes(nodesRef.current.map((n) => (n.selected ? { ...n, selected: false } : n)));
      select([]);
    } else if (isMod(event) && matches(event, "KeyZ") && !isTyping(target) && !body) {
      event.preventDefault();
      if (event.shiftKey) redo();
      else undo();
    }
  }

  function onFocus(event: FocusEvent<HTMLElement>) {
    const key = event.target.closest<HTMLElement>(".react-flow__node")?.dataset.id as FrameKey | undefined;
    if (key === focused.current) return;
    focused.current = key;
    refreshLive();
  }

  function onDragOver(event: DragEvent<HTMLElement>) {
    if (event.dataTransfer.types.includes("Files")) event.preventDefault();
  }

  function onDrop(event: DragEvent<HTMLElement>) {
    const files = Array.from(event.dataTransfer.files);
    if (!files.length) return;
    event.preventDefault(); // the window must not open the file itself
    const at = flow.screenToFlowPosition({ x: event.clientX, y: event.clientY });
    // a drop without a point (some sources send none) opens the frames at the first free slots instead
    void addFiles(files, Number.isFinite(at.x) && Number.isFinite(at.y) ? at : undefined);
  }

  const aria = useMemo(
    () => ({
      "node.a11yDescription.default": t("flowNodeHelp"),
      "node.a11yDescription.keyboardDisabled": t("flowNodeHelp"),
      "node.a11yDescription.ariaLiveMessage": ({ x, y }: { direction: string; x: number; y: number }) =>
        fill(t("flowNodeMoved"), { x, y }),
      "edge.a11yDescription.default": "",
      "controls.ariaLabel": t("zoomControls"),
      "controls.zoomIn.ariaLabel": t("zoomIn"),
      "controls.zoomOut.ariaLabel": t("zoomOut"),
      "controls.fitView.ariaLabel": t("fitAll"),
      "controls.interactive.ariaLabel": "",
      "minimap.ariaLabel": t("minimap"),
      "handle.ariaLabel": "",
    }),
    [lang],
  );

  const rtl = dir() === "rtl";

  return (
    <section
      aria-label={t("canvas")}
      aria-describedby={help}
      dir="ltr"
      className="relative h-full w-full bg-stone"
      onKeyDown={onKeyDown}
      onFocus={onFocus}
      onDragOver={onDragOver}
      onDrop={onDrop}
    >
      <p id={help} hidden>
        {t("canvasKeys")}
      </p>
      <CanvasActionsContext.Provider value={actions}>
        <ReactFlow<FrameNode>
          nodes={nodes}
          edges={NO_EDGES}
          nodeTypes={nodeTypes}
          onNodesChange={onNodesChange}
          onSelectionChange={onSelectionChange}
          onMoveEnd={onMoveEnd}
          onlyRenderVisibleElements
          deleteKeyCode={null}
          minZoom={0.1}
          maxZoom={2}
          panOnScroll
          zoomActivationKeyCode={isMac() ? "Meta" : "Control"}
          elevateNodesOnSelect
          nodesFocusable
          nodesConnectable={false}
          edgesFocusable={false}
          ariaLabelConfig={aria}
          proOptions={{ hideAttribution: true }}
        >
          <Background variant={BackgroundVariant.Dots} gap={20} size={1.5} color="rgb(14 15 18 / 0.16)" />
          <MiniMap
            className="max-[900px]:hidden"
            position={rtl ? "bottom-right" : "bottom-left"}
            style={{ marginBottom: 72 }}
            ariaLabel={t("minimap")}
            bgColor="#F9F8F4"
            nodeColor="#F2EEE7"
            nodeStrokeColor="rgb(14 15 18 / 0.2)"
            maskColor="rgb(242 238 231 / 0.6)"
            maskStrokeColor="#0E0F12"
            maskStrokeWidth={1.5}
            pannable
            zoomable
          />
          {children}
        </ReactFlow>
      </CanvasActionsContext.Provider>
      <ZoomBar onArrange={() => doArrange("stage")} />
      {state === "failed" && (
        <div role="alert" dir={dir()} className="absolute inset-x-0 top-6 mx-auto flex w-fit items-center gap-3 rounded-[14px] border border-ink/10 bg-paper px-4 py-2 text-copper">
          {t("canvasFailed")}
          <button type="button" onClick={() => setAttempt((n) => n + 1)} className="rounded-md border border-ink px-3 py-1 text-ink">
            {t("retry")}
          </button>
        </div>
      )}
      {problems.length > 0 && (
        <div role="alert" dir={dir()} className="absolute inset-x-0 top-6 mx-auto flex w-fit max-w-[32rem] flex-col gap-1 rounded-[14px] border border-ink/10 bg-paper px-4 py-2 text-copper">
          {problems.map((problem, index) => (
            <p key={index}>
              <bdi dir="auto" className="font-semibold">
                {problem.name}
              </bdi>{" "}
              {pick(problem.line)}
            </p>
          ))}
          <button type="button" onClick={() => setProblems([])} className="self-end text-slate hover:text-ink">
            {t("close")}
          </button>
        </div>
      )}
    </section>
  );
}

/** Zoom out, the zoom level, zoom in, and Arrange by stage, at the bottom inline start (it mirrors in Arabic). */
function ZoomBar({ onArrange }: { onArrange(): void }) {
  useLanguage();
  const flow = useReactFlow();
  const percent = useStore((s) => Math.round(s.transform[2] * 100));
  const button =
    "rounded-md px-2 py-1 hover:bg-stone focus-visible:outline-2 focus-visible:outline-ink";
  return (
    <div
      role="toolbar"
      aria-label={t("zoomControls")}
      dir={dir()}
      style={{ [dir() === "rtl" ? "right" : "left"]: 16 }}
      className="absolute bottom-4 z-10 flex items-center gap-1 rounded-[14px] border border-ink/10 bg-paper p-1 shadow-[0_1px_4px_rgb(14_15_18/0.08)]"
    >
      <button type="button" aria-label={t("zoomOut")} title={t("zoomOut")} className={button} onClick={() => void flow.zoomOut({ duration: duration() })}>
        −
      </button>
      <span className="min-w-12 text-center tabular-nums">
        <span className="sr-only">{fill(t("zoomLevel"), { percent })}</span>
        <bdi dir="ltr" aria-hidden="true">
          {percent}%
        </bdi>
      </span>
      <button type="button" aria-label={t("zoomIn")} title={t("zoomIn")} className={button} onClick={() => void flow.zoomIn({ duration: duration() })}>
        +
      </button>
      <button type="button" className={button} onClick={onArrange}>
        {t("arrangeByStage")}
      </button>
    </div>
  );
}
