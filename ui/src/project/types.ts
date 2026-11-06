// The workspace's contracts: what the core says about the
// project's files, Deliverables, Desks and agents. `sources.ts` is the only file that knows the routes behind them.
import type { Ref } from "react";
import type { DeliverableInfo, SheetView } from "../deliverables/types";
import type { Language, Text } from "../i18n";

export type { DeliverableInfo }; // Plan 6 declares it (plus pending, total, sample): never redeclared

export type FrameKind = "files" | "file" | "deliverable" | "desk" | "team" | "clientboq";
/** `files:all`, `file:<id>`, `deliverable:<id>`, `desk:<id>`, `team:core`, `clientboq:<file id>`. */
export type FrameKey = `${FrameKind}:${string}`;

/** A place inside a frame: a sheet row and column, a document block (`row`) and text range, a PDF page. */
export type Anchor = { row?: string; column?: string; page?: number; text?: [number, number]; point?: [number, number]; sheet?: string };
export type DocKind = "files" | "file" | "deliverable" | "clientboq" | "view";
/** "files:all", "file:<id>", "deliverable:<id>", "clientboq:<id>", "view:<chat part id>" (workspace/views.ts). */
export type DocKey = `${DocKind}:${string}`;
/** A spreadsheet file as its sheets (core/qsone/records/sheetview.py): one sheet's rows `r<row>`, columns by letter. */
export type FileSheet = SheetView & { sheet: string; sheets: { name: string; hidden: boolean }[]; more?: boolean };
/** The document open in the workspace, and where in it. */
export type Opened = { key: DocKey; anchor: Anchor | null };
export type Focus = { frame: FrameKey; anchor: Anchor | null };

/** Plan 2: GET /projects/{id}/files -> {files}. */
export type FileInfo = {
  id: string;
  name: string;
  status: "read" | "partly_read" | "stored" | "unreadable";
  note: Text | null;
  replaces: string | null;
  duplicate?: boolean;
};

/** A client BOQ imported from a file (GET /projects/{id}/workspace -> client_boqs): one read-only document each. `at` is the
 * newest import of the file. */
export type ClientBoqInfo = { file_id: string; name: string; items: number; headings: number; at: string };

/** Plan 4. A Temporary Desk's id is its Brief id; a saved Desk's is its slug. */
export type DeskInfo = { id: string; name: Text; stage: "temporary" | "draft" | "approved" };
export type AgentKind = "lead" | "checker" | "specialist" | "quick";
/** Plan 4: GET /projects/{id}/team -> {desks, agents}. The core never sends `idle`: the screen uses it for a team
 * member with no running agent. */
export type AgentInfo = {
  id: string;
  kind: AgentKind;
  role: Text;
  desk_id: string | null;
  model: string;
  /** The model's name as the sheet gives it («Gemini 3.1 Flash Lite»); null when it is not on the sheet. */
  model_name?: string | null;
  /** The model's provider, for its company's logo; null when the core does not know it. */
  provider?: string | null;
  state: "idle" | "thinking" | "working" | "waiting" | "done" | "failed";
  line: Text | null;
  /** The language of its Brief: the line is in it. */
  lang?: Language;
  brief_id: string | null;
  focus: Focus | null;
  at: string;
};
export type Team = { desks: DeskInfo[]; agents: AgentInfo[] };

/** Plan 4: GET /projects/{id}/activity, one JSON per server-sent event. */
export type ActivityEvent =
  | { type: "agent"; agent: AgentInfo }
  | { type: "agent-gone"; id: string }
  | { type: "deliverable"; deliverable: DeliverableInfo }
  | { type: "file"; file: FileInfo }
  | { type: "client_boq"; client_boq: ClientBoqInfo }
  | { type: "desk"; desk: DeskInfo }
  | { type: "waiting"; count: number };

/** GET /projects/{id}/status: only the fields the core knows. */
export type ProjectStatus = {
  stage?: Text;
  submission_date?: string;
  days_left?: number;
  /** `sample`: a number behind it is sample data; the screen labels it. */
  boq_value?: {
    value: string;
    currency: string;
    deliverable_id: string;
    revision: number | null;
    status: string;
    sample?: boolean;
    /** What the total covers: the Sheet's items, of the client BOQ's items (when one was imported). */
    items?: number;
    of?: number;
    /** How many of the Sheet's items have every number they need: the top bar says how many are left. */
    priced?: number;
  };
  open_comments?: number;
  waiting?: number;
};

/** What the engineer selected, sent with the message to the Lead QS. */
export type SelectionItem = { kind: FrameKind | "agent"; id: string; title: string; anchor?: Anchor; label?: string };

/** A text piece One read from a file, with where it is (sheet, row, page). */
export type FilePiece = { locator: Record<string, string | number>; text: string };

/** Everything the screen reads and writes for one project. */
export interface ProjectSources {
  files(): Promise<FileInfo[]>;
  deliverables(): Promise<DeliverableInfo[]>;
  team(): Promise<Team>;
  status(): Promise<ProjectStatus>;
  workspace(): Promise<{ open: DocKey | null; anchor: Anchor | null; client_boqs: ClientBoqInfo[] }>;
  saveWorkspace(opened: Opened, keepalive?: boolean): Promise<void>;
  /** Live events until `signal` aborts; reconnects by itself and then calls `onReconnect`. */
  activity(onEvent: (event: ActivityEvent) => void, signal: AbortSignal, onReconnect?: () => void): void;
  /** An object URL of the page as a PNG. */
  pageImage(fileId: string, page: number, width: number): Promise<string>;
  /** The number of pages; 0 when the file is not a PDF. */
  pages(fileId: string): Promise<number>;
  fileText(fileId: string, page?: number): Promise<FilePiece[]>;
  /** The client BOQ imported from the file, as a read-only Sheet view. */
  clientBoq(fileId: string): Promise<SheetView>;
  /** A spreadsheet file's sheet `name` (the first Excel shows when left out) as a read-only Sheet view; null for a
   * file that is no spreadsheet or cannot be opened as one (its text shows instead). */
  fileSheet(fileId: string, name?: string): Promise<FileSheet | null>;
  upload(file: File): Promise<FileInfo>;
}

/** How `locate` finds a target: by default it scrolls the target into view; `scroll: false` only measures. */
export type LocateOptions = { scroll?: boolean };

// The viewer registry's contract. Plan 6 Task 10 builds `viewerFor(kind)` in ui/src/viewers/registry.ts against
// these types: a component per Deliverable kind (null when there is none), loading its own data.
export interface ViewerHandle {
  /** The target's box relative to the viewer's root, in unscaled CSS pixels, or null when it cannot be found. It
   * brings the target into view first, unless `scroll` is false (only measure: the thin line by an agent's row). */
  locate(anchor: Anchor, options?: LocateOptions): DOMRect | null;
}
export interface ViewerProps {
  projectId: string;
  deliverableId: string;
  /** "workspace": the review board as the open document shows it, without the board's own title. */
  mode: "full" | "workspace";
  /** The engineer's selection inside the viewer, with a label in the page language («البنود 03/01–03/04»). */
  onSelection?(anchor: Anchor | null, label: string | null): void;
  /** React 19: the ref is a prop. */
  ref?: Ref<ViewerHandle>;
}
