// The chat stream as the new thread reads it: the contract's new parts (section 3.1) beside the two of today it
// draws (data-progress, data-status), the marks on stored messages (3.3), and the rule that only the last part of a
// type and id is live (3.1, rule 2).
import type { UIMessage } from "ai";
import type { Schemas } from "@/api/client";
import type { CardData as KeptCard } from "@/chat/parts/types";

export type Text = Schemas["Text"];
export type Source = Schemas["Source"];
export type TenderPlan = Schemas["TenderPlan"];
export type Finding = Schemas["Finding"];

/** data-progress, id = the agent run: what that agent is doing now. */
export type ProgressData = { agent: Text; text: Text };
/** data-status, id = the Brief. */
export type BriefState = Schemas["BriefEvent"]["state"];
/** `fix`: what the screen can offer beside a failed Brief's step. */
export type StatusData = { state: BriefState; step: Text | null; fix?: Schemas["LeadBlock"]["fix"] };
/** data-card, id = the card: what a running Brief waits on (3.2), the two new kinds included. */
export type CardData = Omit<KeptCard, "kind"> & { kind: KeptCard["kind"] | "keep_member" | "setting" };

export type ThreadData = {
  progress: ProgressData;
  status: StatusData;
  plan: Schemas["PlanPart"];
  finding: Schemas["FindingPart"];
  sources: Schemas["SourcesPart"];
  steer: Schemas["SteerPart"];
  stage: Schemas["StagePart"];
  card: CardData;
  room: Schemas["RoomMessage"];
};

export type ThreadMessage = UIMessage<Partial<Schemas["StoredMessageMark"]>, ThreadData>;
export type ThreadPart = ThreadMessage["parts"][number];
export type DataPart<K extends keyof ThreadData> = { type: `data-${K}`; id?: string; data: ThreadData[K] };

export const isData = <K extends keyof ThreadData>(part: ThreadPart, kind: K): part is ThreadPart & DataPart<K> =>
  part.type === `data-${kind}`;

/** The text of a message, its text parts joined. */
export const textOf = (message: ThreadMessage): string =>
  message.parts.flatMap((part) => (part.type === "text" ? [part.text] : [])).join("");

/** The key of a part that can repeat: its type and id. */
const keyOf = (part: ThreadPart) => `${part.type}:${"id" in part ? (part.id ?? "") : ""}`;

/** For each pointer part (plan, finding, stage) the place of its last copy in the thread: "<message>:<index>". */
export function livePlaces(messages: readonly ThreadMessage[]): Map<string, string> {
  const last = new Map<string, string>();
  for (const message of messages)
    message.parts.forEach((part, index) => {
      if (part.type === "data-plan" || part.type === "data-finding" || part.type === "data-stage") last.set(keyOf(part), `${message.id}:${index}`);
    });
  return last;
}

/** True when this part is the last of its type and id in the thread, so it draws in full. */
export const isLive = (live: Map<string, string>, message: ThreadMessage, index: number): boolean =>
  live.get(keyOf(message.parts[index]!)) === `${message.id}:${index}`;

const ACTIVE: readonly BriefState[] = ["queued", "running", "waiting_engineer", "waiting_connection", "paused_cap"];

/** The state of the newest Brief in the thread, from the last reply's status part; null when none runs. */
export function briefState(messages: readonly ThreadMessage[]): BriefState | null {
  const reply = messages.findLast((message) => message.role === "assistant");
  const status = reply?.parts.findLast((part) => isData(part, "status")) as DataPart<"status"> | undefined;
  return status && ACTIVE.includes(status.data.state) ? status.data.state : null;
}

/** What the Lead is doing now: the last progress part of a reply that still runs. */
export function liveProgress(messages: readonly ThreadMessage[]): ProgressData | null {
  if (briefState(messages) === null) return null;
  const reply = messages.findLast((message) => message.role === "assistant");
  const progress = reply?.parts.findLast((part) => isData(part, "progress")) as DataPart<"progress"> | undefined;
  return progress?.data ?? null;
}

/** The newest reply's Brief when it ended `failed`: its status part, for the step and the fix to show. */
export function failedBrief(messages: readonly ThreadMessage[]): DataPart<"status"> | null {
  const reply = messages.findLast((message) => message.role === "assistant");
  const status = reply?.parts.findLast((part) => isData(part, "status")) as DataPart<"status"> | undefined;
  return status?.data.state === "failed" ? status : null;
}

/** Every card the thread holds, in order, by its id (the stream replaces a card in place). */
export const cardsOf = (messages: readonly ThreadMessage[]): { id: string; data: CardData }[] =>
  messages.flatMap((m) => m.parts.flatMap((p) => (isData(p, "card") && p.id ? [{ id: p.id, data: (p as DataPart<"card">).data }] : [])));

/** The work log of the newest reply, in the order it came: each worker's step (ended once a newer step came, or the
 * work ended) and what the team said to each other meanwhile. */
export type WorkEntry = { step: ProgressData & { done: boolean } } | { room: Schemas["RoomMessage"] };

export function workLog(messages: readonly ThreadMessage[]): WorkEntry[] {
  const reply = messages.findLast((message) => message.role === "assistant");
  const parts = reply?.parts ?? [];
  const running = briefState(messages) !== null;
  const last = parts.findLastIndex((part) => isData(part, "progress"));
  return parts.flatMap((part, at): WorkEntry[] => {
    if (isData(part, "progress")) return [{ step: { ...(part as DataPart<"progress">).data, done: !running || at < last } }];
    if (isData(part, "room")) return [{ room: (part as DataPart<"room">).data }];
    return [];
  });
}
