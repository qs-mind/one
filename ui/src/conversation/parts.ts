// The chat stream as the new thread reads it: the contract's new parts (section 3.1) beside the two of today it
// draws (data-progress, data-status), the marks on stored messages (3.3), and the rule that only the last part of a
// type and id is live (3.1, rule 2).
import type { UIMessage } from "ai";
import type { Schemas } from "@/api/client";

export type Text = Schemas["Text"];
export type Source = Schemas["Source"];
export type TenderPlan = Schemas["TenderPlan"];
export type Finding = Schemas["Finding"];

/** data-progress, id = the agent run: what that agent is doing now. */
export type ProgressData = { agent: Text; text: Text };
/** data-status, id = the Brief. */
export type BriefState = Schemas["BriefEvent"]["state"];
export type StatusData = { state: BriefState; step: Text | null };

export type ThreadData = {
  progress: ProgressData;
  status: StatusData;
  plan: Schemas["PlanPart"];
  finding: Schemas["FindingPart"];
  sources: Schemas["SourcesPart"];
  steer: Schemas["SteerPart"];
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
      if (part.type === "data-plan" || part.type === "data-finding") last.set(keyOf(part), `${message.id}:${index}`);
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
