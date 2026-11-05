// One team member in the team and Desk frames: role, model, state in words with an icon (never colour alone), the
// Progress Line, what it is on (a button that shows that frame), Follow, and Stop for the Brief it works on.
import { useStore, type ReactFlowState } from "@xyflow/react";
import { useState } from "react";
import { ProviderLogo } from "../../brand/providers/ProviderLogo";
import { coreLine, send } from "../../core";
import { fill, pick, t, texts, useLanguage, type Text } from "../../i18n";
import { canvasApi } from "../api";
import { idOf } from "../frames/Frame";
import type { AgentInfo, Anchor, FrameKey } from "../types";
import { FileName } from "../../ui/FileName";
import { cursorShown, type LiveAgent } from "./activity";
import { follow, stopFollowing, useFollowing } from "./follow";

export const stateText: Record<AgentInfo["state"], keyof typeof texts> = {
  idle: "stateIdle",
  thinking: "stateThinking",
  working: "stateWorking",
  waiting: "stateWaiting",
  done: "stateDone",
  failed: "stateFailed",
};

/** A model not on the sheet: its id, without the API's «models/» prefix. */
const modelLabel = (id: string) => id.replace(/^models\//, "");

/** A shape per state, so the state reads without colour. */
function StateIcon({ state }: { state: AgentInfo["state"] }) {
  const common = { viewBox: "0 0 12 12", className: "h-3 w-3 shrink-0", "aria-hidden": true } as const;
  switch (state) {
    case "working":
      return (
        <svg {...common}>
          <circle cx="6" cy="6" r="4.5" fill="currentColor" />
        </svg>
      );
    case "thinking":
      return (
        <svg {...common}>
          <circle cx="2" cy="6" r="1.3" fill="currentColor" />
          <circle cx="6" cy="6" r="1.3" fill="currentColor" />
          <circle cx="10" cy="6" r="1.3" fill="currentColor" />
        </svg>
      );
    case "waiting":
      return (
        <svg {...common}>
          <rect x="2.5" y="2" width="2.4" height="8" fill="currentColor" />
          <rect x="7.1" y="2" width="2.4" height="8" fill="currentColor" />
        </svg>
      );
    case "done":
      return (
        <svg {...common}>
          <path d="M2 6.5 L5 9.2 L10 3" fill="none" stroke="currentColor" strokeWidth="1.8" />
        </svg>
      );
    case "failed":
      return (
        <svg {...common}>
          <path d="M2.5 2.5 L9.5 9.5 M9.5 2.5 L2.5 9.5" fill="none" stroke="currentColor" strokeWidth="1.8" />
        </svg>
      );
    default:
      return (
        <svg {...common}>
          <circle cx="6" cy="6" r="4" fill="none" stroke="currentColor" strokeWidth="1.5" />
        </svg>
      );
  }
}

/** A frame's name as the canvas shows it; a file not open on the canvas is named from the Project files frame. */
const titleOf = (key: FrameKey) => (s: ReactFlowState) => {
  const node = s.nodeLookup.get(key);
  if (node) return node.ariaLabel ?? null;
  if (!key.startsWith("file:")) return null;
  const files = (s.nodeLookup.get("files:all")?.data as { files?: { id: string; name: string }[] } | undefined)?.files;
  return files?.find((f) => f.id === idOf(key))?.name ?? null;
};

/** «البند 3/02», «صفحة 4»: never a raw id. */
function placeOf(anchor: Anchor | null): string | null {
  if (anchor?.row) return fill(t("anchorRow"), { row: anchor.row });
  if (anchor?.page) return fill(t("anchorPage"), { page: anchor.page });
  return null;
}

const button =
  "nodrag rounded-lg border border-ink/20 px-3 py-1 hover:bg-stone focus-visible:outline-2 focus-visible:outline-ink";

export function AgentCard({ agent }: { agent: LiveAgent }) {
  useLanguage();
  const followed = useFollowing() === agent.id;
  const frame = agent.focus?.frame ?? null;
  const title = useStore(frame ? titleOf(frame) : () => null);
  const [stopping, setStopping] = useState(false);
  const [problem, setProblem] = useState<Text | null>(null);
  const role = pick(agent.role);
  const needsYou = agent.state === "waiting" || agent.state === "failed";
  const running = agent.state !== "done" && agent.state !== "failed" && agent.state !== "idle";
  const place = placeOf(agent.focus?.anchor ?? null);
  const said = place ? t("agentOnAt") : t("agentOn");
  const on = title ? fill(said, { title, place: place ?? "" }) : "";
  const [before = "", after = ""] = said.replace("{place}", place ?? "").split("{title}");

  async function stop() {
    if (!agent.brief_id) return;
    setStopping(true);
    setProblem(null);
    const response = await send(`/briefs/${encodeURIComponent(agent.brief_id)}/stop`, "POST");
    setStopping(false);
    if (!response?.ok) setProblem(await coreLine(response, texts.stopFailed));
  }

  return (
    // min-w-0 and words that wrap: the card fits its frame, never scrolls it sideways or cuts its buttons
    <li className="flex min-w-0 flex-col gap-1.5 rounded-[10px] px-3 py-2.5 [overflow-wrap:anywhere]" data-agent={agent.id}>
      <span className="flex items-center justify-between gap-3">
        <span dir="auto" className="min-w-0 truncate font-semibold">
          {role}
        </span>
        <span className={`flex shrink-0 items-center gap-1 ${needsYou ? "text-copper" : "text-slate"}`}>
          <StateIcon state={agent.state} />
          {t(stateText[agent.state])}
        </span>
      </span>
      {agent.model && (
        <span className="flex min-w-0 max-w-full items-center gap-1.5 self-start text-slate">
          <ProviderLogo provider={agent.provider ?? ""} />
          <bdi dir="ltr" className="min-w-0 truncate">
            {agent.model_name ?? modelLabel(agent.model)}
          </bdi>
        </span>
      )}
      {agent.noNews && <span className="text-slate">{t("noNews")}</span>}
      {agent.line && (
        <span dir="auto" className="text-slate">
          {pick(agent.line, agent.lang)}
        </span>
      )}
      {frame && title && (
        <button
          type="button"
          aria-label={on}
          className="nodrag flex min-w-0 max-w-full items-baseline self-start whitespace-pre text-start underline decoration-ink/30 underline-offset-2 hover:decoration-ink focus-visible:outline-2 focus-visible:outline-ink"
          onClick={(event) => {
            event.stopPropagation(); // the click must not also select the team frame around the card
            canvasApi.focusFrame(frame, agent.focus?.anchor ? { anchor: agent.focus.anchor } : undefined);
          }}
        >
          {/* the frame's name keeps to one line, in its own direction; the words round it stay whole */}
          <span className="shrink-0">{before}</span>
          <FileName name={title} fit />
          <span className="shrink-0">{after}</span>
        </button>
      )}
      {(cursorShown(agent) || (running && agent.brief_id)) && (
        <span className="flex flex-wrap gap-2 pt-1">
          {cursorShown(agent) && (
            <button
              type="button"
              aria-pressed={followed}
              aria-label={followed ? t("stopFollowing") : fill(t("followRole"), { role })}
              className={button}
              onClick={() => (followed ? stopFollowing() : follow(agent.id))}
            >
              {followed ? t("stopFollowing") : t("follow")}
            </button>
          )}
          {running && agent.brief_id && (
            <button
              type="button"
              disabled={stopping}
              aria-label={fill(t("stopRole"), { role })}
              className={`${button} disabled:opacity-50`}
              onClick={() => void stop()}
            >
              {t("stop")}
            </button>
          )}
        </span>
      )}
      {problem && (
        <span role="alert" className="text-copper">
          {pick(problem)}
        </span>
      )}
    </li>
  );
}
