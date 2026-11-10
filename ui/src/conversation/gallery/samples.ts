// The gallery's sample thread: the contract's samples (ui/src/api/samples.json: P1's proposed plan, P2's approved plan
// with its Suggested change, P2's Findings) and parts shaped as section 3.1's examples. Dev only.
import type { Schemas } from "@/api/client";
import raw from "@/api/samples.json?raw";
import { conversationGallery as g } from "@/texts/design/conversation";
import type { Lang } from "@/texts/types";
import type { LogStep } from "../LiveLine";
import type { Finding, TenderPlan, ThreadMessage } from "../parts";

const P1 = "5a000000000000000000000000000001";
const P2 = "5a000000000000000000000000000002";

type Samples = Record<string, unknown> & { [key: `plan:${string}`]: Schemas["PlanView"] };
const samples = JSON.parse(raw) as Samples;

export const planProposed = samples[`plan:${P1}`]!.plan as TenderPlan;
export const planWithChange = samples[`plan:${P2}`]!.plan as TenderPlan;
export const findings = (samples[`findings:${P2}`] as Schemas["Findings"]).findings;
/** The Lead's name as the core gives it ("Lead QS"). */
export const leadName = (samples[`team_members:${P2}`] as Schemas["TeamMembers"]).members.find((m) => m.role === "lead")!.name;

export const raised = findings.find((f) => f.status === "raised")!;
export const queued = findings.find((f) => f.status === "queued")!;
export const settled = findings.find((f) => f.status === "settled" && f.chosen !== null)!;

/** A Finding whose first option spends money: the decision card holds it. */
export const paidFinding: Finding = {
  ...raised,
  id: "5a0000000000000000000000000090a1",
  title: g.paidTitle,
  options: [g.paidOption, g.freeOption],
};

export const log: LogStep[] = [
  { agent: g.leadAgent, text: g.stepFiles, done: true },
  { agent: g.leadAgent, text: g.stepPlan, done: true },
  { agent: g.agent, text: g.stepConditions, done: false },
];

/** The thread in one language: ONE's reading after a drop, the reply with a decision, a question, the plan reply. */
export function sampleThread(lang: Lang): ThreadMessage[] {
  return [
    { id: "b1-question", role: "user", metadata: { by: "one", at: "2026-11-09T08:00:00.000000+00:00" }, parts: [] },
    {
      id: "b1-reply",
      role: "assistant",
      parts: [
        { type: "text", text: g.leadRead[lang] },
        { type: "data-finding", id: raised.id, data: { finding_id: raised.id } },
        { type: "data-sources", id: "b1", data: { sources: raised.sources } },
        { type: "data-status", id: "b1", data: { state: "done", step: null } },
      ],
    },
    { id: "b2-question", role: "user", parts: [{ type: "text", text: g.engineerAsks[lang] }] },
    {
      id: "b2-reply",
      role: "assistant",
      parts: [
        { type: "text", text: g.leadShort[lang] },
        { type: "data-plan", id: planProposed.id, data: { plan_id: planProposed.id, version: planProposed.version } },
        { type: "data-steer", id: "5a0000000000000000000000000000e1", data: { text: g.steer[lang], at: "2026-11-09T08:02:00.000000+00:00" } },
        { type: "data-status", id: "b2", data: { state: "running", step: null } },
        { type: "data-progress", id: "run-1", data: { agent: g.agent, text: g.reading } },
      ],
    },
  ];
}
