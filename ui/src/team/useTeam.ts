// A tender's team (GET /projects/{id}/members), kept current by the activity stream: a `member` event adds or
// replaces one member; a `plan` event and the end of a Brief reload the list (members join with a plan, and their
// records move when work ends). Contract 3.4.
import { useEffect, useState } from "react";
import { subscribeTender } from "@/activity";
import { client, type Schemas } from "@/api/client";

export type TeamMember = Schemas["TeamMember"];
type Text = Schemas["Text"];

export type Team =
  | { state: "loading" }
  | { state: "ready"; members: TeamMember[] }
  | { state: "failed"; error: Text | null };

const ENDED: Schemas["BriefEvent"]["state"][] = ["done", "stopped", "failed"];

/** The core's words of a refusal; null for a body problem (FastAPI's `detail`) that has none. */
export const wordsOf = (error: unknown): Text | null =>
  typeof error === "object" && error !== null && "error" in error ? (error as { error: Text }).error : null;

export function useTeam(projectId: string): { team: Team; reload: () => void } {
  const [team, setTeam] = useState<Team>({ state: "loading" });
  const [round, setRound] = useState(0);

  useEffect(() => {
    let live = true;
    const load = () =>
      void client
        .GET("/projects/{project_id}/members", { params: { path: { project_id: projectId } } })
        .then(({ data, error }) => {
          if (!live) return;
          setTeam(data ? { state: "ready", members: data.members } : { state: "failed", error: wordsOf(error) });
        })
        .catch(() => live && setTeam({ state: "failed", error: null }));
    // Listen first, then load: nothing said meanwhile is missed, and a stream that comes back loads again.
    const stop = subscribeTender(
      projectId,
      (event) => {
        if (!live) return;
        if (event.type === "plan" || (event.type === "brief" && ENDED.includes(event.state))) load();
        if (event.type !== "member") return;
        setTeam((now) => {
          if (now.state !== "ready") return now;
          const at = now.members.findIndex((it) => it.id === event.member.id);
          const members = at < 0 ? [...now.members, event.member] : now.members.with(at, event.member);
          return { state: "ready", members };
        });
      },
      load,
    );
    load();
    return () => {
      live = false;
      stop();
    };
  }, [projectId, round]);

  return { team, reload: () => setRound((n) => n + 1) };
}

/** A member's short name by id, for message headers; null for an id the tender's team does not hold. */
export function nameOf(members: readonly TeamMember[], id: string): Text | null {
  return members.find((it) => it.id === id)?.name ?? null;
}
