// The project team (team:core): the Lead QS and the Checking QS, plus any agent outside a Desk. A member with no
// running agent shows as idle; nothing else is made up.
import type { Node, NodeProps } from "@xyflow/react";
import { dir, texts, useLanguage } from "../../i18n";
import { useTeamAgents, type LiveAgent } from "../live/activity";
import { AgentCard } from "../live/AgentCard";
import { Frame, frameTitle, memoFrame, type TeamData } from "./Frame";

const idle = (kind: "lead" | "checker"): LiveAgent => ({
  id: `idle-${kind}`,
  kind,
  role: kind === "lead" ? texts.roleLead : texts.roleChecker,
  desk_id: null,
  model: "",
  state: "idle",
  line: null,
  brief_id: null,
  focus: null,
  at: "",
  noNews: false,
});

function TeamFrameView(props: NodeProps<Node<TeamData, "team">>) {
  useLanguage();
  const { collapsed } = props.data;
  const agents = useTeamAgents(); // from the live store: an agent's move never re-renders the canvas
  const rows = [
    ...(agents.some((a) => a.kind === "lead") ? [] : [idle("lead")]),
    ...(agents.some((a) => a.kind === "checker") ? [] : [idle("checker")]),
    ...agents,
  ].sort((a, b) => order(a) - order(b));
  return (
    <Frame
      id="team:core"
      selected={props.selected}
      collapsed={collapsed}
      title={frameTitle({ type: "team", data: props.data })}
      dir={dir()}
    >
      <ul className="flex flex-col gap-1 px-2 pb-2">
        {rows.map((agent) => (
          <AgentCard key={agent.id} agent={agent} />
        ))}
      </ul>
    </Frame>
  );
}

const order = (a: LiveAgent) => ({ lead: 0, checker: 1, specialist: 2, quick: 3 })[a.kind];

export const TeamFrame = memoFrame(TeamFrameView);
