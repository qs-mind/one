// The data parts a Brief's stream carries (Plan 4, Task 8). Each has a stable id, so the AI SDK updates it in place.
import type { UIMessage } from "ai";
import type { Text } from "../../i18n";

export type BriefState =
  | "queued"
  | "running"
  | "waiting_engineer"
  | "waiting_connection"
  | "paused_cap"
  | "stopped"
  | "done"
  | "failed";

/** data-progress, id = the agent run: what that agent is doing now. */
export type ProgressData = { agent: Text; text: Text };
/** data-team, id = the message: one message between agents, for the Coordination Room. */
export type TeamData = { sender: Text; recipient: Text; text: string };
/** data-card, id = the card: anything the engineer must answer. */
export type CardData = {
  kind: "outside" | "online" | "cap" | "budget" | "fallback" | "desk" | "disagreement";
  title: Text;
  detail: Text;
  options: string[];
  status?: "pending" | "settled" | "withdrawn";
  choice?: string | null;
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

export type OneData = {
  progress: ProgressData;
  team: TeamData;
  card: CardData;
  cost: CostData;
  review: ReviewData;
  unsourced: UnsourcedData;
  status: StatusData;
};

/** A message the engineer sent while a Brief ran is marked as steering it. */
export type OneMessage = UIMessage<{ steering?: boolean }, OneData>;
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
