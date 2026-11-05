// A frame on the canvas: Paper with a name strip (title, status, buttons), resize handles when selected, and a body
// that owns its keys. The body carries nodrag nowheel nopan nokey, so typing, selecting cells and scrolling inside a
// frame never move the canvas or the frame (decision 11). Enter goes in, Esc comes back (handled by the canvas).
import { NodeResizer, useStore, type Node } from "@xyflow/react";
import { createContext, memo, useContext, type ComponentType, type ReactNode } from "react";
import { fill, pick, t, useLanguage } from "../../i18n";
import { lod, type Detail } from "../lod";
import { MIN_H, MIN_W, STRIP_H } from "../place";
import type { Anchor, DeliverableInfo, DeskInfo, FileInfo, FrameKey, FrameKind, ProjectSources } from "../types";
import { FileName } from "../../ui/FileName";

/** `h` is the frame's open height, kept while it is folded to its strip. */
type Base = { collapsed: boolean; live: boolean; h: number };
export type FilesData = Base & { files: FileInfo[] };
export type FileData = Base & { file: FileInfo; page?: number };
export type DeliverableData = Base & { deliverable: DeliverableInfo };
/** `working`: how many of the Desk's agents work now (from the live store), for its folded line. The agents
 * themselves are read by the frames from the live store, so their moves never touch the canvas's nodes. */
export type DeskData = Base & { desk: DeskInfo; working: number };
export type TeamData = Base;

export type FrameNode =
  | Node<FilesData, "files">
  | Node<FileData, "file">
  | Node<DeliverableData, "deliverable">
  | Node<DeskData, "desk">
  | Node<TeamData, "team">;

/** What a frame may ask of the canvas around it. */
export type CanvasActions = {
  projectId: string;
  sources: ProjectSources;
  toggle(key: FrameKey): void;
  close(key: FrameKey): void;
  openFull(deliverableId: string): void;
  openFile(fileId: string, page?: number): void;
  addFiles(files: File[]): void;
  viewerSelection(key: FrameKey, anchor: Anchor | null, label: string | null): void;
};

export const CanvasActionsContext = createContext<CanvasActions | null>(null);

export function useCanvasActions(): CanvasActions {
  const actions = useContext(CanvasActionsContext);
  if (!actions) throw new Error("A frame must sit inside the Canvas.");
  return actions;
}

/** The frame's level of detail; re-renders only when it changes, not on every zoom step. */
export function useDetail(): Detail {
  return useStore((s) => lod(s.transform[2]));
}

export const kindOf = (key: FrameKey) => key.slice(0, key.indexOf(":")) as FrameKind;
export const idOf = (key: string) => key.slice(key.indexOf(":") + 1);

type TypeAndData<N> = N extends { type?: infer T; data: infer D } ? { type?: T; data: D } : never;
export type Titled = TypeAndData<FrameNode>;

/** The frame's name in the page language, as the strip, the selection chip and screen readers say it. */
export function frameTitle(node: Titled): string {
  switch (node.type) {
    case "files":
      return t("projectFiles");
    case "file":
      return node.data.file.name;
    case "deliverable":
      return node.data.deliverable.title;
    case "desk":
      return node.data.collapsed
        ? fill(t("deskSummary"), { desk: pick(node.data.desk.name), n: node.data.working })
        : pick(node.data.desk.name);
    default:
      return t("projectTeam");
  }
}

type FrameProps = {
  id: FrameKey;
  selected: boolean;
  collapsed: boolean;
  title: string;
  /** The direction of the frame's content; the canvas around it stays left to right. */
  dir: "rtl" | "ltr" | "auto";
  lang?: string;
  meta?: ReactNode;
  /** "Open full screen" for a Deliverable. */
  onOpenFull?(): void;
  closable?: boolean;
  /** The body scrolls or runs a viewer, so the wheel is its own; false for a poster. */
  scrolls?: boolean;
  children?: ReactNode;
};

const iconButton =
  "nodrag shrink-0 rounded-md px-1.5 leading-none text-slate hover:bg-stone hover:text-ink focus-visible:outline-2 focus-visible:outline-ink";

export function Frame({ id, selected, collapsed, title, dir, lang, meta, onOpenFull, closable, scrolls = true, children }: FrameProps) {
  useLanguage();
  const actions = useCanvasActions();
  const detail = useDetail();
  return (
    <div
      dir={dir}
      lang={lang}
      data-frame={id}
      className={`flex h-full w-full flex-col overflow-hidden rounded-[14px] bg-paper shadow-[0_1px_4px_rgb(14_15_18/0.08)] ${
        selected ? "border-[1.5px] border-ink" : "border border-ink/10"
      }`}
    >
      <NodeResizer
        isVisible={selected && !collapsed}
        minWidth={MIN_W}
        minHeight={MIN_H}
        handleClassName="!h-2 !w-2 !rounded-none !border-[1.5px] !border-ink !bg-paper"
        lineClassName="!border-transparent"
      />
      <header style={{ height: STRIP_H }} className="flex shrink-0 cursor-grab items-center gap-2 px-3">
        <h3 dir="auto" title={title} className="min-w-0 flex-1 truncate font-semibold">
          <FileName name={title} />
        </h3>
        {meta}
        {onOpenFull && (
          <button type="button" onClick={onOpenFull} aria-label={t("openFull")} title={t("openFull")} className={iconButton}>
            ⤢
          </button>
        )}
        <button
          type="button"
          onClick={() => actions.toggle(id)}
          aria-label={collapsed ? t("expand") : t("collapse")}
          aria-expanded={!collapsed}
          title={collapsed ? t("expand") : t("collapse")}
          className={iconButton}
        >
          {collapsed ? "▾" : "▴"}
        </button>
        {closable && (
          <button type="button" onClick={() => actions.close(id)} aria-label={t("closeFrame")} title={t("closeFrame")} className={iconButton}>
            ✕
          </button>
        )}
      </header>
      {!collapsed && detail !== "title" && (
        <div
          data-frame-body
          tabIndex={-1}
          // A body that scrolls keeps the wheel for itself (nowheel); a poster lets it pan the canvas. A pinch or
          // Ctrl/Cmd+wheel always zooms the canvas: the class is taken off for that one event, in the capture
          // phase, before React Flow's pane sees it (otherwise the webview would zoom the whole page).
          onWheelCapture={(event) => {
            if (scrolls) event.currentTarget.classList.toggle("nowheel", !(event.ctrlKey || event.metaKey));
          }}
          className={`nodrag nopan nokey ${scrolls ? "nowheel" : ""} min-h-0 flex-1 cursor-auto overflow-auto border-t border-ink/10 outline-none`}
        >
          {children}
        </div>
      )}
    </div>
  );
}

type FrameComponentProps = { id: string; data: object; selected?: boolean; width?: number; height?: number };

function shallowEqual(a: object, b: object): boolean {
  if (a === b) return true;
  const ka = Object.keys(a) as (keyof typeof a)[];
  return ka.length === Object.keys(b).length && ka.every((k) => a[k] === b[k]);
}

/** A frame re-renders when its data, selection or size changes; never on a pan or another frame's drag. */
export function memoFrame<P extends FrameComponentProps>(component: ComponentType<P>) {
  return memo(
    component,
    (a, b) =>
      a.id === b.id && a.selected === b.selected && a.width === b.width && a.height === b.height && shallowEqual(a.data, b.data),
  );
}
