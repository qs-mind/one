// The data parts a Brief's stream carries (Plan 4, Task 8). Each has a stable id, so the AI SDK updates it in place.
import type { UIMessage } from "ai";
import type { SelectionItem } from "../../canvas/types";
import type { Language, Text } from "../../i18n";

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
  tick?: boolean;
  connector?: { name: string; transport: "stdio" | "http"; runs: string };
  tools?: ConnectorTool[];
};
/** data-card, id = the card: anything the engineer must answer. */
export type CardData = {
  kind:
    | "outside"
    | "online"
    | "cap"
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
  payload?: CardPayload;
  status?: "pending" | "settled" | "withdrawn";
  choice?: string | null;
  /** A settled card with a payload: the answers by question id, and the rows ticked, by index. */
  answers?: Record<string, string>;
  rows_ok?: number[];
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
/** data-status, id = the Brief. */
export type StatusData = { state: BriefState; step: Text | null };
/** data-deliverable, id = the Deliverable (Plan 6): the Lead QS made it; the chat shows its card. */
export type DeliverableData = { id: string };

export type OneData = {
  progress: ProgressData;
  team: TeamData;
  card: CardData;
  cost: CostData;
  review: ReviewData;
  unsourced: UnsourcedData;
  status: StatusData;
  deliverable: DeliverableData;
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
