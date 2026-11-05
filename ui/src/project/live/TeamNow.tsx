// The team in the chat's head: who is working now («شغال: مهندس التسعير»), or the project team when no one is, as
// a button that opens the team list: the Lead QS and the Checking QS, any agent outside a Desk, then each Desk folded
// to one line («قسم التسعير: واحد شغال») that opens to its members. Role names whole, never Arabic initials.
import { useState } from "react";
import { count, fill, language, pick, t, texts, useLanguage } from "../../i18n";
import { Popover, PopoverContent, PopoverTrigger } from "../../ui/popover";
import { useDesks } from "../../workspace/documents";
import type { DeskInfo } from "../types";
import { useAgents, useDeskAgents, useTeamAgents, type LiveAgent } from "./activity";
import { AgentCard } from "./AgentCard";

const busy = (a: LiveAgent) => a.state === "working" || a.state === "thinking";

/** A team member with no running agent shows as idle; nothing else is made up. */
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

const order = (a: LiveAgent) => ({ lead: 0, checker: 1, specialist: 2, quick: 3 })[a.kind];

function DeskLine({ desk }: { desk: DeskInfo }) {
  const [open, setOpen] = useState(false);
  const agents = useDeskAgents(desk.id);
  return (
    <li className="flex flex-col">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
        className="flex items-center justify-between gap-3 rounded-[10px] px-3 py-1.5 text-start hover:bg-stone focus-visible:outline-2 focus-visible:outline-ink"
      >
        <span dir="auto" className="min-w-0 font-semibold">
          {count("deskSummary", agents.filter(busy).length, { desk: pick(desk.name) })}
        </span>
        <span aria-hidden="true" className="text-xs text-slate">
          {open ? "▴" : "▾"}
        </span>
      </button>
      {open && (
        <ul className="flex flex-col gap-1 ps-3">
          {agents.map((agent) => (
            <AgentCard key={agent.id} agent={agent} />
          ))}
        </ul>
      )}
    </li>
  );
}

/** The team: the project team's members, then the Desks folded. */
export function TeamList() {
  useLanguage();
  const agents = useTeamAgents(); // from the live store: an agent's move never re-renders the document
  const desks = useDesks();
  const rows = [
    ...(agents.some((a) => a.kind === "lead") ? [] : [idle("lead")]),
    ...(agents.some((a) => a.kind === "checker") ? [] : [idle("checker")]),
    ...agents,
  ].sort((a, b) => order(a) - order(b));
  return (
    <ul aria-label={t("projectTeam")} className="flex flex-col gap-2">
      {rows.map((agent) => (
        <AgentCard key={agent.id} agent={agent} />
      ))}
      {desks.map((desk) => (
        <DeskLine key={desk.id} desk={desk} />
      ))}
    </ul>
  );
}

export function TeamNow() {
  useLanguage();
  const working = useAgents().filter(busy);
  const roles = [...new Set(working.map((a) => pick(a.role)))].join(language() === "ar" ? "، " : ", ");
  return (
    <Popover>
      <PopoverTrigger className="min-w-0 truncate rounded-lg px-1 text-start text-xs text-slate hover:text-ink focus-visible:outline-2 focus-visible:outline-ink">
        {working.length ? fill(t("workingNow"), { role: roles }) : t("projectTeam")}
      </PopoverTrigger>
      <PopoverContent align="start" className="max-h-[70vh] w-80 max-w-[calc(100vw-32px)] overflow-y-auto p-3">
        <TeamList />
      </PopoverContent>
    </Popover>
  );
}
