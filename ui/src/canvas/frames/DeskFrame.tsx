// One Desk: its name, Temporary / Draft / Approved, and its specialists. A Desk starts folded to one line
// ("Pricing Desk: 2 working"), so Desks stay quiet in daily work until the engineer opens one.
import type { Node, NodeProps } from "@xyflow/react";
import { dir, t, useLanguage } from "../../i18n";
import { useDeskAgents } from "../live/activity";
import { AgentCard } from "../live/AgentCard";
import type { DeskInfo } from "../types";
import { Frame, frameTitle, memoFrame, type DeskData } from "./Frame";

const stageText: Record<DeskInfo["stage"], "deskTemporary" | "deskDraft" | "deskApproved"> = {
  temporary: "deskTemporary",
  draft: "deskDraft",
  approved: "deskApproved",
};

function DeskFrameView(props: NodeProps<Node<DeskData, "desk">>) {
  useLanguage();
  const { desk, collapsed } = props.data;
  const agents = useDeskAgents(desk.id); // from the live store: an agent's move never re-renders the canvas
  return (
    <Frame
      id={props.id as `desk:${string}`}
      selected={props.selected}
      collapsed={collapsed}
      title={frameTitle({ type: "desk", data: props.data })}
      dir={dir()}
      meta={!collapsed && <span className="shrink-0 text-slate">{t(stageText[desk.stage])}</span>}
    >
      <ul className="flex flex-col divide-y divide-ink/10">
        {agents.map((agent) => (
          <AgentCard key={agent.id} agent={agent} />
        ))}
      </ul>
    </Frame>
  );
}

export const DeskFrame = memoFrame(DeskFrameView);
