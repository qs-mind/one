// What the tender place shows, from its routes and its live events (contract, section 0): the header and what waits
// (GET .../tender), the plan, the Findings and the team. It listens first, opens the tender in the core
// (openTender.ts), then reads, and does both again after the stream comes back; an event that carries the whole thing
// replaces it, a plan event also reloads the team.
import { useCallback, useEffect, useRef, useState } from "react";
import { subscribeTender } from "@/activity";
import { client, type Schemas, type TenderActivity } from "@/api/client";
import { tender as texts } from "@/texts/tender";
import { openTender } from "./openTender";

export type TenderData = {
  /** null until read. */
  view: Schemas["TenderView"] | null;
  /** Why it could not be read: the core's words, or "unreachable" when no answer came. */
  refused: Schemas["Text"] | "unreachable" | null;
  /** undefined until read; null when the tender has no plan. */
  plan: Schemas["TenderPlan"] | null | undefined;
  findings: Schemas["Finding"][];
  members: Schemas["TeamMember"][];
  /** The core opened the tender: what reads its records (the documents) may start. */
  open: boolean;
};

const EMPTY: TenderData = { view: null, refused: null, plan: undefined, findings: [], members: [], open: false };
/** The core's words in a refusal; a body with none (a malformed request, a bug) reads as "it did not go through". */
const wordsOf = (error: unknown): Schemas["Text"] =>
  typeof error === "object" && error !== null && "error" in error ? (error as Schemas["Refusal"]).error : texts.failed;

export function useTender(projectId: string) {
  const [data, setData] = useState<TenderData>(EMPTY);
  const [brief, setBrief] = useState<Schemas["BriefEvent"] | null>(null);
  // An answer that comes after the place closed, or after it moved to another tender, is dropped.
  const shown = useRef<string | null>(null);
  const put = useCallback(
    (change: (d: TenderData) => TenderData) => {
      if (shown.current === projectId) setData(change);
    },
    [projectId],
  );

  const readMembers = useCallback(async () => {
    const { data: team } = await client.GET("/projects/{project_id}/members", { params: { path: { project_id: projectId } } });
    if (team) put((d) => ({ ...d, members: team.members }));
  }, [projectId, put]);

  const read = useCallback(async () => {
    const refused = await openTender(projectId, () => shown.current === projectId);
    if (refused) return put((d) => (d.view ? d : { ...d, refused }));
    put((d) => (d.open ? d : { ...d, open: true }));
    const path = { params: { path: { project_id: projectId } } };
    const [tender, plan, findings] = await Promise.all([
      client.GET("/projects/{project_id}/tender", path).catch(() => ({ data: undefined, error: undefined })),
      client.GET("/projects/{project_id}/plan", path).catch(() => ({ data: undefined })),
      client.GET("/projects/{project_id}/findings", path).catch(() => ({ data: undefined })),
    ]);
    put((d) => ({
      ...d,
      view: tender.data ?? d.view,
      refused: tender.data || d.view ? null : tender.error ? wordsOf(tender.error) : "unreachable",
      plan: plan.data ? plan.data.plan : d.plan,
      findings: findings.data?.findings ?? d.findings,
    }));
    await readMembers().catch(() => undefined);
  }, [projectId, put, readMembers]);

  useEffect(() => {
    shown.current = projectId;
    setData(EMPTY);
    const on = (event: TenderActivity) => {
      if (event.type === "plan") {
        setData((d) => ({ ...d, plan: event.plan }));
        void readMembers().catch(() => undefined);
      } else if (event.type === "tender") setData((d) => ({ ...d, view: { tender: event.tender, waiting: event.waiting } }));
      else if (event.type === "finding")
        setData((d) => {
          const known = d.findings.some((f) => f.id === event.finding.id);
          const findings = known ? d.findings.map((f) => (f.id === event.finding.id ? event.finding : f)) : [...d.findings, event.finding];
          return { ...d, findings };
        });
      else if (event.type === "member")
        setData((d) => ({ ...d, members: d.members.map((m) => (m.id === event.member.id ? event.member : m)) }));
      else if (event.type === "brief") {
        setBrief(event);
        // a member's record changes when its work ends (S183)
        if (event.state !== "running" && event.state !== "queued") void readMembers().catch(() => undefined);
      }
    };
    const stop = subscribeTender(projectId, on, () => void read());
    void read();
    return () => {
      shown.current = null;
      stop();
    };
  }, [projectId, read, readMembers]);

  // Each write answers the thing it changed (kept here), or the core's words when it refused; it throws only when the
  // core cannot be reached.
  const settle = <T,>(answer: { data?: T; error?: unknown }, keep: (value: T) => void): Schemas["Text"] | null => {
    if (answer.data === undefined) return wordsOf(answer.error);
    keep(answer.data);
    return null;
  };
  const path = { path: { project_id: projectId } };

  const actions = {
    async approvePlan(version: number) {
      const answer = await client.POST("/projects/{project_id}/plan/approve", { params: path, body: { version } });
      return settle(answer, (v) => put((d) => ({ ...d, plan: v.plan })));
    },
    async answerChange(changeId: string, accept: boolean) {
      const answer = await client.POST("/projects/{project_id}/plan/change", { params: path, body: { change_id: changeId, accept } });
      return settle(answer, (v) => put((d) => ({ ...d, plan: v.plan })));
    },
    async decide(findingId: string, choice: 0 | 1) {
      const answer = await client.POST("/projects/{project_id}/findings/{finding_id}/decide", {
        params: { path: { project_id: projectId, finding_id: findingId } },
        body: { choice },
      });
      return settle(answer, (f) => put((d) => ({ ...d, findings: d.findings.map((x) => (x.id === f.id ? f : x)) })));
    },
    async requestPlan() {
      const answer = await client.POST("/projects/{project_id}/plan/request", { params: path });
      return settle(answer, () => undefined);
    },
  };

  return { ...data, brief, actions };
}
