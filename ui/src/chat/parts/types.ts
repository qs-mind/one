// The data parts a Brief's stream carries (Plan 4, Task 8). Each has a stable id, so the AI SDK updates it in place.
import type { UIMessage } from "ai";
import type { SelectionItem } from "../../canvas/types";
import type { Source } from "../../deliverables/types";
import type { Language, Text } from "../../i18n";
import type { ViewData } from "./view/types";

export type BriefState =
  | "queued"
  | "running"
  | "waiting_engineer"
  | "waiting_connection"
  | "paused_cap"
  | "stopped"
  | "done"
  | "failed";

/** data-progress, id = the agent run: what that agent is doing now, and the Brief's language to show it in. */
export type ProgressData = { agent: Text; text: Text; lang?: Language };
/** data-team, id = the message: one message between agents, for the Coordination Room. */
export type TeamData = { sender: Text; recipient: Text; text: string };
/** One question on a card, written by the agent in the engineer's language. */
export type CardQuestion = { id: string; text: string; options?: string[]; free_text?: boolean };
/** One tool of a Connector, with the hints its server gives (core/qsone/connectors/hub.py). */
export type ConnectorTool = { name: string; purpose: string; read_only: boolean; destructive: boolean; open_world: boolean };
/** What a card shows beyond its words (Plan 5): questions to answer, a table whose rows may be ticked, and a
 * Connector being added with its tools. */
export type CardPayload = {
  questions?: CardQuestion[];
  columns?: { key: string; label: Text }[];
  rows?: Record<string, string>[];
  /** The column holding each row's number, and each row's source as the core has it (a price to keep: its quote's
   * file and row, or the chat): the number opens into its source card. */
  number_column?: string;
  row_sources?: (Source | null)[];
  tick?: boolean;
  connector?: { name: string; transport: "stdio" | "http"; runs: string };
  tools?: ConnectorTool[];
  /** A price card's model (core: costs._ask_unknown_price). */
  model?: { connector: string; model: string; name: string };
};
/** data-card, id = the card: anything the engineer must answer. */
export type CardData = {
  kind:
    | "outside"
    | "online"
    | "cap"
    | "price"
    | "budget"
    | "fallback"
    | "desk"
    | "disagreement"
    | "question"
    | "keep"
    | "rows"
    | "cost"
    | "connector";
  title: Text;
  detail: Text;
  options: string[];
  /** What fixes what the detail says, as the core says (core.ts Fix): a model of unknown price, "ai". */
  fix?: string;
  payload?: CardPayload;
  status?: "pending" | "settled" | "withdrawn";
  choice?: string | null;
  /** A settled card with a payload: the answers by question id, and the rows ticked, by index. */
  answers?: Record<string, string>;
  rows_ok?: number[];
  /** The answers that spend money or can't be taken back: press-and-hold, never one click (core: stream.HOLD). */
  hold?: { why: "paid" | "irreversible"; options: string[] };
  /** When the engineer answered (ISO), for the folded card's one-line trace. */
  settled_at?: string;
};
/** data-cost, id = the scope. */
export type CostData = {
  level: "info" | "paused" | "stopped";
  scope: "brief" | "day" | "month";
  spent: string;
  cap: string;
  equivalent: boolean;
  text: Text;
};
export type ReviewComment = { about: string; text: string };
/** data-review, id = the Deliverable. */
export type ReviewData = { code: "A" | "B" | "C"; comments: ReviewComment[]; same_provider: boolean; round?: number };
/** data-unsourced: numbers in the reply that no tool result gave. */
export type UnsourcedData = { values: string[] };
/** data-sourced, id = the Brief: numbers in the reply that exactly one ledger number in a tool result gave, by how
 * the reply writes them, with that number's id and exact value; the reply opens each into its source card. */
export type SourcedData = { numbers: Record<string, { id: string; value: string }> };
/** data-status, id = the Brief. */
/** `fix`: a failed Brief's fix, as the core says (core.ts Fix). */
export type StatusData = { state: BriefState; step: Text | null; fix?: string };
/** data-deliverable, id = the Deliverable (Plan 6): the Lead QS made it; the chat shows its card. */
export type DeliverableData = { id: string };
/** data-understood, id = understood-<Brief id> (Plan 8): the Lead QS read a tender folder; the chat shows the
 * "I understood this" card, which reads the facts itself. */
export type UnderstoodData = { project_id: string };

/** data-facts, id = the Brief (core: engine/truth.py): what ONE's records hold beside the reply (null when it has
 * no BOQ), and a line for each claim of the reply the records do not show. */
export type FactsData = { text: Text | null; flags: Text[] };
/** data-redo, id = the Brief: the reply's words in [from, to) went back to be fixed; the screen drops them. */
export type RedoData = { from: number; to: number };

/** One step of a Brief's work log: who, what, and its real start and end (ISO, the core's clock); `until` is null
 * while it runs. */
export type WorkStep = { agent: Text; text: Text; at: string; until: string | null };
/** data-worklog, id = the Brief (core: engine/worklog.py): when it began and ended (null while it runs), each step. */
export type WorklogData = { started: string; ended: string | null; steps: WorkStep[] };

export type OneData = {
  progress: ProgressData;
  team: TeamData;
  card: CardData;
  cost: CostData;
  review: ReviewData;
  unsourced: UnsourcedData;
  sourced: SourcedData;
  status: StatusData;
  /** data-notice: a line from a tool for the engineer, with its fix (no web search: "search"). */
  notice: { text: Text; fix?: string };
  deliverable: DeliverableData;
  understood: UnderstoodData;
  /** data-view, id = the view (decision 16.1): what the Lead QS chose to show, from ONE's blocks. */
  view: ViewData;
  worklog: WorklogData;
  facts: FactsData;
  redo: RedoData;
};

/** A message the engineer sent while a Brief ran is marked as steering it; one sent with a canvas selection keeps
 * it (Plan 7), shown as a chip. */
export type OneMessage = UIMessage<{ steering?: boolean; selection?: SelectionItem[] }, OneData>;
export type OnePart = OneMessage["parts"][number];

/** The parts of one kind, in the order they first came. */
export function partsOf<K extends keyof OneData>(parts: OnePart[], kind: K): { id: string; data: OneData[K] }[] {
  return parts.flatMap((part) => {
    if (part.type !== `data-${kind}`) return [];
    const data = part as unknown as { id?: string; data: OneData[K] };
    return [{ id: data.id ?? "", data: data.data }];
  });
}

const active: BriefState[] = ["queued", "running", "waiting_engineer", "waiting_connection", "paused_cap"];

/** The Brief still running in these messages, from the last reply's status part. */
export function activeBrief(messages: OneMessage[]): string | undefined {
  const last = messages.findLast((message) => message.role === "assistant");
  const status = last ? partsOf(last.parts, "status").at(-1) : undefined;
  return status && active.includes(status.data.state) ? status.id : undefined;
}
